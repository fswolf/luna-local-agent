"""Cutting her off: listening while she talks so you can interrupt, and
waiting for the wake word.

Part of the voice package; voice/speech.py is the front door.
"""
import sounddevice as sd
from core import logbook
import ui
import config
from config import SAMPLE_RATE
from voice.listen import VAD_BLOCK_SIZE, _rms, levels
from voice import listen
from voice.playback import _afplay, _close_mic, _open_mic


# ---------------------------------------------------------------------------
# Barge-in
#
# The problem with listening while she talks is that the microphone
# hears her too, and Silero is quite right to call that speech. With no
# echo cancellation available the only honest discriminator left is
# loudness: her voice arrives at the mic attenuated by the room, yours
# doesn't.
#
# So the first fraction of a second of playback is used to measure how
# loud she is *at the microphone*, and after that it takes both a
# confident speech classification and a level well above that baseline,
# sustained, to count as you interrupting. On headphones the baseline is
# near silence and this is trivially reliable; on speakers it depends on
# your volume, which is why the margin is configurable.
# ---------------------------------------------------------------------------
BARGE_IN_CALIBRATION_SECONDS = 0.5
BARGE_IN_FLOOR = 0.004      # below this it's room tone, not a person
BARGE_IN_ARM_TIMEOUT = 20.0 # give up waiting for playback to start


def _playing():
    """Is audio actually coming out of the speakers right now?

    The distinction matters more than it sounds. The watcher starts
    when the first sentence is handed to the TTS server, which is a
    second or so before any sound exists - and calibrating against that
    silence sets the baseline to the noise floor, after which her own
    first word clears the bar and she interrupts herself. Every time.
    """
    if _afplay[0] is not None and _afplay[0].poll() is None:
        return True

    try:
        stream = sd.get_stream()
    except Exception:
        return False

    return stream is not None and stream.active


def _speech_probability(block):
    """Raw Silero probability for one 512-sample frame."""
    import torch

    with torch.no_grad():
        return float(listen._vad_model(torch.from_numpy(block), SAMPLE_RATE).item())


def _watch_for_barge_in(done, stop):
    """Stop the reply's speaking (`stop`, its interrupts.Stop) if the user
    starts talking over Luna. `done`: playback finished, stop watching.

    Runs for as long as playback does. Bails out quietly on any audio
    error - failing to offer barge-in is a missing nicety, but crashing
    the speaker thread would lose the reply.
    """
    threshold = min(0.95, config.STT_VAD_THRESHOLD + config.STT_BARGE_IN_BOOST)
    block_seconds = VAD_BLOCK_SIZE / SAMPLE_RATE
    needed = max(1, int(config.STT_BARGE_IN_SECONDS / block_seconds))

    bleed = []
    calibrating = max(1, int(BARGE_IN_CALIBRATION_SECONDS / block_seconds))
    baseline = None
    streak = 0

    levels["barge_peak"] = 0.0
    levels["barge_probability"] = 0.0

    # The model carries LSTM state between frames, and it was last used
    # on your voice, not hers.
    try:
        listen._vad_model.reset_states()
    except Exception:
        pass

    try:
        stream = _open_mic(VAD_BLOCK_SIZE)
    except Exception:
        return

    waited = 0.0

    try:
        while not done.is_set() and not stop.speaking.is_set():
            audio, _overflow = stream.read(VAD_BLOCK_SIZE)
            block = audio[:, 0].copy()
            level = _rms(block)

            # Nothing to talk over yet. Keep draining the mic so the
            # buffer doesn't go stale, but don't measure anything.
            if not _playing():
                if baseline is None:
                    waited += block_seconds

                    if waited > BARGE_IN_ARM_TIMEOUT:
                        return

                continue

            if baseline is None:
                bleed.append(level)

                if len(bleed) >= calibrating:
                    # Upper quartile: her loudest moments are the ones
                    # that would otherwise trigger a false interrupt.
                    bleed.sort()
                    baseline = max(
                        BARGE_IN_FLOOR, bleed[int(len(bleed) * 0.75)]
                    )
                    levels["barge_baseline"] = baseline
                    logbook.debug(
                        "barge-in", "calibrated | her level at the mic=%.4f "
                        "(floor %.4f) | you need %.4f to cut in",
                        baseline, BARGE_IN_FLOOR,
                        baseline * config.STT_BARGE_IN_MARGIN,
                    )

                continue

            levels["barge_peak"] = max(levels["barge_peak"], level)

            if level < baseline * config.STT_BARGE_IN_MARGIN:
                streak = 0
                continue

            try:
                probability = _speech_probability(block)
            except Exception:
                return

            levels["barge_probability"] = max(
                levels["barge_probability"], probability
            )

            if probability < threshold:
                streak = 0
                continue

            streak += 1

            if streak >= needed:
                # The line that would have found this bug in a minute:
                # a baseline at the floor means calibration ran during
                # silence, so she is interrupting herself.
                logbook.info(
                    "barge-in",
                    "fired | level=%.4f baseline=%.4f needed>%.4f "
                    "speech=%.2f threshold=%.2f held=%.2fs",
                    level, baseline, baseline * config.STT_BARGE_IN_MARGIN,
                    probability, threshold, streak * block_seconds,
                )
                stop.barged_in = True
                stop.stop(speaking=True)

                try:
                    from mind import mood

                    mood.note_bargein()
                except Exception:
                    pass  # moods are decoration; never break the audio path
                ui.set_status("Stopped - go ahead")
                return
    except Exception:
        return
    finally:
        _close_mic(stream)


def barge_in_available():
    return config.STT_BARGE_IN and listen._vad_model is not None


# ---------------------------------------------------------------------------
# Wake word
# ---------------------------------------------------------------------------
def wait_for_wake_word(should_stop):
    """Block until the wake word is heard.

    Returns True if it fired, False if `should_stop()` asked us to give
    up. Nothing else runs while this does - no Whisper, no model, just
    a 1.5MB classifier over 80ms frames - so it can sit here all day.
    """
    from voice import wakeword

    if not wakeword.available():
        return True  # nothing to wait for; behave as before

    ui.set_status(f"Waiting for \"{wakeword.label()}\"")
    wakeword.reset()

    try:
        stream = _open_mic(wakeword.FRAME_SIZE)
    except Exception as e:
        ui.add_message("system", f"Wake word listener couldn't open the mic: {e}")
        return True

    try:
        while not should_stop():
            audio, _overflow = stream.read(wakeword.FRAME_SIZE)

            if wakeword.heard(audio[:, 0].copy()):
                return True
    except Exception as e:
        ui.add_message("system", f"Wake word listener stopped: {e}")
        return True
    finally:
        _close_mic(stream)

    return False
