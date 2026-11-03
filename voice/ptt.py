"""Push-to-talk, in three shapes.

  auto   - HOME starts listening, silence ends the turn.
  manual - HOME starts recording, HOME stops it. Silence is ignored, so
           a pause mid-sentence doesn't cut you off.
  open   - hands free. HOME arms the mic and it stays armed: speech
           starts a turn, silence ends it, and once Luna has answered it
           re-arms itself. HOME again switches it off.

Shared by the keyboard listeners, the control socket and the TUI, so
every input path behaves identically.
"""
import threading
import time

import config
from core import interrupts, logbook, safe
from voice import playback, speech
import ui
from voice import wakeword

from core.assistant import assistant_task

# Runtime override for config.STT_MODE, set by /mode.
_mode = config.STT_MODE

_hands_free = False
_loop_thread = None


def mode():
    return _mode


def set_mode(new_mode):
    """Switch modes at runtime. Returns the mode actually in effect."""
    global _mode

    new_mode = str(new_mode).strip().lower()

    if new_mode not in ("auto", "manual", "open"):
        return None

    # Leaving open mode while the loop is running would strand it.
    if _mode == "open" and new_mode != "open":
        stop_hands_free()

    _mode = new_mode
    ui.set_mode(_mode)

    return _mode


def hands_free_active():
    return _hands_free


# ---------------------------------------------------------------------------
# Single turn (auto / manual)
# ---------------------------------------------------------------------------
def _start_turn(model):
    # You're about to talk: whatever she's saying (a reminder, a chat
    # reply) goes quiet first, or the mic records her instead of you.
    interrupts.stop_all(generating=False, listening=False)

    # Opened here, at the press, not when the worker gets going: a second
    # press a moment later has to find it.
    stop = interrupts.open("voice")

    def run():
        with interrupts.using(stop):
            assistant_task(model, _mode)

    threading.Thread(target=run, daemon=True).start()


def _interrupt():
    """Cancel the turn: shut up, stop listening, stop generating."""
    ui.set_status("Stopped")
    interrupts.home()

    # Anything physical stops with her: a toy left running because you
    # cut her off mid-sentence is the wrong way round.
    try:
        import plugins

        plugins.panic()
    except Exception:
        pass


def _finish_recording():
    """Manual mode's second press: end the recording, keep the turn.

    Emphatically not _interrupt(). Pressing HOME to finish speaking is a
    request for an answer, so it must not set stop_generating - doing
    that aborted the reply the press had just asked for, and the turn
    came back empty every time.
    """
    ui.set_status("Transcribing...")
    interrupts.stop_all(speaking=False, generating=False, listening=True, kinds=("voice",))


# ---------------------------------------------------------------------------
# Hands-free loop (open)
# ---------------------------------------------------------------------------
def _hands_free_loop(model):
    """Listen, answer, listen again.

    Recording proper still only happens between turns - her own voice
    out of the speakers would otherwise retrigger the mic and she'd
    talk to herself indefinitely - and the settle pause covers the tail
    end of playback.

    Barge-in is the exception, and it is handled during playback by a
    separate monitor with a much higher bar (speech.watch_for_barge_in).
    When it fires the user is already mid-sentence, so waiting out the
    settle pause would eat the start of what they're saying.
    """
    # With a wake word loaded, she waits for her name before the first
    # turn - and then stays open for a while afterwards, so a follow-up
    # question doesn't need saying it again. Without one, every turn
    # starts on speech, which is what open mode always did.
    follow_up_until = 0.0
    failures = 0

    try:
        while _hands_free:
            mic_failed = False

            if wakeword.available() and time.monotonic() > follow_up_until:
                heard = speech.wait_for_wake_word(lambda: not _hands_free)

                if heard is None:           # the mic didn't open, or died
                    mic_failed = True
                elif not heard or not _hands_free:
                    break
                else:
                    _pause(safe.seconds(wakeword.cooldown_seconds(), 1.0, hi=60))

            if not mic_failed:
                playback.clear_mic_error()
                try:
                    # Once the wake word has armed it, a silent turn should
                    # time out rather than wait forever - it was probably the
                    # television. Without a wake word, waiting is the point.
                    with interrupts.using(kind="voice") as stop:
                        spoke = assistant_task(
                            model, "auto" if wakeword.available() else "open"
                        )
                except Exception as e:
                    ui.add_message("system", f"Listening stopped: {e}")
                    break

                # The turn swallows its own errors, so ask the mic layer
                # whether it was the microphone that failed. A turn she
                # answered heard you, whatever barge-in's own mic did.
                mic_failed = not spoke and bool(playback.mic_error())

            if not _hands_free:
                break

            # A dead mic used to go round this loop every half second for
            # ever, a message and a traceback each time. Back off, and
            # after a few in a row stop and say so once.
            if mic_failed:
                failures += 1
                if failures >= MIC_FAILURES_TO_STOP:
                    ui.add_message(
                        "system",
                        f"Hands-free stopped: the microphone isn't available "
                        f"({playback.mic_error() or 'it would not open'}). "
                        "Press HOME to try again.",
                    )
                    break
                _pause(min(30.0, 2.0 ** failures))
                continue

            failures = 0

            # Only hold the door open if she actually answered something.
            follow_up_until = (
                time.monotonic() + safe.seconds(config.WAKE_WORD_FOLLOW_UP_SECONDS, 0)
                if spoke else 0.0
            )

            if not stop.barged_in:
                _pause(safe.seconds(config.STT_SETTLE_SECONDS, 0.6, hi=60))
    except Exception:
        # A thread that dies here would leave open mode "on" with nothing
        # listening; log it and switch hands-free off properly instead.
        logbook.exception("ptt", "hands-free loop failed")
        logbook.tell("Hands-free listening stopped after an error. Press HOME to start it again.")
    finally:
        stop_hands_free()


# Mic failures in a row before hands-free gives up rather than retrying.
MIC_FAILURES_TO_STOP = 3


def _pause(seconds):
    """Sleep, but wake early when hands-free is switched off."""
    until = time.monotonic() + seconds

    while _hands_free and time.monotonic() < until:
        time.sleep(min(0.2, max(0.0, until - time.monotonic())))


def start_hands_free(model):
    global _hands_free, _loop_thread

    if _hands_free:
        return

    _hands_free = True
    ui.set_status("Listening (hands free)")

    _loop_thread = threading.Thread(
        target=_hands_free_loop, args=(model,), daemon=True
    )
    _loop_thread.start()


def stop_hands_free():
    global _hands_free

    if not _hands_free:
        return

    _hands_free = False

    # Breaks any recording currently in progress.
    interrupts.home()

    ui.set_status("Idle")


# ---------------------------------------------------------------------------
# What HOME does
# ---------------------------------------------------------------------------
def toggle(model):
    if _mode == "open":
        if _hands_free:
            stop_hands_free()
        else:
            start_hands_free(model)
        return

    if interrupts.busy():
        # The same key, two meanings, decided by whether the mic is open.
        # In manual mode you press to start and press to finish, so a
        # press while recording is "I'm done, go" - not "forget it".
        # Once she's thinking or talking, it's "forget it".
        if _mode == "manual" and interrupts.recording():
            _finish_recording()
        else:
            _interrupt()

        return

    _start_turn(model)


def stop(model=None):
    """Interrupt only - never starts a turn. Unlike HOME it has only the
    one meaning, so it stops whatever she's doing that can be stopped,
    not just your own turn."""
    if _mode == "open":
        stop_hands_free()
        return

    if interrupts.busy(kinds=None):
        _interrupt()
