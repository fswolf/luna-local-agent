"""Whose voice is that: Luna tells the people she knows apart by how they
sound, so in a house with more than one of you she knows who's talking.

Each spoken turn's recording (the same one Whisper hears) is turned into
a voice print: 192 numbers from SpeechBrain's ECAPA speaker model,
describing how a voice sounds, not what it said. That is compared with
the prints of everyone enrolled (senses/people.py); the closest one wins if it
is close enough (people.voice_match). Nobody close enough means the
person at the keyboard, the way it always was.

    /people enroll voice Shannon     she reads 5 lines out loud, one
                                     at a time, and each becomes a print

It runs on the CPU in well under a second, beside transcription, so a
turn takes no longer. It needs the voices extra:

    python3 installer/install.py --extras voices      (pip install speechbrain)

and fetches the model (about 80 MB) once into ~/.cache/ai-voice/models.
Nothing is recorded: the print is made from the turn's audio in memory
and only enrolment keeps prints, never the sound.
"""
import os
import random
import threading

import config
from core import logbook

MODEL = "speechbrain/spkrec-ecapa-voxceleb"
MODEL_DIR = os.path.expanduser("~/.cache/ai-voice/models/ecapa")
RATE = 16000
MIN_SECONDS = 1.0              # shorter than this, a print is mostly guesswork
ENROLL_TURNS = 5

# What to read out while enrolling, 5 of them at random each time, so nobody
# has to make something up on the spot and the prints don't all come from
# the same words. Everyday things said to a home assistant, 9-10 words
# (3-5 seconds), a mix of questions and statements and of s, sh, th, r and
# l sounds. Written by ChatGPT on the agent bridge for this.
LINES = (
    "Could you turn on the lights near the window?",
    "Please play something cheerful while I tidy this room.",
    "Is there a chance of rain later this afternoon?",
    "Let's keep the music soft for a little while.",
    "Can you set a short timer for three minutes?",
    "Please remind me to water the flowers this evening.",
    "Which shelf would look better with a small plant?",
    "Could you lower the shades before the sun gets brighter?",
    "That gentle sound of rain is really quite relaxing.",
    "Let's try a different light color in this room.",
    "Would you tell me a short story about the ocean?",
    "Please pause the song until I come back here.",
    "How long will it take to finish this playlist?",
    "The yellow cushion looks lovely beside the blue chair.",
    "Thank you for helping make this space feel welcoming.",
)

_state = {"model": None, "error": "", "loading": False, "enroll": None}
_lock = threading.Lock()


def available():
    """Is SpeechBrain installed? (Cheap: doesn't load anything.)"""
    try:
        import importlib.util

        return importlib.util.find_spec("speechbrain") is not None
    except (ImportError, ValueError):
        return False


def enabled():
    return bool(getattr(config, "PEOPLE_VOICE", True))


def wanted():
    """Worth loading the model: switched on, installed, and someone has
    voice prints or is being enrolled."""
    if not enabled() or not available():
        return False
    if _state["enroll"]:
        return True
    from senses import people

    return any(p.get("voice") for p in people.everyone().values())


def _load():
    """The speaker model, loaded once. None (and a reason) if it can't be."""
    if _state["model"] is not None:
        return _state["model"]
    with _lock:
        if _state["model"] is not None:
            return _state["model"]
        if not available():
            _state["error"] = "SpeechBrain isn't installed - python3 installer/install.py --extras voices"
            return None
        _state["loading"] = True
        try:
            try:
                from speechbrain.inference.speaker import EncoderClassifier
            except ImportError:                       # SpeechBrain before 1.0
                from speechbrain.pretrained import EncoderClassifier
            os.makedirs(MODEL_DIR, exist_ok=True)
            extra = {}
            try:
                # SpeechBrain links its files into savedir by default, and
                # Windows won't make symlinks without developer mode
                from speechbrain.utils.fetching import LocalStrategy

                extra["local_strategy"] = LocalStrategy.COPY
            except ImportError:
                pass
            _state["model"] = EncoderClassifier.from_hparams(source=MODEL, savedir=MODEL_DIR,
                                                             run_opts={"device": "cpu"}, **extra)
            _state["error"] = ""
            logbook.info("voices", "speaker model ready")
        except Exception as e:
            _state["error"] = f"the speaker model didn't load: {e}"
            logbook.warn("voices", "speaker model failed: %s", e)
        finally:
            _state["loading"] = False
    return _state["model"]


def warm_up():
    """Load the model in the background at startup, if anyone needs it."""
    if wanted():
        threading.Thread(target=_load, daemon=True, name="voices-load").start()


