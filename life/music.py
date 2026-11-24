"""She listens to the music you play: what kind it is and its beat.

The listening itself is done by a small service on her server
(server/music/listen.py, set up by server/music/install.sh); this side only
records and asks. When the player (playerctl) starts a new track, about
music.after seconds in (10, past the intro) she records music.seconds (8) of
what your speakers are playing (the sound card's monitor, never the mic),
sends it to music.url and keeps the answer: music, talking or both, the
style ("dub techno"), the tempo and where the beats fall. One look per track.

What she does with it:
- her situation line: "Music playing: Artist - Title; sounds like dub techno, about 128 BPM, heavy bass"
- the portrait gets a "music" event: energetic music and she dances to it
  (when she's idle and in the mood), a chill song and she bobs her head on
  the beat; rave styles sometimes bring out the rave set; the glow sticks
  pulse on the beat (portrait/viewer/portrait.js, props.js)

Off until music.url is set. Needs playerctl, and parec (PipeWire/Pulse) or
ffmpeg to record. The clip goes to the service and is dropped there.
"""
import io
import shutil
import subprocess
import threading
import time
import urllib.request
import wave
import zlib

import config
from core import logbook

RATE = 16000                  # what's recorded and sent (the service resamples for the beat)
POLL = 3                      # seconds between looks at the player
RECENT = 30 * 60              # a paused song's answer is kept this long, for the same track coming back

RAVE = ("Techno", "House", "Trance", "Dubstep", "Drum n Bass", "Jungle", "Hardstyle", "Hardcore", "Gabber",
        "Breakbeat", "Breaks", "Electro", "Bass Music", "Trap", "Garage", "Grime", "Makina", "Big Beat",
        "Juke", "Footwork", "Phonk", "Donk", "Hard Dance", "Eurodance", "Hands Up")

_state = {"track": None, "title": "", "since": 0.0, "asked": False, "answer": None, "at": None,
          "playing": False, "thread": None, "cache": {}, "sent": None, "why": ""}
_lock = threading.Lock()
_listening = threading.Lock()  # one recording at a time


def enabled():
    return bool(getattr(config, "MUSIC_URL", "")) and shutil.which("playerctl") is not None


def _run(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=5, errors="replace")
        return r.returncode == 0, (r.stdout or "").strip()
    except (OSError, subprocess.TimeoutExpired):
        return False, ""


def player():
    """(playing?, track key, 'Artist - Title') from playerctl."""
    ok, status = _run(["playerctl", "status"])
    if not ok:
        return False, None, ""
    ok, meta = _run(["playerctl", "metadata", "--format", "{{playerName}}|{{artist}}|{{title}}"])
    meta = meta if ok else ""
    name, _, rest = meta.partition("|")
    artist, _, title = rest.partition("|")
    shown = " - ".join(p for p in (artist.strip(), title.strip()) if p)
    return status.lower() == "playing", meta or None, shown


def _talking():
    """She's speaking or a turn is running: her own voice would be in the clip."""
    try:
        from core import interrupts

        return interrupts.busy(kinds=None)
    except Exception:
        return False


def record(seconds):
    """Raw 16 kHz mono 16-bit sound from what the speakers play, or None."""
    if shutil.which("parec"):
        cmd = ["parec", "-d", "@DEFAULT_MONITOR@", "--format=s16le", f"--rate={RATE}", "--channels=1", "--raw"]
    elif shutil.which("ffmpeg"):
        cmd = ["ffmpeg", "-loglevel", "quiet", "-f", "pulse", "-i", "@DEFAULT_MONITOR@", "-t", str(seconds),
               "-ac", "1", "-ar", str(RATE), "-f", "s16le", "-"]
    else:
        return None
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    except OSError:
        return None
    timer = threading.Timer(seconds, p.terminate)
    timer.start()
    try:
        data = p.stdout.read()
    finally:
        timer.cancel()
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:                # didn't take the hint: make it
            p.kill()
            p.wait()
    return data[: RATE * 2 * int(seconds)] or None


