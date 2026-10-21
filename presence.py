"""Presence: Luna notices when someone is in front of the webcam.

With camera.presence.enabled on, one thread keeps the webcam open and looks
for a face a few times a second (camera.presence.fps, 3 by default). It
costs a few percent of one CPU core and no GPU. From that:

- **Greets you on arrival.** When someone shows up after being gone longer
  than greet_after_minutes, she says hi in one short line, the way the
  startup greeting works, and only when nothing else is going on.
- **Looks at you.** While a face is in view her portrait's eyes follow it
  instead of aiming at the terminal (livefeed's gaze loop asks gaze()).
- **Goes quiet when nobody's there.** After quiet_after_minutes with no
  face, nobody_here() is true: game turns and scheduled jobs stop speaking
  out loud (they still write to the screen), and the startup greeting
  waits for someone to arrive.
- **Knows faces.** /people enroll face <name> stores a few face prints in
  agent/people/ (people.py); after that a face in view is matched to a
  name, which the greeting and voice recognition use.

Nothing is recorded or sent: frames live in memory only, the latest one
also serves look_at_camera (camera.py) so the two never fight over the
device.

Face finding is OpenCV's YuNet, face prints OpenCV's SFace (two small ONNX
models fetched once into ~/.cache/ai-voice/models). Until YuNet is there,
OpenCV's own Haar detector stands in: it finds faces but can't tell whose.
"""
import os
import threading
import time
import urllib.request

import config
import logbook

MODEL_DIR = os.path.expanduser("~/.cache/ai-voice/models")
MODELS = {
    "detect": ("face_detection_yunet_2023mar.onnx", (
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
        "https://huggingface.co/opencv/face_detection_yunet/resolve/main/face_detection_yunet_2023mar.onnx",
    ), 100_000),
    "recognise": ("face_recognition_sface_2021dec.onnx", (
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
        "https://huggingface.co/opencv/face_recognition_sface/resolve/main/face_recognition_sface_2021dec.onnx",
    ), 10_000_000),
}
WIDTH = 640                 # what faces are looked for in; plenty for a desk
ABSENT_AFTER = 8.0          # seconds without a face before she counts you gone
GREET_COOLDOWN = 300.0      # at most one arrival greeting per 5 minutes
WHO_EVERY = 2.0             # seconds between face matches while someone is there


# ---------------------------------------------------------------------------
# Who's there, over time (no camera in here: easy to test)
# ---------------------------------------------------------------------------
class Tracker:
    """Turns "a face this check / none" into arrivals and absences."""

    def __init__(self, now=None):
        self.started = time.monotonic() if now is None else now
        self.present = False
        self.last_seen = None      # when a face was last in view
        self.left_at = None

    def update(self, seen, now):
        """Returns ("arrived", gap_seconds or None) or None."""
        event = None
        if seen:
            if not self.present:
                gap = None if self.last_seen is None else now - self.last_seen
                event = ("arrived", gap)
                self.present = True
            self.last_seen = now
        elif self.present and self.last_seen is not None and now - self.last_seen >= ABSENT_AFTER:
            self.present = False
            self.left_at = self.last_seen
        return event

    def nobody_for(self, now):
        """Seconds with nobody in view (0 while someone is)."""
        if self.present:
            return 0.0
        since = self.last_seen if self.last_seen is not None else self.started
        return max(0.0, now - since)


def gaze_from(box, width, height):
    """A face's box in the picture -> where the portrait should look,
    x and y in -1..1 (x towards the screen's right, y up). The camera
    faces you, so the picture is mirrored: a face on the picture's left
    is on the screen's right as she sees it."""
    x, y, w, h = box
    cx, cy = (x + w / 2) / width, (y + h / 2) / height
    clamp = lambda v: max(-1.0, min(1.0, v))
    # webcams sit above the screen: someone centred in the picture is a
    # little below her eye line, so y is lifted a touch
    return {"x": round(clamp((0.5 - cx) * 2.2), 3), "y": round(clamp((0.45 - cy) * 1.6), 3)}


# ---------------------------------------------------------------------------
# State shared with the rest of Luna
# ---------------------------------------------------------------------------
_state = {"thread": None, "stop": threading.Event(), "model": None, "frame": None, "frame_at": 0.0,
          "box": None, "size": (0, 0), "who": None, "who_at": 0.0, "who_score": 0.0, "greeted_at": -1e9,
          "error": "", "detector": "", "enroll": None, "checks": 0, "first": None}
_tracker = Tracker()
_lock = threading.Lock()


def running():
    thread = _state["thread"]
    return bool(thread and thread.is_alive())


