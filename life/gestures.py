"""What sets off the 3D portrait's gestures (portrait/viewer/gestures.js).

portrait.gestures picks how her own replies turn into movement:

  tags      she picks: one hidden tag like [hug] where it fits, cut out
            before anything is shown or spoken. She's offered a few names
            that fit her mood (BAND_PICKS, portrait.gestures_offered),
            about 70 prompt tokens. Keywords as a fallback.
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
from core import logbook

MODES = ("tags", "meaning", "keywords", "off")
# The built-in gestures are files in portrait/gestures/ (wave.js,
# hug.js...). Each says what it's for ("about"), whether it's private
# (never from stream chat), and so on; read from there, so a new file is a
# new gesture with nothing else to edit.
_GESTURE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "portrait", "gestures")
_files = {"at": 0.0, "found": {}}


def builtin():
    """{name: {"about": str, "private": bool, "left": bool, "full": bool, "lewd": bool, "view": bool}} for every gesture file."""
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
                       "left": bool(re.search(r"^\s*left:\s*true", text, re.M)),
                       "full": bool(re.search(r"^\s*full:\s*true", text, re.M)),
                       "lewd": bool(re.search(r"^\s*lewd:\s*true", text, re.M)),
                       "view": bool(re.search(r"^\s*view:\s*\d", text, re.M))}
    _files.update(at=time.monotonic(), found=found)
    return found


def _shown(g):
    """A gesture marked full: true only reads with all of her on screen (her
    legs), so it's offered only while the portrait is framed full body -
    otherwise it would be a tag that does nothing visible, and prompt
    tokens for nothing."""
    return not g.get("full") or str(getattr(config, "PORTRAIT_FRAME", "bust")) == "full"


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
            from web import livefeed

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

_turn = {"sent": set(), "asides": set()}   # gestures sent; asides already read


def mode():
    m = str(getattr(config, "PORTRAIT_GESTURES", "keywords") or "keywords").lower()
    return m if m in MODES else "keywords"


def _three_d():
    return str(getattr(config, "PORTRAIT_MODEL", "")).lower().endswith((".vrm", ".glb"))


# -- tags ----------------------------------------------------------------
# The short list she's offered in tags mode, by her mood band (the same
# bands as the portrait's idles: grudge, cool, neutral, warm, loving, lewd).
# Offering all forty-odd gestures with descriptions cost hundreds of prompt
# tokens and read to a small model as an invitation to narrate a move in
# every line. A handful of names that fit the moment does the job. Names
# that aren't gesture files here are skipped; if a band comes up short,
# other gestures fill the gap. Every gesture still plays from an aside she
# writes, the keyword fallback and meaning mode.
BAND_PICKS = {
    "grudge": ["huff", "sulk", "step_back", "shrug"],
    "cool": ["shrug", "huff", "explain", "wave", "step_back"],
    "neutral": ["wave", "shrug", "explain", "bounce", "surprise", "giggle", "shy"],
    "warm": ["wave", "hug", "giggle", "bounce", "shy", "wink", "surprise", "shrug"],
    "loving": ["hug", "blow_kiss", "giggle", "shy", "wink", "beckon_kiss", "bounce", "wave"],
    "lewd": ["sultry_beckon", "beckon_kiss", "blow_kiss", "look_back", "bend_over", "touch_self",
             "wink", "shy"],
}
SAD_PICKS = ["cry", "hands_on_chest"]      # a sad mood, whatever the band


def _band():
    """(band, mood name): the band the portrait uses, from the mood."""
    try:
        from mind import mood

        st = mood.portrait_state()
        w = float(st.get("warmth") or 0.0)
        band = st.get("row") or ("cool" if w < -0.2 else "neutral" if w < 0.35 else "warm" if w < 0.66 else "loving")
        return band, str(st.get("label") or "")
    except Exception:
        return "neutral", ""


def offered(private=True, limit=None):
    """The gesture names she's offered right now, at most limit
    (portrait.gestures_offered), fitting her mood."""
    from mind import mood

    tame = bool(mood.tame())      # live on a stream with lewd off: don't offer the lewd ones
    ok = {n for n, g in builtin().items()
          if g["about"] and (private or not g["private"]) and not (tame and g.get("lewd")) and _shown(g)}
    ok |= {c["name"] for c in clips() if c.get("about") and (private or not c.get("private"))}
    if limit is None:
        try:
            limit = int(getattr(config, "PORTRAIT_GESTURES_OFFERED", 8))
        except (TypeError, ValueError):
            limit = 8
    limit = max(0, limit)
    band, label = _band()
    picks = (SAD_PICKS if "sad" in label.lower() or "hurt" in label.lower() else []) + BAND_PICKS.get(band, [])
    out = list(dict.fromkeys(n for n in picks if n in ok))
    out += sorted(n for n in ok if n not in out)        # only reached when a band comes up short
    return out[:limit]


def prompt_line(private=True):
    """The system prompt's line about her body, in tags mode, for a 3D
    model: a few gesture names that fit her mood (offered()). Empty
    otherwise, so it costs nothing when it can't be used."""
    if mode() != "tags" or not _three_d():
        return ""
    names = offered(private)
    if not names:
        return ""
    # names only: with "(what it's for)" beside each, small models copied
    # the descriptions into the reply as stage directions
    # no advice about how to write: every rule added here changed how a
    # small model talked, which is why keywords mode is the default
    return (f"You can move on screen: put one of these where it fits: {' '.join(f'[{n}]' for n in names)}. "
            "Most replies need none.\n")


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
    _turn["asides"] = set()


