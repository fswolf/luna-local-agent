"""Sound devices: opening the mic, playing her voice through PortAudio, and
afplay on a Mac when PortAudio gives up.

Part of the voice package; voice/speech.py is the front door.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import sounddevice as sd
import numpy as np
from core import logbook
import ui
from scipy.io.wavfile import write
import config
from config import SAMPLE_RATE
from voice.tts import _lip_stop, _lip_sync


_audio_warned = [0.0]


def _reset_portaudio():
    """Make PortAudio forget and re-read the audio devices. Only when no
    microphone stream is open: restarting it under one breaks that stream.
    Holding _mic_lock, so none can open while it restarts."""
    with _mic_lock:
        if _mic_streams[0] > 0:
            return

        try:
            sd._terminate()
            sd._initialize()
            logbook.info("speech", "restarted PortAudio to re-read the audio devices")
        except Exception as e:
            logbook.warn("speech", "couldn't restart PortAudio: %s", e)


# Every microphone stream (recording, barge-in, the wake word) opens and
# closes through these, so _reset_portaudio knows when one is open.
_mic_lock = threading.Lock()
_mic_streams = [0]


def _open_mic(blocksize):
    """A started mono float32 input stream at SAMPLE_RATE, counted."""
    with _mic_lock:
        stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1,
                                blocksize=blocksize, dtype="float32")
        try:
            stream.start()
        except Exception:
            stream.close()
            raise
        _mic_streams[0] += 1

    return stream


def _close_mic(stream):
    try:
        stream.stop()
        stream.close()
    except Exception:
        pass    # already gone with the device; the count still has to drop
    finally:
        with _mic_lock:
            _mic_streams[0] -= 1


_native_rate = [False]   # set once CoreAudio has refused the voice's own rate


def _resample(samples, rate, target):
    if not target or target == rate or len(samples) < 2:
        return samples, rate
    n = max(1, int(len(samples) * target / rate))
    out = np.interp(np.linspace(0, len(samples) - 1, n), np.arange(len(samples)), samples)
    return out.astype(np.float32), target


def _device_rate():
    try:
        return int(sd.query_devices(kind="output")["default_samplerate"])
    except Exception:
        return 0


def _start_playback(samples, rate):
    """sd.play, made to survive macOS and Bluetooth.

    macOS's CoreAudio sometimes refuses to open a stream (PortAudio's
    -9986 "Internal PortAudio error", CoreAudio's 'what'). The usual cause
    is Bluetooth headphones: opening their microphone switches them to
    headset mode, the output device changes rate under PortAudio's feet,
    and PortAudio's cached idea of the device is stale. So: wait, restart
    PortAudio so it re-reads the devices, try again, then try at the
    device's own rate. A voice that can't play is
    reported once and skipped - the reply is on screen either way - rather
    than taking the whole speaker thread down with it."""
    # On a Mac, play at the output device's own rate. Bluetooth headphones
    # run at 44.1 kHz (music) or 16/24 kHz (call mode) and CoreAudio can
    # refuse anything else outright - her Mac took 44100 straight away
    # after refusing Kokoro's 24000 five times. Elsewhere, only after a
    # refusal has been seen once.
    if sys.platform == "darwin" or _native_rate[0]:
        samples, rate = _resample(samples, rate, _device_rate())

    try:
        sd.play(samples, rate)
        return True
    except sd.PortAudioError as e:
        first = e

    # Bluetooth takes a second or two to switch back from headset mode to
    # music mode after the mic closes - longer than a fast model takes to
    # answer, which is why LM Studio (slower) got away with it and
    # llama-server didn't. So keep trying for up to ~3 seconds, re-reading
    # the devices each time, before falling back to the device's own rate.
    for wait in (0.25, 0.5, 0.75, 1.0):
        try:
            sd.stop()
            time.sleep(wait)
            _reset_portaudio()
            sd.play(samples, rate)
            logbook.info("speech", "speakers opened after a retry (%s)", first)
            return True
        except sd.PortAudioError:
            continue

    try:
        device_rate = int(sd.query_devices(kind="output")["default_samplerate"])
        if device_rate and device_rate != rate and len(samples) > 1:
            n = max(1, int(len(samples) * device_rate / rate))
            resampled = np.interp(np.linspace(0, len(samples) - 1, n),
                                  np.arange(len(samples)), samples).astype(np.float32)
            sd.play(resampled, device_rate)
            logbook.info("speech", "played at the device's %d Hz after: %s", device_rate, first)
            _native_rate[0] = True      # from now on, go straight to the device's rate
            return True
    except Exception:
        pass

    logbook.warn("speech", "couldn't open the speakers: %s | %s", first, _audio_devices())

    if time.monotonic() - _audio_warned[0] > 60:
        _audio_warned[0] = time.monotonic()
        ui.add_message("system", f"Couldn't play her voice ({first}). The reply is on screen; "
                                 "check the sound output device.")

    return False


def _audio_devices():
    """One line about the devices PortAudio sees, for the log."""
    try:
        out = sd.query_devices(kind="output")
        inp = sd.query_devices(kind="input")
        return (f"out={out['name']!r} {int(out['default_samplerate'])}Hz "
                f"in={inp['name']!r} {int(inp['default_samplerate'])}Hz "
                f"default={sd.default.device}")
    except Exception as e:
        return f"devices unknown ({e})"


# macOS fallback: afplay, the system's own player. It talks to CoreAudio
# directly, takes any rate, and doesn't care what mode Bluetooth headphones
# are in - which is exactly where PortAudio gives up. Once it's needed it's
# used for the rest of the session, so no sentence waits out the retries.
_afplay = [None, False]      # [running process, switched over]
_afplay_rate = [0]           # a rate afplay has accepted this session (0 = not yet known)
AFPLAY = shutil.which("afplay") if sys.platform == "darwin" else None


def _use_afplay():
    """afplay from the start on a Mac (tts.player "auto"), or once PortAudio
    has refused; never when tts.player is "portaudio"."""
    player = str(getattr(config, "TTS_PLAYER", "auto")).lower()
    if not AFPLAY or player == "portaudio":
        return False
    return player == "afplay" or sys.platform == "darwin" or _afplay[1]


def _play_afplay(samples, rate, stop):
    """Play one chunk with afplay; False if interrupted (`stop`, interrupts.Stop).

    Bluetooth headphones on macOS can refuse the voice's own rate
    outright ("AudioQueueStart failed ('what')" for Kokoro's 24 kHz), so
    a refused file is rewritten at 44.1 kHz, then 48 kHz, and the rate
    that works is used first from then on."""
    rates = [rate, 44100, 48000]

    if _afplay_rate[0]:
        rates = [_afplay_rate[0]] + [r for r in rates if r != _afplay_rate[0]]

    # 'what' is usually transient: Bluetooth still in headset mode right
    # after the mic closed. llama-server answers before it switches back,
    # so back off and retry for ~3s instead of giving up in 0.3s.
    for n, wait in enumerate((0, 0.5)):
        if wait and stop.speaking.wait(wait):
            return False
        for attempt, target in enumerate(dict.fromkeys(rates)):
            played, outcome = _afplay_once(*_resample(samples, rate, target), stop)

            if played is None:           # interrupted
                return False

            if played:
                if attempt or n:
                    logbook.info("speech", "afplay took the audio at %d Hz (not %d) on pass %d",
                                 target, rate, n + 1)
                _afplay_rate[0] = target
                return True

            logbook.warn("speech", "afplay refused %d Hz (pass %d): %s", target, n + 1, outcome)

    # Keep the refused audio so it can be inspected (empty? NaN? odd rate?).
    try:
        dump = os.path.join(os.path.expanduser("~/.cache/ai-voice"), "last-refused.wav")
        write(dump, rate, (np.nan_to_num(np.clip(samples, -1, 1)) * 32767).astype(np.int16))
        logbook.warn("speech", "afplay refused every try: %d samples @ %d Hz, finite=%s, peak=%.3f -> %s",
                     len(samples), rate, bool(np.isfinite(samples).all()),
                     float(np.nanmax(np.abs(samples))) if len(samples) else 0.0, dump)
    except Exception as e:
        logbook.warn("speech", "couldn't save refused audio: %s", e)
    return "refused"


def _afplay_once(samples, rate, stop):
    """(played, message): played is True, False (refused), or None (interrupted)."""
    fd, path = tempfile.mkstemp(prefix="luna-", suffix=".wav")
    os.close(fd)

    try:
        write(path, rate, (np.clip(samples, -1, 1) * 32767).astype(np.int16))
        proc = subprocess.Popen([AFPLAY, path], stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    except Exception as e:
        try:
            os.unlink(path)
        except OSError:
            pass
        return False, f"couldn't start afplay: {e}"

    _afplay[0] = proc
    started = time.monotonic()

    try:
        while proc.poll() is None:
            if stop.speaking.wait(0.05):    # wakes the moment it's set
                proc.kill()
                _lip_stop()
                return None, "interrupted"

        err = (proc.stderr.read() or b"").decode("utf-8", "replace").strip()
        took = time.monotonic() - started

        if proc.returncode != 0 or "failed" in err.lower():
            return False, f"exit {proc.returncode} after {took:.1f}s: {err or 'no message'}"

        logbook.debug("speech", "afplay played %.1fs of audio at %d Hz in %.1fs", len(samples) / rate, rate, took)
        return True, ""
    finally:
        _afplay[0] = None
        try:
            os.unlink(path)
        except OSError:
            pass


def _play(samples, rate, stop):
    """Play one chunk; return False if it was stopped (`stop`, interrupts.Stop)."""
    _lip_sync(samples, rate)

    if _use_afplay():
        result = _play_afplay(samples, rate, stop)
        if result != "refused":
            return result
        # afplay can't get the speakers; try PortAudio in-process instead,
        # and stick with it from now on if it works.
        logbook.info("speech", "afplay refused - trying PortAudio")
        if not _start_playback(samples, rate):
            if time.monotonic() - _audio_warned[0] > 60:
                _audio_warned[0] = time.monotonic()
                ui.add_message("system", "Couldn't play her voice (afplay and PortAudio both refused). "
                                         "The reply is on screen; the log has the details.")
            return True
        config.TTS_PLAYER = "portaudio"
        logbook.info("speech", "PortAudio played it - using PortAudio from now on")

    if not _start_playback(samples, rate):
        if AFPLAY:
            if not _afplay[1]:
                _afplay[1] = True
                logbook.info("speech", "PortAudio won't open the speakers - playing with afplay from now on")
                ui.add_message("system", "Playing her voice through macOS's own player (afplay) - "
                                         "PortAudio wouldn't open the speakers.")
            return _play_afplay(samples, rate, stop) is not False
        return True     # skipped, not interrupted: carry on with the rest

    while True:
        stream = sd.get_stream()

        if stream is None or not stream.active:
            return True

        if stop.speaking.wait(0.05):        # wakes the moment it's set
            sd.stop()
            _lip_stop()
            return False
