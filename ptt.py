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
import interrupts
import speech
import ui
import wakeword

from assistant import assistant_task

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

    while _hands_free:
        if wakeword.available() and time.monotonic() > follow_up_until:
            if not speech.wait_for_wake_word(lambda: not _hands_free):
                break

            if not _hands_free:
                break

            time.sleep(wakeword.cooldown_seconds())

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

        if not _hands_free:
            break

        # Only hold the door open if she actually answered something.
        follow_up_until = (
            time.monotonic() + config.WAKE_WORD_FOLLOW_UP_SECONDS
            if spoke else 0.0
        )

        if not stop.barged_in:
            time.sleep(config.STT_SETTLE_SECONDS)

    stop_hands_free()


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
