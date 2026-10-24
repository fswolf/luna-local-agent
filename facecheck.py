"""One quick look at the desk: who's typing, or who's talking when her
voice match isn't sure. For when presence (presence.py) isn't watching;
while it is, it already knows the face and nothing here opens the camera.

    "people": { "face_check": true, "face_check_minutes": 10, "face_check_seconds": 2 }

Off by default. When on:

- a typed turn, or a spoken one whose voice score lands just under
  people.voice_match (GREY), asks check()
- check() takes one frame (camera.frame), finds the biggest face with
  presence's YuNet, makes its print with SFace and matches it against
  the enrolled face prints (people.match)
- the answer counts for face_check_minutes while the conversation keeps
  going; after GAP with no turns (someone could have sat down) the next
  turn looks again. Most turns cost nothing

Nothing is saved and nothing is sent: the frame lives for one match and
goes nowhere, not even to the model.

## It never gets in the way

The face check is an extra. Whatever goes wrong, check() returns None
("couldn't check") and the turn goes on exactly as it would without it:

- OpenCV, the face models and the camera are all optional and looked up
  when needed, inside try
- the look runs on its own thread with a deadline (face_check_seconds);
  past it the turn carries on without an answer, and a camera that hangs
  doesn't start a second look on top of the first
- on a spoken turn the look starts as soon as the voice match is in,
  while Whisper is still transcribing (assistant._whose_voice), so it
  mostly costs no time; a turn that finds a look already under way waits
  for that one instead of opening the camera again
- a failed look waits a minute before the next one; FAILS_TO_PAUSE in a
  row pauses the check for the session, said once in the chat and the
  logbook, not on every turn ("/people check" tries again)
- a frame with no face in it, or too dark to see, is an answer ("nobody
  in view"), not a failure; the face models still downloading is neither
"""
import threading
import time

import config
import logbook

GREY = 0.1               # a voice score this far under people.voice_match counts as "not sure"
FAILS_TO_PAUSE = 3       # failed looks in a row before it pauses itself
RETRY_AFTER = 60.0       # seconds after a failed look before the next
LOADING_RETRY = 20.0     # seconds to wait while the face models download
GAP = 300.0              # seconds without a turn after which a look is stale anyway
NOT_OWNER_EVERY = 120.0  # someone other than the owner is looked at again sooner, so the
                         # owner coming back isn't treated as a guest for long
LOADING_GIVE_UP = 600.0  # face models still missing after this long: a failure, not a wait
DARK = 8                 # a frame this dark (0-255 average) shows nobody

_lock = threading.Lock()
_state = {"busy": False, "inflight": None, "started": 0.0, "at": None, "turn_at": None,
          "name": None, "score": None, "what": "", "fails": 0, "retry_at": 0.0,
          "loading_since": None, "paused": "", "last_error": "", "said": ""}


def enabled():
    return bool(getattr(config, "PEOPLE_FACE_CHECK", False))


def _every():
    try:
        return max(0.0, float(getattr(config, "PEOPLE_FACE_CHECK_MINUTES", 10))) * 60.0
    except (TypeError, ValueError):
        return 600.0


def _budget():
    try:
        return max(0.2, min(15.0, float(getattr(config, "PEOPLE_FACE_CHECK_SECONDS", 2))))
    except (TypeError, ValueError):
        return 2.0


def _fresh_for(name):
    """How long a look's answer holds: the full face_check_minutes for the
    owner (or nobody), less for anyone else."""
    try:
        import people

        if name and not people.is_owner(name):
            return min(_every(), NOT_OWNER_EVERY)
    except Exception:
        pass
    return _every()


def unsure(voice_score):
    """Is this voice score in the grey zone just under people.voice_match?"""
    try:
        line = float(getattr(config, "PEOPLE_VOICE_MATCH", 0.3))
        return line - GREY <= float(voice_score) < line
    except (TypeError, ValueError):
        return False


