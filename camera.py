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

"device" is any of:

    0, 1, ...                 a webcam on this machine, by number
    "/dev/video2"             (Linux) a webcam by its device file
    "http://host:8080/..."    a webcam server: a snapshot URL that returns
                              one JPEG, or an MJPEG stream - read straight
                              over HTTP, no OpenCV needed
    "rtsp://host/stream"      an RTSP camera or server (OpenCV's FFmpeg)

A local webcam goes through OpenCV on all three systems: V4L2 on Linux
(asked for MJPEG, which is what most USB webcams need to give a large
picture), AVFoundation on macOS, DirectShow / Media Foundation on
Windows.

    pip install opencv-python-headless       (installer: --extras camera)

    "camera": { "device": 0, "width": 1280, "warmup": 5 }
"""
import base64
import glob
import re
import sys
import threading
import urllib.request

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


def _device():
    """The configured camera: an int, a /dev path or a URL."""
    raw = getattr(config, "CAMERA_DEVICE", 0)

    if isinstance(raw, str) and raw.strip().lstrip("-").isdigit():
        return int(raw.strip())

    return raw.strip() if isinstance(raw, str) else int(raw)


def _is_http(device):
    return isinstance(device, str) and re.match(r"(?i)^https?://", device) is not None


def available():
    if _remote_or_job():
        return False

    if _cv2() is None and not _is_http(_device()):
        return False

    try:
        import vision

        return not vision._model_is_blind()
    except Exception:
        return True


def why_unavailable():
    if _cv2() is None and not _is_http(_device()):
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


def _open(cv2, device, width=1280):
    """VideoCapture on the backend that behaves best here.

    Windows' default (Media Foundation) can take seconds; DirectShow
    doesn't. Linux gets V4L2 by name - left to choose, OpenCV can pick
    GStreamer and hang - and MJPEG: most USB webcams only manage a large
    picture compressed, and uncompressed at 1280 wide they send garbage
    or nothing."""
    if isinstance(device, str) and "://" in device:
        return cv2.VideoCapture(device, cv2.CAP_FFMPEG)

    if sys.platform == "win32":
        cap = cv2.VideoCapture(device, cv2.CAP_DSHOW)

        if cap.isOpened():
            return cap

        cap.release()

    if sys.platform.startswith("linux"):
        cap = cv2.VideoCapture(device, cv2.CAP_V4L2)

        if cap.isOpened():
            try:
                cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
                if width:
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            except Exception:
                pass

            return cap

        cap.release()

    return cv2.VideoCapture(device)


def _grab_http(url, timeout=8):
    """One JPEG from a webcam server: a snapshot URL answers with the
    image itself, an MJPEG stream with an endless run of them - read
    until the first whole one and hang up."""
    # user:password@ in the URL (most camera servers) becomes Basic auth:
    # urllib won't take it from the URL itself.
    from urllib.parse import unquote, urlsplit, urlunsplit

    parts = urlsplit(url)
    headers = {"User-Agent": "Luna"}

    if parts.username is not None:
        token = base64.b64encode(f"{unquote(parts.username)}:{unquote(parts.password or '')}".encode()).decode()
        headers["Authorization"] = "Basic " + token
        host = parts.hostname + (f":{parts.port}" if parts.port else "")
        url = urlunsplit((parts.scheme, host, parts.path, parts.query, parts.fragment))

    req = urllib.request.Request(url, headers=headers)

    with urllib.request.urlopen(req, timeout=timeout) as resp:
        kind = (resp.headers.get("Content-Type") or "").lower()

        if kind.startswith("image/"):
            return resp.read(20_000_000)

        buf = b""

        while len(buf) < 20_000_000:
            chunk = resp.read(65536)

            if not chunk:
                break

            buf += chunk
            start = buf.find(b"\xff\xd8")
            end = buf.find(b"\xff\xd9", start + 2) if start >= 0 else -1

            if start >= 0 and end >= 0:
                return buf[start:end + 2]

    raise ValueError(f"no picture in the answer ({kind or 'no content type'})")


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
    device = _device() if device is None else device
    width = int(getattr(config, "CAMERA_WIDTH", 1280))
    warmup = max(0, int(getattr(config, "CAMERA_WARMUP", 5)))

    if _is_http(device):
        return _grab_url(cv2, device, width)

    if cv2 is None:
        last_error = why_unavailable()
        return None, last_error

    with _lock:
        cap = _open(cv2, device, width)

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


def _grab_url(cv2, url, width):
    """A webcam server's picture, scaled down if OpenCV is here to do it."""
    global last_error
    where = re.sub(r"//[^/@]*@", "//", url)   # never echo a password in the URL

    try:
        data = _grab_http(url)
    except Exception as e:
        last_error = f"couldn't get a picture from {where}: {e}"
        return None, last_error

    size = ""

    if cv2 is not None:
        try:
            import numpy as np

            frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
            h, w = frame.shape[:2]

            if width and w > width:
                frame = cv2.resize(frame, (width, int(h * width / w)), interpolation=cv2.INTER_AREA)
                ok, jpeg = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
                if ok:
                    data = jpeg.tobytes()
                h, w = frame.shape[:2]

            size = f", {w}x{h}"
        except Exception:
            pass

    last_error = ""
    return data, f"camera server {where}{size}, {len(data) // 1024}KB"


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
    """[(index, 'WxH')] for each camera that opens. Slow-ish: each probe
    opens the device, so this is for /camera list, not every turn. On
    Linux the /dev/video* files are what's there - one webcam often has
    two, and only one of them gives pictures."""
    cv2 = _cv2()

    if cv2 is None:
        return []

    found = []
    candidates = list(range(limit))

    if sys.platform.startswith("linux"):
        nodes = sorted(glob.glob("/dev/video*"), key=lambda p: int(re.sub(r"\D", "", p) or 0))
        candidates = [int(re.sub(r"\D", "", p)) for p in nodes] or candidates

    with _lock:
        for i in candidates:
            cap = _open(cv2, i)

            try:
                if cap.isOpened():
                    ok, frame = cap.read()
                    size = f"{frame.shape[1]}x{frame.shape[0]}" if ok and frame is not None else "no picture"
                    found.append((i, size))
            finally:
                cap.release()

    return found