def present():
    return running() and _tracker.present


def nobody_here():
    """True when presence is on, quiet is on and nobody has been in view for
    quiet_after_minutes. False whenever we can't tell (presence off)."""
    if not running() or not getattr(config, "PRESENCE_QUIET", True):
        return False
    return _tracker.nobody_for(time.monotonic()) >= float(getattr(config, "PRESENCE_QUIET_AFTER", 5)) * 60


def who():
    """The recognised person in view, or None (nobody, a stranger, or no
    face prints to compare with)."""
    return _state["who"] if present() else None


def gaze():
    """{"x", "y"} towards the face in view, or None."""
    if not present() or not getattr(config, "PRESENCE_LOOK", True):
        return None
    with _lock:
        box, (w, h) = _state["box"], _state["size"]
    return gaze_from(box, w, h) if box and w and h else None


def frame(max_age=2.0):
    """The latest picture (BGR array) if fresh, for look_at_camera."""
    with _lock:
        if _state["frame"] is not None and time.monotonic() - _state["frame_at"] <= max_age:
            return _state["frame"].copy()
    return None


def status():
    """A few lines for /presence."""
    if not running():
        return [f"Presence: off{' (' + _state['error'] + ')' if _state['error'] else ''}. "
                "/presence on, or camera.presence.enabled in the settings pane."]
    now = time.monotonic()
    lines = [f"Presence: on, {_state['detector'] or 'starting'}, {_state['checks']} checks so far"]
    if _tracker.present:
        name = _state["who"]
        lines.append(f"  someone is here{': ' + name + ' (%.2f)' % _state['who_score'] if name else ''}")
    else:
        lines.append(f"  nobody in view for {int(_tracker.nobody_for(now))} s"
                     + (" - she's keeping quiet" if nobody_here() else ""))
    if _state["error"]:
        lines.append(f"  {_state['error']}")
    return lines


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
def _model(kind):
    """The model file, fetched once. None if it can't be had."""
    name, urls, min_size = MODELS[kind]
    path = os.path.join(MODEL_DIR, name)
    if os.path.isfile(path) and os.path.getsize(path) >= min_size:
        return path
    os.makedirs(MODEL_DIR, exist_ok=True)
    for url in urls:
        tmp = path + ".part"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Luna"})
            with urllib.request.urlopen(req, timeout=60) as resp, open(tmp, "wb") as out:
                while True:
                    chunk = resp.read(1 << 16)
                    if not chunk:
                        break
                    out.write(chunk)
            if os.path.getsize(tmp) >= min_size:
                os.replace(tmp, path)
                logbook.info("presence", "fetched %s", name)
                return path
        except Exception as e:
            logbook.warn("presence", "couldn't fetch %s from %s: %s", name, url, e)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
    return None


_faces = {}


def _faces_for(cv2):
    """One _Faces for the whole run: /presence off and on again doesn't
    reload or re-fetch the models."""
    if "faces" not in _faces:
        _faces["faces"] = _Faces(cv2)
    return _faces["faces"]


class _Faces:
    """Face finding (YuNet, or Haar until YuNet is here) and face prints."""

    def __init__(self, cv2):
        self.cv2 = cv2
        self.yunet = None
        self.sface = None
        self.haar = None
        self.size = None
        try:
            # OpenCV 5 dropped the Haar detector; 4.x has it built in
            self.haar = cv2.CascadeClassifier(os.path.join(cv2.data.haarcascades,
                                                           "haarcascade_frontalface_default.xml"))
            if self.haar.empty():
                self.haar = None
        except Exception:
            self.haar = None
        threading.Thread(target=self._fetch, daemon=True, name="presence-models").start()

    def _fetch(self):
        """Load both models, fetching them first if needed; offline, try
        again every 10 minutes."""
        for attempt in range(48):
            if attempt:
                time.sleep(600)
            if self.yunet is None and (path := _model("detect")):
                try:
                    self.yunet = self.cv2.FaceDetectorYN.create(path, "", (WIDTH, 360), 0.8)
                except Exception as e:
                    logbook.warn("presence", "YuNet didn't load: %s", e)
                    return
            if self.sface is None and (path := _model("recognise")):
                try:
                    self.sface = self.cv2.FaceRecognizerSF.create(path, "")
                except Exception as e:
                    logbook.warn("presence", "SFace didn't load: %s", e)
                    return
            if self.yunet is not None and self.sface is not None:
                return

    def name(self):
        if self.yunet is not None:
            return "YuNet" + ("" if self.sface is not None else " (no face prints: SFace missing)")
        return "Haar (fetching YuNet)" if self.haar is not None else "waiting for the face model to download"

    def find(self, img):
        """[(x, y, w, h, row)] largest first; row is YuNet's (for prints) or None."""
        h, w = img.shape[:2]
        if self.yunet is not None:
            if self.size != (w, h):
                self.yunet.setInputSize((w, h))
                self.size = (w, h)
            _ok, rows = self.yunet.detect(img)
            faces = [(*map(float, r[:4]), r) for r in (rows if rows is not None else [])]
        elif self.haar is not None:
            gray = self.cv2.cvtColor(img, self.cv2.COLOR_BGR2GRAY)
            rects = self.haar.detectMultiScale(gray, 1.15, 6, minSize=(48, 48))
            faces = [(float(x), float(y), float(fw), float(fh), None) for x, y, fw, fh in rects]
        else:
            faces = []
        return sorted(faces, key=lambda f: f[2] * f[3], reverse=True)

    def print_of(self, img, row):
        """128 numbers for this face, or None without YuNet + SFace."""
        if self.sface is None or row is None:
            return None
        aligned = self.sface.alignCrop(img, row)
        return [float(v) for v in self.sface.feature(aligned).flatten()]