def why_not():
    """'' when a look could run now, else the reason (for /people and the logbook)."""
    if not enabled():
        return "off (people.face_check)"
    if _state["paused"]:
        return f"paused after {FAILS_TO_PAUSE} failed looks ({_state['paused']}); /people check tries again"
    try:
        import camera

        if camera._cv2() is None:
            return "OpenCV isn't installed - pip install opencv-python-headless"
    except Exception as e:
        return f"the camera module didn't load ({e})"
    try:
        import people

        if not any(p.get("face") for p in people.everyone().values()):
            return "nobody has face prints yet (/people enroll face <name>)"
    except Exception as e:
        return f"couldn't read the people folder ({e})"
    return ""


def warm():
    """Start the face models loading (a background download the first
    time), so the first check doesn't find them missing. Quiet on failure."""
    if not enabled():
        return
    try:
        import camera
        import presence

        cv2 = camera._cv2()
        if cv2 is not None:
            presence._faces_for(cv2)
    except Exception as e:
        logbook.info("facecheck", "couldn't start the face models: %s", e)


def check(reason="turn", force=False, fresh=False):
    """Who's at the desk: a name, people.STRANGER (a face that clearly
    isn't the owner's), or None (the owner, nobody there, can't place
    them, or couldn't check). fresh: don't reuse the last answer (a
    voice just said it's someone else); paused and back-off still hold.
    Never raises."""
    try:
        return _check(reason, force, fresh)
    except Exception as e:                      # a bug here must not cost a turn
        logbook.exception("facecheck", "face check failed")
        _failed(f"{type(e).__name__}: {e}")
        return None


def _remote_or_job():
    try:
        import turnctx

        turn = turnctx.current()
        return bool(turn.remote or turn.job)
    except Exception:
        return False


def _check(reason, force, fresh=False):
    if not enabled() or _remote_or_job():
        return None
    try:
        import presence

        if presence.running():                  # already watching: it knows
            return presence.verdict()
    except Exception:
        pass

    now = time.monotonic()
    with _lock:
        quiet = _state["turn_at"] is None or now - _state["turn_at"] >= GAP
        _state["turn_at"] = now
        if force:
            _state["paused"], _state["fails"], _state["retry_at"] = "", 0, 0.0
        elif (_state["at"] is not None and not quiet and not fresh
              and now - _state["at"] < _fresh_for(_state["name"])):
            return _state["name"]               # still fresh, same conversation
        inflight = _state["inflight"] if _state["busy"] else None
        if inflight is None:
            if now < _state["retry_at"]:
                return None
            why = why_not()
            if why:
                if why != _state["said"]:       # once, not every turn
                    _state["said"] = why
                    logbook.info("facecheck", "not looking: %s", why)
                if enabled() and not _state["paused"]:
                    _state["retry_at"] = now + RETRY_AFTER   # don't reread the people folder every turn
                return None
            out = {"done": threading.Event()}
            _state.update(busy=True, inflight=out, started=now)

    if inflight is not None:
        # a look is already under way (started alongside transcription, say):
        # wait for it rather than open the camera twice
        # only for what's left of its budget: a look stuck in the driver
        # mustn't cost every later turn the full wait
        left = max(0.0, _state["started"] + _budget() - time.monotonic())
        if inflight["done"].wait(left) and not inflight.get("error") and not inflight.get("loading"):
            return inflight.get("name")
        return None

    worker = threading.Thread(target=_look, args=(out,), daemon=True, name="facecheck")
    try:
        worker.start()
    except Exception as e:
        _state.update(busy=False, inflight=None)
        _failed(f"couldn't start a thread ({e})")
        return None

    if not out["done"].wait(_budget()):
        # the worker is still out there (a camera can hang in its driver);
        # it clears busy when it finally returns, so looks don't pile up
        _failed(f"the camera took longer than {_budget():g} s")
        return None

    if out.get("loading"):
        since = _state["loading_since"] = _state["loading_since"] or time.monotonic()
        if time.monotonic() - since > LOADING_GIVE_UP:
            _state["loading_since"] = None
            _failed(f"the face models didn't load ({out['loading']})")
            return None
        _state["retry_at"] = time.monotonic() + LOADING_RETRY
        logbook.info("facecheck", "the face models are still loading")
        return None
    if out.get("error"):
        _failed(out["error"])
        return None

    name, score = out.get("name"), out.get("score")
    with _lock:
        _state.update(at=time.monotonic(), name=name, score=score, what=out.get("what", ""),
                      fails=0, last_error="", said="", loading_since=None)
    logbook.info("facecheck", "checked (%s): %s", reason, out.get("what", "?"))
    return name