def _samples(audio):
    """A wav path or an array -> float32 mono at 16 kHz, or None."""
    import numpy as np

    if isinstance(audio, str):
        from scipy.io.wavfile import read

        rate, audio = read(audio)
    else:
        rate = RATE
    audio = np.asarray(audio)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if audio.dtype.kind in "iu":
        audio = audio.astype(np.float32) / float(np.iinfo(audio.dtype).max)
    audio = audio.astype(np.float32)
    if rate != RATE and len(audio):
        idx = np.linspace(0, len(audio) - 1, int(len(audio) * RATE / rate))
        audio = np.interp(idx, np.arange(len(audio)), audio).astype(np.float32)
    return audio if len(audio) >= MIN_SECONDS * RATE else None


def print_of(audio):
    """192 numbers for this voice, or None (too short, or no model)."""
    samples = _samples(audio)
    if samples is None:
        return None
    model = _load()
    if model is None:
        return None
    import torch

    with torch.no_grad():
        emb = model.encode_batch(torch.from_numpy(samples).unsqueeze(0))
    return [float(v) for v in emb.squeeze().tolist()]


def identify(audio):
    """(name, score) for whoever said this, (people.STRANGER, best score)
    when it clearly isn't the owner, (None, best score) when it's nobody
    she can place, or (None, None) when no comparison could be made. Also takes the
    turn as an enrolment print when one is running."""
    job = _state["enroll"]
    if not job and not wanted():
        return None, None
    try:
        vector = print_of(audio)
    except Exception as e:
        logbook.warn("voices", "voice print failed: %s", e)
        if job:
            _stop_enrolment(job, f"a voice print failed ({e})")
        return None, None
    if vector is None:
        if job and _state["error"]:
            # no speaker model: every line would fail the same way, and she
            # isn't answering spoken turns while an enrolment runs
            _stop_enrolment(job, _state["error"])
        elif job:
            _tell(f"That was too short for a voice print - read it again: \"{_line(job)}\"")
        return None, None

    from senses import people

    if job:
        total = people.add_prints(job["name"], "voice", [vector])
        job["got"] += 1
        left = job["need"] - job["got"]
        if left <= 0:
            _state["enroll"] = None
        _tell(f"Voice print {job['got']}/{job['need']} for {job['name']} ({total} stored)."
              + (f" Next, read: \"{_line(job)}\"" if left > 0 else f" Done: she'll know {job['name']}'s voice now."))
        return job["name"], 1.0
    # a name, people.STRANGER (clearly not the owner), or None (can't tell)
    return people.verdict("voice", vector, float(getattr(config, "PEOPLE_VOICE_MATCH", 0.3)))


def enroll(name, turns=ENROLL_TURNS):
    """Take the next `turns` spoken turns as name's voice prints.
    Returns (ok, message)."""
    if not enabled():
        return False, "Voice recognition is off (people.voice in the settings pane)."
    if not available():
        return False, "Voice prints need SpeechBrain: python3 installer/install.py --extras voices"
    turns = max(1, int(turns))
    lines = random.sample(LINES, min(turns, len(LINES)))
    _state["enroll"] = {"name": name, "need": turns, "got": 0, "lines": lines}
    threading.Thread(target=_load, daemon=True, name="voices-load").start()
    return True, (f"Listening for {name}: {turns} lines, read out loud one at a time in a normal voice. "
                  f"She only listens while enrolling, she won't answer them. /people cancel stops it.\n"
                  f"First, read: \"{_line(_state['enroll'])}\"")


def _stop_enrolment(job, why):
    """An enrolment that can't go on: stopped, so she answers spoken turns again."""
    if _state["enroll"] is job:
        _state["enroll"] = None
    _tell(f"Voice enrolment for {job['name']} stopped: {why}. "
          f"{job['got']} print(s) kept; /people enroll voice {job['name']} starts again.")


def _line(job):
    """The line to read for the job's next print."""
    lines = job.get("lines") or LINES
    return lines[job["got"] % len(lines)]


def enrolling():
    """Is a voice enrolment running? Its turns are samples, not things to answer."""
    return bool(_state["enroll"])


def cancel():
    job, _state["enroll"] = _state["enroll"], None
    return job


def status():
    if not enabled():
        return "Voice recognition: off"
    if not available():
        return "Voice recognition: needs SpeechBrain (installer --extras voices)"
    if _state["loading"]:
        return "Voice recognition: loading the speaker model"
    if _state["error"]:
        return f"Voice recognition: {_state['error']}"
    job = _state["enroll"]
    if job:
        return (f"Voice recognition: enrolling {job['name']} ({job['got']}/{job['need']}), "
                f"next line: \"{_line(job)}\"")
    return "Voice recognition: " + ("ready" if _state["model"] is not None else "idle (nobody has voice prints yet)"
                                   if not wanted() else "will load on the next spoken turn")


def _tell(line):
    try:
        import ui

        ui.add_message("system", line)
    except Exception:
        pass
