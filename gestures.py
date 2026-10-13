"""What sets off the 3D portrait's gestures (portrait/viewer/gestures.js).

portrait.gestures picks how her own replies turn into movement:

  tags      she picks: one hidden tag like [hug] where it fits, cut out
            before anything is shown or spoken. About 60 cached prompt
            tokens and a few output tokens. Keywords as a fallback.
  meaning   the embedding model compares the exchange with a short
            description of each gesture after she answers. One embedding
            call, off the turn's path. Needs the embedding server;
            keywords as a fallback.
  keywords  only *hugs*, *waves*, 🤗 ... in what she writes (the page does it)
  off       none from the conversation (idle moves and chat still work)

Chat triggers (!hug, a viewer's hi) are separate: portrait.chat_gestures.
"""

import os
import re
import threading
import time

import config
import logbook

MODES = ("tags", "meaning", "keywords", "off")
# The built-in gestures are files in portrait/gestures/ (wave.js,
# hug.js...). Each says what it's for ("about"), whether it's private
# (never from stream chat), and so on; read from there, so a new file is a
# new gesture with nothing else to edit.
_GESTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "portrait", "gestures")
_files = {"at": 0.0, "found": {}}


def builtin():
    """{name: {"about": str, "private": bool, "left": bool}} for every gesture file."""
    if time.monotonic() - _files["at"] < 20:
        return _files["found"]
    found = {}
    try:
        names = sorted(f[:-3] for f in os.listdir(_GESTURE_DIR) if f.endswith(".js") and not f.startswith("_"))
    except OSError:
        names = []
    for name in names:
        try:
            with open(os.path.join(_GESTURE_DIR, name + ".js"), encoding="utf-8") as f:
                text = f.read()
        except OSError:
            continue
        about = re.search(r"""^\s*about:\s*(["'])(.*?)\1""", text, re.M)
        found[name] = {"about": about.group(2) if about else "",
                       "private": bool(re.search(r"^\s*private:\s*true", text, re.M)),
                       "left": bool(re.search(r"^\s*left:\s*true", text, re.M))}
    _files.update(at=time.monotonic(), found=found)
    return found


def all_names():
    """Every built-in gesture, left-handed copies included."""
    out = []
    for name, g in builtin().items():
        out.append(name)
        if g["left"]:
            out.append(name + "_left")
    return out


_PARTIAL = re.compile(r"\[([a-z_]{0,24})$", re.IGNORECASE)
_clips = {"at": 0.0, "list": []}


def clips():
    """portrait/animations, re-read at most every 20 seconds, so a clip
    dropped in while she runs shows up without a restart."""
    if time.monotonic() - _clips["at"] > 20:
        try:
            import livefeed

            _clips["list"] = livefeed.portrait_clips()
        except Exception:
            _clips["list"] = []
        _clips["at"] = time.monotonic()
    return _clips["list"]


def names():
    """Every tag that means something: the built-ins and every clip."""
    return tuple(dict.fromkeys(tuple(n for n, g in builtin().items() if g["about"])
                               + tuple(c["name"] for c in clips())))


_tag_cache = {}


def _tag():
    key = names()
    if key not in _tag_cache:
        _tag_cache.clear()
        _tag_cache[key] = re.compile(r"[ \t]*\[(" + "|".join(map(re.escape, key)) + r")\][ \t]?",
                                     re.IGNORECASE)
    return _tag_cache[key]

_turn = {"sent": set()}


def mode():
    m = str(getattr(config, "PORTRAIT_GESTURES", "tags") or "tags").lower()
    return m if m in MODES else "tags"


def _three_d():
    return str(getattr(config, "PORTRAIT_MODEL", "")).lower().endswith((".vrm", ".glb"))


# -- tags ----------------------------------------------------------------
def prompt_line(private=True):
    """The system prompt's line about her body, in tags mode, for a 3D
    model. Empty otherwise, so it costs nothing when it can't be used.
    A clip with an "about" in clips.json is offered too (or describes the
    built-in it replaces); private clips only in your own turns."""
    if mode() != "tags" or not _three_d():
        return ""

    about = {n: g["about"] for n, g in builtin().items() if g["about"] and (private or not g["private"])}
    for c in clips():
        if c.get("about") and (private or not c.get("private")):
            about[c["name"]] = str(c["about"])[:60]

    offered = ", ".join(f"[{n}] ({a})" for n, a in about.items())

    return ("Body: you have an animated 3D body on screen. When a gesture fits what you "
            f"say, put one tag where it happens: {offered}. At most one per reply, most "
            "replies need none. Tags are hidden from the screen and the voice; never "
            "mention them.\n")