def _look(out):
    """One frame, the biggest face, its print, the best match. Runs on its
    own thread; everything it finds goes into out."""
    try:
        import camera
        import people
        import presence

        cv2 = camera._cv2()
        if cv2 is None:
            out["error"] = "OpenCV isn't installed"
            return
        faces = presence._faces_for(cv2)
        if faces.yunet is None or faces.sface is None:
            out["loading"] = faces.name()
            return
        img, what = camera.frame(width=presence.WIDTH)   # small: quicker to open and to read
        if img is None:
            out["error"] = what or "no picture"
            return
        if float(img.mean()) < DARK:
            out.update(name=None, score=None, what="too dark to see anyone")
            return
        h, w = img.shape[:2]
        if w > presence.WIDTH:
            img = cv2.resize(img, (presence.WIDTH, int(h * presence.WIDTH / w)), interpolation=cv2.INTER_AREA)
        found = faces.find(img)
        if not found:
            out.update(name=None, score=None, what="nobody in view")
            return
        vector = faces.print_of(img, found[0][4])
        if vector is None:
            out["loading"] = faces.name()
            return
        name, score = people.verdict("face", vector, float(getattr(config, "PRESENCE_MATCH", 0.36)))
        if name == people.STRANGER:
            what = f"someone who isn't {getattr(config, 'USER_NAME', '') or 'the owner'} ({score:.2f})"
        elif name:
            what = f"{name} ({score:.2f})"
        else:
            what = f"a face she can't place ({score:.2f})"
        out.update(name=name, score=score, what=what)
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
    finally:
        _state.update(busy=False, inflight=None)
        out["done"].set()


def _failed(error):
    with _lock:
        _state["fails"] += 1
        _state["last_error"] = str(error)[:200]
        _state["retry_at"] = time.monotonic() + RETRY_AFTER
        pause = _state["fails"] >= FAILS_TO_PAUSE and not _state["paused"]
        if pause:
            _state["paused"] = _state["last_error"]
    logbook.warn("facecheck", "look failed (%d in a row): %s", _state["fails"], error)
    if pause:
        logbook.warn("facecheck", "paused for this session")
        try:
            import ui

            ui.add_message("system", f"Face check paused: {_state['paused']}. /people check tries again.")
        except Exception:
            pass


def status():
    """One line for /people."""
    if not enabled():
        return "Face check: off (people.face_check)"
    try:
        import presence

        if presence.running():
            return "Face check: on, not needed while presence is watching"
    except Exception:
        pass
    why = why_not()
    if why:
        return f"Face check: {why}"
    if _state["busy"] and time.monotonic() - _state["started"] > 30:
        return (f"Face check: a look has been stuck in the camera for "
                f"{int(time.monotonic() - _state['started'])} s (the driver isn't answering)")
    if _state["at"] is None:
        last = "no look yet"
    else:
        ago = int((time.monotonic() - _state["at"]) // 60)
        last = f"last look {ago} min ago: {_state['what']}"
    error = f"; last failure: {_state['last_error']}" if _state["fails"] else ""
    return f"Face check: on, {last}{error}"


def forget_last():
    """Drop the cached answer (someone was just met): the next turn looks again."""
    with _lock:
        _state.update(at=None, name=None, score=None)


def reset():
    """Forget the last look and any pause (tests, /people check)."""
    with _lock:
        _state.update(busy=False, inflight=None, started=0.0, at=None, turn_at=None, name=None,
                      score=None, what="", fails=0, retry_at=0.0, loading_since=None, paused="",
                      last_error="", said="")