# ---------------------------------------------------------------------------
# The loop
# ---------------------------------------------------------------------------
def set_model(model):
    """The model greetings are written with (main.py hands it over at startup)."""
    _state["model"] = model


def start(model=None):
    """Start watching (once). False with a reason in status() if it can't."""
    if model is not None:
        _state["model"] = model
    if running():
        return True
    import camera

    cv2 = camera._cv2()
    if cv2 is None:
        _state["error"] = "OpenCV isn't installed - pip install opencv-python-headless"
        return False
    if camera._is_http(camera._device()):
        _state["error"] = "presence needs a webcam on this machine, not a camera server"
        return False
    _state["stop"] = threading.Event()
    _state["error"] = ""
    _state["thread"] = threading.Thread(target=_loop, args=(cv2, _state["stop"]), daemon=True, name="presence")
    _state["thread"].start()
    return True


def stop():
    _state["stop"].set()
    thread = _state["thread"]
    if thread and thread.is_alive():
        thread.join(timeout=3)
    _state["thread"] = None
    _tracker.present = False


def _loop(cv2, stopping):
    import camera

    faces = _faces_for(cv2)
    cap = None
    try:
        with camera._lock:
            # full size, so look_at_camera's picture is as sharp as its own;
            # faces are looked for in a WIDTH-wide copy
            cap = camera._open(cv2, camera._device(), int(getattr(config, "CAMERA_WIDTH", 1280)))
        if not cap.isOpened():
            _state["error"] = f"couldn't open camera {camera._device()}." + camera._hint()
            return
        logbook.info("presence", "watching camera %s", camera._device())
        while not stopping.is_set():
            began = time.monotonic()
            ok, img = cap.read()
            if not ok or img is None:
                _state["error"] = "the camera stopped sending pictures"
                stopping.wait(2)
                continue
            full = img
            h, w = img.shape[:2]
            if w > WIDTH:
                img = cv2.resize(img, (WIDTH, int(h * WIDTH / w)), interpolation=cv2.INTER_AREA)
                h, w = img.shape[:2]
            found = faces.find(img)
            _state["detector"] = faces.name()
            _state["checks"] += 1
            now = time.monotonic()
            with _lock:
                _state["frame"], _state["frame_at"] = full, now
                _state["size"] = (w, h)
                _state["box"] = found[0][:4] if found else None
            event = _tracker.update(bool(found), now)
            if found:
                _recognise(faces, img, found[0], now, force=event is not None)
                _enrolling(faces, img, found[0])
            if event and event[0] == "arrived":
                _arrived(event[1])
            wait = 1.0 / max(0.5, min(15.0, float(getattr(config, "PRESENCE_FPS", 3))))
            stopping.wait(max(0.0, wait - (time.monotonic() - began)))
    except Exception as e:
        _state["error"] = f"stopped: {e}"
        logbook.exception("presence", "presence loop failed")
    finally:
        if cap is not None:
            cap.release()
        _tracker.present = False


def _recognise(faces, img, face, now, force=False):
    if not getattr(config, "PRESENCE_RECOGNISE", True):
        _state["who"] = None
        return
    if not force and now - _state["who_at"] < WHO_EVERY:
        return
    vector = faces.print_of(img, face[4])
    if vector is None:
        return
    import people

    name, score = people.match("face", vector, float(getattr(config, "PRESENCE_MATCH", 0.36)))
    _state["who"], _state["who_score"], _state["who_at"] = name, score, now