def from_tags(answer_text):
    """Send any tag she's written so far, once each per turn. Runs in
    every mode, so a tag never does nothing - but only tags mode asks for
    them. A move she described instead, "(beckons you over and blows a
    kiss)", plays too (from_asides)."""
    if mode() == "off":
        return
    if "(" in answer_text or "*" in answer_text:
        from_asides(answer_text)
    if "[" not in answer_text:
        return

    for m in _tag().finditer(answer_text):
        # the name as the file spells it (sultryBeckon), whatever case she wrote
        name = next((n for n in names() if n.lower() == m.group(1).lower()), m.group(1))

        if name.lower() not in _turn["sent"]:
            _turn["sent"].add(name.lower())
            _emit(name, "tag")


# -- described moves -------------------------------------------------------
# Small models often narrate a move, "(bends forward, looking back over her
# shoulder)", rather than tagging it. An aside that clearly describes one
# gesture plays it; the words stay as she wrote them.
_ASIDE = re.compile(r"\(([^()\n]{3,120})\)|\*([^*\n]{3,120})\*")
_STOP = frozenset("a an and the you your her his him she he it its to of over at in on with "
                  "then what is are for from up as".split()) - {"over"}
ASIDE_MIN_WORDS = 2        # words an aside must share with a gesture's description
ASIDE_MIN_SHARE = 0.5      # and the share of the aside's own words they make up


def _stems(text):
    out = set()
    for w in re.findall(r"[a-z]+", text.lower().replace("_", " ")):
        if w in _STOP or len(w) < 3:
            continue
        if w.endswith("ing") and len(w) > 5:
            w = w[:-3]                       # looking -> look
        elif w.endswith("sses"):
            w = w[:-2]                       # kisses -> kiss
        elif w.endswith("s") and not w.endswith("ss") and len(w) > 3:
            w = w[:-1]                       # waves -> wave, blows -> blow
        out.add(w)
    return out


def _offered_now():
    """{name: description} she could be offered on this turn: private ones
    only in private turns, lewd ones not while tame, full-body ones only
    when she's framed full."""
    try:
        from core import turnctx

        private = turnctx.current().private
    except Exception:
        private = True
    try:
        from mind import mood

        tame = bool(mood.tame())
    except Exception:
        tame = False
    found = {n: g["about"] for n, g in builtin().items()
             if g["about"] and (private or not g["private"]) and not (tame and g.get("lewd")) and _shown(g)}
    for c in clips():
        if c.get("about") and (private or not c.get("private")):
            found[c["name"]] = str(c["about"])
    return found


def match_aside(aside, offered=None):
    """The gesture an aside describes, or None."""
    words = _stems(aside)
    if len(words) < ASIDE_MIN_WORDS:
        return None
    best, best_score = None, (0.0, 0.0)
    for name, about in (offered if offered is not None else _offered_now()).items():
        theirs = _stems(about) | _stems(name)
        shared = len(words & theirs)
        # how much of the aside it explains, then (a tie) how much of the
        # gesture the aside covers: "blows you a kiss" is blow_kiss, not
        # the beckon that ends in one
        score = (shared / len(words), shared / len(theirs))
        if shared >= ASIDE_MIN_WORDS and score[0] >= ASIDE_MIN_SHARE and score > best_score:
            best, best_score = name, score
    return best


def from_asides(answer_text):
    """Play each gesture her (asides) and *asides* describe, once per turn."""
    if not _three_d():
        return
    offered = None
    for m in _ASIDE.finditer(answer_text):
        aside = m.group(1) or m.group(2)
        key = aside.strip().lower()
        if key in _turn["asides"]:
            continue
        # apart from "sent": an aside that matched nothing mustn't make
        # meaning mode think a gesture already played
        _turn["asides"].add(key)
        offered = _offered_now() if offered is None else offered
        name = match_aside(aside, offered)
        if name and name.lower() not in _turn["sent"]:
            _turn["sent"].add(name.lower())
            _emit(name, "aside")


def _emit(name, src):
    try:
        from web import livefeed

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
    # turns are asked for, not guessed from the mood of the talk: never by meaning
    found = [(n, g["about"], g["private"]) for n, g in builtin().items() if _shown(g) and not g.get("view")]
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
    from mind import embedmem

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
