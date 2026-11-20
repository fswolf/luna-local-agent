"""sounddevice, for a machine without PortAudio: she runs, but can't hear
or speak until it's installed (portaudio19-dev / portaudio-devel /
portaudio). Everything that opens a device raises PortAudioError, which
the voice code already catches as "no audio device"; the rest does nothing.

    from voice.nosound import sd       # sounddevice, or this stand-in
"""
import time

MISSING = ""          # why sounddevice wouldn't load ("" when it did)


class PortAudioError(Exception):
    pass


class _Default:
    device = (None, None)
    samplerate = None


default = _Default()


def _missing(*_a, **_k):
    raise PortAudioError("PortAudio isn't installed - install it for her voice and microphone")


InputStream = OutputStream = Stream = _missing
play = rec = playrec = query_devices = check_input_settings = check_output_settings = _missing


def query_hostapis(*_a, **_k):
    return ()


def get_stream():
    return None


def stop(*_a, **_k):
    pass


def wait(*_a, **_k):
    pass


def sleep(msec):
    time.sleep(msec / 1000)


def _terminate():
    pass


def _initialize():
    pass


try:
    import sounddevice as sd
except OSError as e:              # sounddevice raises OSError when libportaudio isn't there
    import sys

    sd = sys.modules[__name__]
    MISSING = str(e) or "PortAudio library not found"