def as_wav(raw):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(raw)
    return buf.getvalue()


def service():
    """music.url as the service's address. It's meant to be the address alone
    (http://host:8795), but one of its own paths pasted in from a browser
    test - .../health, .../listen - made every clip go to .../health/listen,
    a 404, and she never heard a song. So a trailing path of the service's
    own is taken off."""
    url = str(getattr(config, "MUSIC_URL", "") or "").strip().rstrip("/")
    for path in ("/health", "/listen"):
        if url.lower().endswith(path):
            url = url[: -len(path)].rstrip("/")
    return url


def ask(wav):
    """The service's answer (a dict) for a WAV clip. Raises on failure."""
    import json
    import urllib.error

    url = service() + "/listen"
    req = urllib.request.Request(url, data=wav, headers={"Content-Type": "audio/wav"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise RuntimeError(f"{url} isn't the listening service (404): music.url should be its address, "
                               f"like http://host:8795 - it's {config.MUSIC_URL!r}") from None
        raise


def style_name(label):
    """'Electronic---Dub Techno' -> 'dub techno'."""
    return label.split("---")[-1].lower() if label else ""


def tempo(bpm, exact=False):
    """Into the 70-180 range a person would say (a 64 is really 128).
    Doubling keeps the beats where they were, with one more between each."""
    bpm = float(bpm or 0)
    while 0 < bpm < 70:
        bpm *= 2
    while bpm > 180:
        bpm /= 2
    return round(bpm, 3) if exact else round(bpm)


def period(beats, bpm):
    """Seconds per beat: a straight line through the beat times when there are
    enough of them (steadier than the tempo, which is rounded), else from bpm."""
    if len(beats) >= 4:
        n = len(beats)
        mx, my = (n - 1) / 2, sum(beats) / n
        num = sum((i - mx) * (b - my) for i, b in enumerate(beats))
        den = sum((i - mx) ** 2 for i in range(n))
        if den and num > 0:
            return num / den
    return 60 / bpm if bpm else 0


def summary(answer, started):
    """What the portrait and her prompt need from the service's answer.
    started: time.time() when the clip began, so beats line up with the clock."""
    styles = answer.get("styles") or []
    top = [(l, s) for l, s in styles if s >= 0.1][:3]
    kind = answer.get("kind", "music")
    bpm = tempo(answer.get("bpm"))
    beats = answer.get("beats") or []
    loud = float(answer.get("loud", -60))
    # the style part only: every electronic label starts "Electronic---", which "Electro" would match
    rave = kind == "music" and any(any(w.lower() in style_name(l) for w in RAVE) and s >= 0.15 for l, s in top)
    energetic = kind == "music" and loud > -35 and (bpm >= 112 or rave)
    p = period(beats, answer.get("bpm"))
    return {"kind": kind, "style": style_name(top[0][0]) if top else "", "styles": [style_name(l) for l, _ in top],
            "bpm": bpm, "beat_bpm": tempo(60 / p, exact=True) if p else 0,    # the pulse the portrait keeps time with
            "beat_at": round(started + beats[0], 3) if beats else None,
            "bass": float(answer.get("bass", 0)), "energetic": energetic, "rave": rave}


def _emit(kind, /, **data):       # /: the event has a "kind" of its own (music, speech, mixed)
    try:
        from web import livefeed

        livefeed.emit(kind, **data)
    except Exception:
        pass


def _send(s):
    if s and s["kind"] != "speech":
        _emit("music", on=True, kind=s["kind"], style=s["style"], bpm=s.get("beat_bpm") or s["bpm"], beat_at=s["beat_at"],
              energetic=s["energetic"], rave=s["rave"], dance=bool(getattr(config, "MUSIC_DANCE", True)),
              rave_ok=bool(getattr(config, "MUSIC_RAVE", True)),
              song=zlib.crc32((_state["track"] or "").encode()))   # the same song, so the portrait keeps its choices
    else:
        _emit("music", on=False)


def listen_now(wait=False):
    """Record and ask now (the track's one look, or /music now). The summary,
    or None with _state["why"] saying why not. wait: when a listen is already
    under way (the track's own, ten seconds in), wait for it and give its
    answer - /music now said "couldn't listen" whenever it landed on one."""
    if not _listening.acquire(blocking=False):
        if not wait:
            return None                                # already listening
        with _listening:                               # its result, not a second recording
            return _state["answer"] if _state["answer"] else None
    try:
        return _listen()
    finally:
        _listening.release()


def _listen():
    key = _state["track"]
    started = time.time()
    _state["why"] = ""
    raw = record(float(getattr(config, "MUSIC_SECONDS", 8)))
    if not raw:
        _state["why"] = "couldn't record what's playing (needs parec or ffmpeg)"
        logbook.warn("music", _state["why"])
        return None
    try:
        answer = ask(as_wav(raw))
    except Exception as e:
        _state["why"] = f"the listening service didn't answer: {e}"
        logbook.warn("music", "%s", _state["why"])
        return None
    s = summary(answer, started)
    with _lock:
        if _state["track"] == key:                     # still the same song
            _state.update(answer=s, at=time.monotonic())
            if key:
                c, t = _state["cache"], time.monotonic()
                for k in [k for k, (_, at) in c.items() if t - at > RECENT]:
                    del c[k]
                c[key] = (s, t)
    logbook.info("music", "%s: %s %s BPM (%s)", _state["title"] or "?", s["kind"], s["bpm"], s["style"] or "no style")
    if _state["track"] == key and _state["playing"]:
        _send(s)
        _state["sent"] = key
    return s


def describe():
    """A line for her prompt (mind/situation.py)."""
    s, title = _state["answer"], _state["title"]
    if not _state["playing"] or not s:
        return ""
    what = f"Music playing: {title}" if title else "Music playing"
    if s["kind"] == "speech":
        return f"Playing: {title or 'something'} (mostly talking, not music)"
    bits = []
    if s["style"]:
        bits.append(f"sounds like {s['style']}" + (f" ({', '.join(s['styles'][1:])})" if len(s["styles"]) > 1 else ""))
    if s["bpm"]:
        bits.append(f"about {s['bpm']} BPM")
    if s["bass"] >= 0.45:
        bits.append("heavy bass")
    if s["kind"] == "mixed":
        bits.append("someone talking over it")
    return what + ("; " + ", ".join(bits) if bits else "")


def tick(now=None):
    now = time.monotonic() if now is None else now
    playing, key, title = player()
    playing = playing and key is not None
    with _lock:
        if key != _state["track"]:
            _state.update(track=key, title=title, since=now, asked=False, answer=None)
            cached = _state["cache"].get(key)
            if cached and now - cached[1] < RECENT:     # the same song again: no need to listen twice
                _state.update(answer=cached[0], asked=True)
        if playing and not _state["playing"]:
            _state["since"] = now                      # the 10 s count from when it plays
            if _state["answer"] and _state["answer"].get("beat_at"):
                # resumed (or the same song again): the style still holds, the beat doesn't
                _state["answer"] = dict(_state["answer"], beat_at=None)
                _state["asked"] = False
        _state["playing"] = playing
        answer, sent = _state["answer"], _state["sent"]
    # tell the portrait what's on (once per track), and when it stops
    if playing and answer and sent != key:
        _send(answer)
        _state["sent"] = key
    elif sent is not None and (not playing or sent != key):
        _emit("music", on=False)
        _state["sent"] = None
    after = float(getattr(config, "MUSIC_AFTER", 10))
    if playing and not _state["asked"] and now - _state["since"] >= after and not _talking():
        _state["asked"] = True
        threading.Thread(target=listen_now, daemon=True, name="music-listen").start()


def _loop():
    while True:
        try:
            if enabled():
                tick()
        except Exception as e:
            logbook.warn("music", "tick failed: %s", e)
        time.sleep(POLL)


def start():
    if _state["thread"] is None:
        _emit("music", on=False)
        _state["thread"] = threading.Thread(target=_loop, daemon=True, name="music")
        _state["thread"].start()