# ---------------------------------------------------------------------------
# Enrolling a face
# ---------------------------------------------------------------------------
def enroll(name, shots=10, seconds=20):
    """Take `shots` face prints of whoever is in front of the camera and
    store them under name. Returns (ok, message). Starts presence for the
    time it takes if it's off."""
    was_running = running()
    if not was_running and not start():
        return False, _state["error"] or "couldn't start the camera"
    job = {"name": name, "need": shots, "got": [], "done": threading.Event(), "last": 0.0}
    _state["enroll"] = job
    try:
        job["done"].wait(seconds)
    finally:
        _state["enroll"] = None
        if not was_running:
            stop()
    if not job["got"]:
        return False, ("no face prints taken: the face model isn't here yet (it downloads on first use), "
                       "or no face was in view. Look at the camera and try again.")
    import people

    total = people.add_prints(name, "face", job["got"])
    return True, f"{name}: {len(job['got'])} face prints taken ({total} stored)."


def _enrolling(faces, img, face):
    job = _state["enroll"]
    now = time.monotonic()
    if not job or now - job["last"] < 0.4:
        return
    vector = faces.print_of(img, face[4])
    if vector is None:
        return
    job["got"].append(vector)
    job["last"] = now
    if len(job["got"]) >= job["need"]:
        job["done"].set()


# ---------------------------------------------------------------------------
# Saying hi
# ---------------------------------------------------------------------------
def _when(gap):
    minutes = gap / 60
    if minutes < 90:
        return f"about {int(round(minutes))} minutes"
    if minutes < 60 * 20:
        return f"about {int(round(minutes / 60))} hours"
    return f"about {int(round(minutes / 1440))} days"


def on_first_arrival(callback):
    """Run callback (in its own thread) when someone first comes into view:
    the startup greeting, held until there's someone to greet."""
    _state["first"] = callback


def _run_quietly(callback):
    try:
        callback()
    except Exception as e:      # an Interrupted greeting, a model gone: never a traceback in the TUI
        logbook.info("presence", "held greeting didn't run: %s", e)


def _arrived(gap):
    """Someone came into view after `gap` seconds (None: first sight since
    Luna started, which the startup greeting covers)."""
    if gap is None:
        callback, _state["first"] = _state["first"], None
        if callback is not None:
            threading.Thread(target=_run_quietly, args=(callback,), daemon=True, name="presence-first").start()
        return
    if not getattr(config, "PRESENCE_GREET", True):
        return
    try:
        import reflect

        # talking to her from across the room, out of the camera's view,
        # isn't being away: count from the last turn too
        gap = min(gap, reflect.idle_seconds())
    except Exception:
        pass
    if gap < float(getattr(config, "PRESENCE_GREET_AFTER", 20)) * 60:
        return
    now = time.monotonic()
    if now - _state["greeted_at"] < GREET_COOLDOWN or not _state["model"]:
        return
    _state["greeted_at"] = now
    threading.Thread(target=_greet, args=(gap,), daemon=True, name="presence-greet").start()


def _greet(gap):
    time.sleep(1.5)                       # a moment to settle, and to see who it is
    try:
        import assistant
        import interrupts
        import mood

        if assistant.busy() or interrupts.recording() or mood.away():
            return
        if not assistant._turn.acquire(blocking=False):
            return
    except Exception:
        return
    import history
    import llm
    import ui
    from speech import speak

    name = _state["who"] if _tracker.present else None
    person = name or getattr(config, "USER", "the user")
    try:
        with interrupts.using(kind="greeting") as stopper:
            assistant._hold(stopper)
            trigger = (f"(Not words from anyone: {person} just came back and is in front of you again, "
                       f"after being away {_when(gap)}. Greet them in one short line, in your own voice "
                       "and your current mood. Don't ask where they were unless you want to.)")
            ui.set_status("Saying hi...")
            answer = llm.ask(trigger, _state["model"], remember=False, source="greeting")
            if answer.strip():
                ui.add_message(config.AGENT_NAME.lower(), answer)
                history.add_message("user", f"({person} came back after {_when(gap)})")
                history.add_message("assistant", answer)
                history.save()
                if not stopper.speaking.is_set():
                    ui.set_status("Speaking...")
                    speak(answer)
    except Exception as e:
        logbook.warn("presence", "greeting failed: %s", e)
    finally:
        assistant._hold(None)
        assistant._turn.release()
        try:
            ui.set_status("Idle")
        except Exception:
            pass