def strip(text):
    """Text with gesture tags cut, and a half-written one held back."""
    if "[" in text:
        # a space where it sat between words, nothing before punctuation
        text = _tag().sub("\0", text)
        text = re.sub(r"(?<=\S)\0(?=\w)", " ", text).replace("\0", "")
    partial = _PARTIAL.search(text)

    if partial and any(n.startswith(partial.group(1).lower()) for n in names()):
        text = text[:partial.start()]

    return text


def new_turn():
    _turn["sent"] = set()


def from_tags(answer_text):
    """Send any tag she's written so far, once each per turn. Runs in
    every mode, so a tag never does nothing - but only tags mode asks for
    them."""
    if "[" not in answer_text or mode() == "off":
        return

    for m in _tag().finditer(answer_text):
        # the name as the file spells it (sultryBeckon), whatever case she wrote
        name = next((n for n in names() if n.lower() == m.group(1).lower()), m.group(1))

        if name.lower() not in _turn["sent"]:
            _turn["sent"].add(name.lower())
            _emit(name, "tag")


def _emit(name, src):
    try:
        import livefeed

        livefeed.emit("gesture", name=name, src=src)
    except Exception:
        pass


# -- meaning -------------------------------------------------------------
# What each gesture is for, as the embedding model will see it. "none"
# rows soak up ordinary answers, so a gesture has to beat them, not just
# score high: replies about files, weather and code look alike to an
# embedding model no matter what.
PROTOTYPES = {
    "wave": ["Greeting someone who just arrived: hello, hi, welcome back, good morning.",
             "Saying goodbye: see you later, good night, bye for now."],
    "hug": ["A warm, affectionate moment: I missed you, I love you, you mean a lot to me.",
            "Comforting someone who is sad, hurt or had a rough day."],
    "jump": ["Huge excitement and celebration: we did it, amazing news, that's incredible!"],
    "bounce": ["Playful, giggly, happy and teasing banter; something cute or funny."],
    "shrug": ["Not knowing or not being able to help: I'm not sure, no idea, oh well, it failed."],
    "stretch": ["Feeling sleepy or tired, yawning, just woke up, a long day."],
    "none": ["A factual answer with information, numbers or instructions.",
             "Reporting the result of a task: the file is saved, the command ran, here is the list.",
             "Thinking through a question calmly and explaining something.",
             "A neutral reply in an ordinary conversation."],
}
_INSTRUCT = ("Instruct: Given a moment in a conversation, retrieve the body language "
             "that fits it\nQuery: ")


def _prototypes(private=True):
    """The built-in descriptions above, plus one for every gesture file and
    clip with an "about" line that isn't described already - so a gesture
    you write is matched by meaning too. Private ones only in private turns."""
    protos = {k: list(v) for k, v in PROTOTYPES.items()}
    found = [(n, g["about"], g["private"]) for n, g in builtin().items()]
    found += [(c["name"], str(c.get("about") or ""), bool(c.get("private"))) for c in clips()]
    for name, about, is_private in found:
        if not about or name in protos or (is_private and not private):
            continue
        protos[name] = [f"A moment for the gesture {name.replace('_', ' ')}: {about}."]
    if not private:
        for name in [n for n, g in builtin().items() if g["private"]]:
            protos.pop(name, None)
    return protos


def _scores(text, private=True):
    import embedmem

    if not embedmem.available():
        return None

    protos = _prototypes(private)
    docs = [d for ds in protos.values() for d in ds]
    vecs = embedmem.vectors(docs)

    if not vecs:
        return None

    q = embedmem._embed([_INSTRUCT + text[:600]])[0]

    return {name: max(embedmem.cosine(q, vecs[d]) for d in ds)
            for name, ds in protos.items()}


def classify(text, private=True):
    """(gesture or None, scores). A gesture must beat the best "none" row
    by portrait.meaning_margin."""
    scores = _scores(text, private)

    if not scores:
        return None, None

    margin = float(getattr(config, "PORTRAIT_MEANING_MARGIN", 0.04))
    best = max((n for n in scores if n != "none"), key=scores.get)

    return (best if scores[best] - scores["none"] >= margin else None), scores


def after_reply(said, answer, private=True):
    """In meaning mode: what she just said (and what to), off the turn's
    path. Skipped if she already tagged one."""
    if mode() != "meaning" or not _three_d() or not answer or _turn["sent"]:
        return

    def run():
        try:
            pick, scores = classify(f"They said: {said[:200]}\nShe answered: {answer[:500]}", private)

            if scores:
                logbook.info("gestures", "%s  %s", pick or "-",
                             " ".join(f"{k} {v:.2f}" for k, v in sorted(scores.items(), key=lambda kv: -kv[1])))
            if pick:
                _emit(pick, "meaning")
        except Exception as e:
            logbook.warn("gestures", "meaning check failed: %s", e)

    threading.Thread(target=run, daemon=True).start()
