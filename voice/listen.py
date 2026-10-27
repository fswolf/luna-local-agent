"""Recording you: calibrating the room, deciding when you started and stopped
talking (energy or Silero VAD), and the levels /mic shows.

Part of the voice package; voice/speech.py is the front door.
"""
import os
import tempfile
import numpy as np
from core import interrupts
from core import logbook
import ui
from scipy.io.wavfile import write
from collections import deque
import config
from config import SAMPLE_RATE, STT_VAD
from voice.playback import _close_mic, _open_mic


# ---------------------------------------------------------------------------
# Recording / voice activity detection
#
# The old version compared RMS against a hardcoded 0.035 and nothing else.
# That's roughly ten times the level a normal desktop mic produces, so on
# most inputs `started` never flipped true, the silence timer never began,
# and every recording ran to the 60-second cap instead of stopping when
# you did. Thresholds are now derived from the actual noise floor, with
# separate levels to start and to keep going.
# ---------------------------------------------------------------------------
BLOCK_SIZE = 1024                 # 64ms at 16kHz, energy path
VAD_BLOCK_SIZE = 512              # 32ms - what the Silero model expects
CALIBRATION_SECONDS = 0.4         # listen to the room before arming
SMOOTHING = 3                     # blocks averaged, so one quiet frame
                                  # doesn't look like you stopped talking
PRE_ROLL_SECONDS = 0.8            # audio kept from before speech was detected
MIN_SPEECH_SECONDS = 0.25         # shorter than this is a cough, not a sentence
ABSOLUTE_FLOOR = 0.0022           # don't trust a silent-room calibration
NOISE_CEILING = 0.02              # don't trust a loud one either

# Energy-path multipliers. Lowered from 3.0/1.5: with only loudness to go
# on, a high bar is late to trigger and a high floor treats quiet
# syllables as silence. Silero replaces the guesswork entirely.
START_MULTIPLIER = 2.2
CONTINUE_MULTIPLIER = 1.15

# Set by load_models() when silero-vad imports.
_vad_model = None
vad_backend = "energy"


def _load_vad():
    """Load Silero if we're allowed to and it's installed.

    It is a genuine speech classifier rather than a loudness meter, which
    is the whole difference: it can trigger on the first syllable without
    also triggering on a fan, and it won't end a turn because you went
    quiet for a moment.
    """
    global _vad_model, vad_backend

    if STT_VAD == "energy":
        vad_backend = "energy"
        return

    try:
        from silero_vad import load_silero_vad

        _vad_model = load_silero_vad()
        vad_backend = "silero"
    except Exception as e:
        _vad_model = None
        vad_backend = "energy"

        if STT_VAD == "silero":
            # Explicitly asked for it, so say why it isn't happening.
            try:
                ui.add_message(
                    "system",
                    f"silero-vad unavailable ({e}) - using the energy detector. "
                    "pip install silero-vad",
                )
            except Exception:
                pass

# Last measurement, surfaced by /mic so a bad mic is diagnosable.
levels = {
    "noise_floor": 0.0,
    "start": 0.0,
    "continue": 0.0,
    "peak": 0.0,
    "speech_seconds": 0.0,
    "triggered": False,
    "mode": config.STT_MODE,
    "backend": "energy",
    # Barge-in, reported by /barge
    "barge_baseline": 0.0,
    "barge_peak": 0.0,
    "barge_probability": 0.0,
}


def _rms(block):
    return float(np.sqrt(np.mean(block ** 2)))


