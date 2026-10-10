"""Letting Luna see through the webcam: one picture, when you ask.

    > "What am I holding?"
    > "Read this label for me."
    > "Luna, look at this."

look_at_camera grabs a single frame and hands it over the same way
look_at_screen does (vision._pending, attached to the next message).
There's no stream and nothing is saved: the frame lives in memory for
one turn and goes only to the local model.

Off until you switch it on in the tools pane (Tab twice, Camera group).
It's an opt-in tool, so a fresh install never offers it, and it's never
offered on a Discord turn, a scheduled job or stream chat, so nobody
but you at the keyboard can ask her to look.

OpenCV does the capture on all three systems: V4L2 on Linux,
AVFoundation on macOS, Media Foundation / DirectShow on Windows.

    pip install opencv-python-headless       (installer: --extras camera)

    "camera": { "device": 0, "width": 1280, "warmup": 5 }
"""
import base64
import sys
import threading

import config
import logbook

_lock = threading.Lock()
last_error = ""


def _cv2():
    try:
        import cv2

        return cv2
    except Exception:
        return None


def _remote_or_job():
    """A turn that didn't come from you at the keyboard."""
    try:
        import state

        return bool(getattr(state.remote, "source", None) or getattr(state.job, "name", None))
    except Exception:
        return False


def available():
    if _cv2() is None or _remote_or_job():
        return False

    try:
        import vision

        return not vision._model_is_blind()
    except Exception:
        return True


def why_unavailable():
    if _cv2() is None:
        return "OpenCV isn't installed - pip install opencv-python-headless"

    if _remote_or_job():
        return "only for turns typed or spoken at the desk"

    try:
        import vision

        if vision._model_is_blind():
            return vision.why_unavailable()
    except Exception:
        pass

    return ""


def _open(cv2, device):
    """VideoCapture on the backend that opens fastest here. Windows'
    default (Media Foundation) can take seconds; DirectShow doesn't."""
    if sys.platform == "win32":
        cap = cv2.VideoCapture(device, cv2.CAP_DSHOW)

        if cap.isOpened():
            return cap

        cap.release()

    return cv2.VideoCapture(device)


def _hint():
    if sys.platform == "darwin":
        return (" On a Mac, allow the camera for the terminal Luna runs in: System Settings > "
                "Privacy & Security > Camera, then restart Luna.")

    if sys.platform == "win32":
        return (" On Windows, check Settings > Privacy > Camera > Let desktop apps access "
                "your camera, and that nothing else (OBS, Discord) is using it.")

    return " Check that something else isn't using it, and that you're in the video group."


def grab(device=None):
    """(jpeg bytes, description) or (None, error). One frame, after a few
    thrown away so auto-exposure has settled - the first frame from most
    webcams is nearly black."""
    global last_error
    cv2 = _cv2()

    if cv2 is None:
        last_error = why_unavailable()
        return None, last_error

    device = int(getattr(config, "CAMERA_DEVICE", 0) if device is None else device)
    width = int(getattr(config, "CAMERA_WIDTH", 1280))
    warmup = max(0, int(getattr(config, "CAMERA_WARMUP", 5)))

    with _lock:
        cap = _open(cv2, device)

        try:
            if not cap.isOpened():
                last_error = f"couldn't open camera {device}." + _hint()
                return None, last_error

            frame = None

            for _ in range(warmup + 1):
                ok, got = cap.read()

                if ok and got is not None:
                    frame = got

            if frame is None:
                last_error = f"camera {device} opened but sent no picture." + _hint()
                return None, last_error
        finally:
            cap.release()

    h, w = frame.shape[:2]

    if width and w > width:
        frame = cv2.resize(frame, (width, int(h * width / w)), interpolation=cv2.INTER_AREA)
        h, w = frame.shape[:2]

    ok, jpeg = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])

    if not ok:
        last_error = "couldn't encode the picture"
        return None, last_error

    data = jpeg.tobytes()

    if float(frame.mean()) < 8:
        logbook.info("camera", "frame from %d is nearly black", device)

    last_error = ""
    return data, f"camera {device}, {w}x{h}, {len(data) // 1024}KB"


def capture(device=None):
    """Grab a frame and stash it for the next message, like a screenshot.
    (data_url, description) or (None, error)."""
    data, what = grab(device)

    if data is None:
        return None, what

    import vision

    url = "data:image/jpeg;base64," + base64.b64encode(data).decode()
    vision.stash(url, "the camera picture")

    try:
        import ui

        ui.add_message("system", f"Camera: took one picture ({what}), not saved")
    except Exception:
        pass

    logbook.info("camera", "took a picture: %s", what)
    return url, what


def cameras(limit=6):
    """[(index, 'WxH')] for each camera index that opens. Slow-ish: each
    probe opens the device, so this is for /camera list, not every turn."""
    cv2 = _cv2()

    if cv2 is None:
        return []

    found = []

    with _lock:
        for i in range(limit):
            cap = _open(cv2, i)

            try:
                if cap.isOpened():
                    ok, frame = cap.read()
                    size = f"{frame.shape[1]}x{frame.shape[0]}" if ok and frame is not None else "no picture"
                    found.append((i, size))
            finally:
                cap.release()

    return found