def _calibrate(stream):
    """Measure the room for a moment to place the thresholds.

    Uses the lower quartile rather than the mean, so starting to talk
    immediately after pressing HOME doesn't drag the noise floor up and
    deafen the detector.
    """
    readings = []

    for _ in range(max(1, int(CALIBRATION_SECONDS * SAMPLE_RATE / BLOCK_SIZE))):
        audio, _overflow = stream.read(BLOCK_SIZE)
        readings.append(_rms(audio[:, 0]))

    readings.sort()

    return readings[len(readings) // 4] if readings else 0.0


# The turn's recording, for Whisper. The system's temp folder: "/tmp" is
# C:\tmp on Windows, which doesn't exist.
_INPUT_WAV = os.path.join(tempfile.gettempdir(), "luna-input.wav")


def _record_energy(mode):
    """RMS fallback. Only loudness to work with, so it is late to start
    and prone to cutting off - see _record_silero for the good path."""
    record_immediately = mode == "manual"
    stop_on_silence = mode != "manual"
    give_up_after = config.STT_NO_SPEECH_TIMEOUT if mode == "auto" else None
    max_seconds = config.STT_MANUAL_MAX_SECONDS if mode == "manual" else config.STT_MAX_SECONDS

    stream = _open_mic(BLOCK_SIZE)

    try:
        noise = min(_calibrate(stream), NOISE_CEILING)

        sensitivity = max(0.1, config.STT_SENSITIVITY)
        start_threshold = max(ABSOLUTE_FLOOR, noise * START_MULTIPLIER) / sensitivity
        continue_threshold = max(
            ABSOLUTE_FLOOR / 2, noise * CONTINUE_MULTIPLIER
        ) / sensitivity

        levels.update({
            "noise_floor": noise,
            "start": start_threshold,
            "continue": continue_threshold,
            "peak": 0.0,
            "speech_seconds": 0.0,
            "triggered": record_immediately,
            "mode": mode,
            "backend": "energy",
        })

        block_seconds = BLOCK_SIZE / SAMPLE_RATE
        pre_roll = deque(maxlen=max(1, int(PRE_ROLL_SECONDS / block_seconds)))
        recent = deque(maxlen=SMOOTHING)

        chunks = []
        started = record_immediately
        silence = 0.0
        elapsed = 0.0

        if record_immediately:
            ui.set_status("Recording...")

        while True:
            audio, _overflow = stream.read(BLOCK_SIZE)
            block = audio[:, 0].copy()

            level = _rms(block)
            recent.append(level)
            smoothed = sum(recent) / len(recent)

            elapsed += block_seconds
            levels["peak"] = max(levels["peak"], level)

            if not started:
                pre_roll.append(block)

                # Raw level to trigger: waiting for the smoothed average
                # costs you the first syllable.
                if level > start_threshold:
                    started = True
                    levels["triggered"] = True
                    chunks.extend(pre_roll)
                    chunks.append(block)
                    ui.set_status("Recording...")
                elif give_up_after is not None and elapsed >= give_up_after:
                    return None  # you never said anything
            else:
                chunks.append(block)

                if stop_on_silence:
                    # Smoothed level to *stop*: a pause between words
                    # shouldn't end the recording.
                    if smoothed > continue_threshold:
                        silence = 0.0
                    else:
                        silence += block_seconds

                    if silence >= config.STT_SILENCE_SECONDS:
                        break

            if interrupts.current().listening.is_set():     # HOME, or manual's second press
                break

            if elapsed >= max_seconds:
                break
    finally:
        _close_mic(stream)

    if not started or not chunks:
        return None

    recorded = np.concatenate(chunks)

    # Drop the trailing silence that ended the recording - Whisper
    # hallucinates filler over long silent tails.
    keep = len(recorded) - int(max(0.0, silence - 0.3) * SAMPLE_RATE)
    recorded = recorded[:max(0, keep)]

    speech_seconds = len(recorded) / SAMPLE_RATE
    levels["speech_seconds"] = speech_seconds

    if speech_seconds < MIN_SPEECH_SECONDS:
        return None

    filename = _INPUT_WAV
    write(filename, SAMPLE_RATE, recorded)

    return filename


def _record_silero(mode):
    """Silero VAD path.

    VADIterator hands back {'start': ...} the first frame that crosses
    the threshold and {'end': ...} only after min_silence of genuine
    non-speech - and it ends at (threshold - 0.15), not the threshold, so
    trailing off quietly doesn't terminate the turn. That built-in
    hysteresis is what the energy detector could never do.
    """
    from silero_vad import VADIterator

    iterator = VADIterator(
        _vad_model,
        threshold=min(0.9, max(0.1, config.STT_VAD_THRESHOLD)),
        sampling_rate=SAMPLE_RATE,
        min_silence_duration_ms=int(config.STT_SILENCE_SECONDS * 1000),
        speech_pad_ms=200,
    )
    iterator.reset_states()

    give_up_after = config.STT_NO_SPEECH_TIMEOUT if mode == "auto" else None
    block_seconds = VAD_BLOCK_SIZE / SAMPLE_RATE

    levels.update({
        "noise_floor": 0.0,
        "start": config.STT_VAD_THRESHOLD,
        "continue": max(0.0, config.STT_VAD_THRESHOLD - 0.15),
        "peak": 0.0,
        "speech_seconds": 0.0,
        "triggered": False,
        "mode": mode,
        "backend": "silero",
    })

    stream = _open_mic(VAD_BLOCK_SIZE)

    pre_roll = deque(maxlen=max(1, int(PRE_ROLL_SECONDS / block_seconds)))
    chunks = []
    started = False
    elapsed = 0.0

    try:
        while True:
            audio, _overflow = stream.read(VAD_BLOCK_SIZE)
            block = audio[:, 0].copy()

            elapsed += block_seconds
            levels["peak"] = max(levels["peak"], _rms(block))

            try:
                event = iterator(block)
            except Exception:
                # Model unhappy with a frame - don't let it kill the turn.
                event = None

            if not started:
                pre_roll.append(block)

                if event and "start" in event:
                    started = True
                    levels["triggered"] = True
                    chunks.extend(pre_roll)
                    ui.set_status("Recording...")
                elif give_up_after is not None and elapsed >= give_up_after:
                    return None
            else:
                chunks.append(block)

                if event and "end" in event:
                    break

            if interrupts.current().listening.is_set():     # HOME, or manual's second press
                break

            if elapsed >= config.STT_MAX_SECONDS:
                break
    finally:
        _close_mic(stream)

    if not started or not chunks:
        return None

    recorded = np.concatenate(chunks)
    speech_seconds = len(recorded) / SAMPLE_RATE
    levels["speech_seconds"] = speech_seconds

    logbook.debug("stt", "silero captured %.1fs | mode=%s peak=%.4f",
                  speech_seconds, mode, levels["peak"])

    if speech_seconds < MIN_SPEECH_SECONDS:
        logbook.debug("stt", "dropped: %.2fs is shorter than %.2fs",
                      speech_seconds, MIN_SPEECH_SECONDS)

        return None

    filename = _INPUT_WAV
    write(filename, SAMPLE_RATE, recorded)

    return filename


def record_audio(mode=None):
    """Record a turn. Returns a wav path, or None if there was nothing
    worth transcribing.

    Three shapes, because one size genuinely doesn't fit:

      auto   - wait for speech, stop on silence. Good for a quick
               question.
      manual - record from the moment you press, stop when you press
               again. Silence ignored entirely, so you can gather your
               thoughts mid-sentence.
      open   - wait for speech however long it takes, stop on silence.
               Same as auto minus the give-up timeout, because hands
               free there's nothing to give up on.
    """
    mode = mode or config.STT_MODE

    # Manual has nothing to detect - you decide both ends.
    if mode != "manual" and _vad_model is not None:
        try:
            return _record_silero(mode)
        except Exception as e:
            logbook.exception("stt", "silero failed, falling back to levels")
            ui.add_message(
                "system", f"Silero VAD failed ({e}) - falling back to levels."
            )

    return _record_energy(mode)
