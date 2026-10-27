"""Who's who: the people Luna can recognise, by face (senses/presence.py) and by
voice (senses/voices.py).

Each person is one file, agent/people/<name>.json:

    {"name": "Shannon", "pronouns": "she/her",
     "face": [[...128 numbers...], ...], "voice": [[...192 numbers...], ...]}

The numbers are prints (embeddings): what a face or a voice looks like to
a small model, not a picture or a recording. Still personal, so the
folder is gitignored and nothing here is ever sent anywhere.

Matching is cosine similarity: each new print is compared with every
stored print of every person, and the best one wins if it clears the
threshold. Several prints per person (a few angles, a few sentences)
make it steadier than one.

## The ladder: who gets what

    owner        the user block in agent.json: everything, as always
    registered   enrolled here (agent/people/): their own name, memory, tools
    guest        met this session (meet): a name and facts kept in memory
                 only, gone on restart unless the owner keeps them (keep)
    stranger     someone she can tell isn't the owner (STRANGER): no name,
                 none of the owner's memory, a short list of safe tools

She only drops below owner on evidence: a face or voice that clearly
isn't the owner's, compared against the owner's own prints. Nothing to
compare with (the owner never enrolled, no camera, a dark room, a voice
that only just missed) means the owner, as before, so a missing camera
never locks the owner out of their own memory.
"""
import json
import math
import os
import re
import threading
import time

import config

FOLDER = os.path.join(config.BASE_DIR, "agent", "people")
_lock = threading.Lock()
MAX_PRINTS = 40            # per kind per person: plenty of angles, bounded file

STRANGER = "someone new"  # the speaker on a stranger's turn; not a name anyone can enroll
# How far under the match line the owner's own best score must be before a
# face or a voice counts as clearly someone else. Between the two lines she
# isn't sure, and not sure is the owner.
MARGIN = {"face": 0.1, "voice": 0.1}
MEET_WINDOW = 600.0        # seconds an unknown face or voice stays meetable
# What a stranger or a session guest may use: nothing that reads the owner's
# files, screen, mail, history or home, or acts for them. registered people
# and the owner get the full list, as before.
GUEST_TOOLS = frozenset({"get_datetime", "time_until", "calculate", "web_search",
                         "system_status", "read_manual", "meet_guest"})
GUEST_MEMORY_TOOLS = frozenset({"remember_fact", "recall_facts", "forget_fact", "update_fact"})

_session = {}              # guests met this session: name -> {"name", "face", "voice", "facts"}
_unknown = {}              # kind -> (vector, monotonic time): the latest print nobody matched


def _slug(name):
    return re.sub(r"[^a-z0-9_-]+", "-", str(name).strip().lower()).strip("-") or "someone"


def _path(name):
    return os.path.join(FOLDER, _slug(name) + ".json")


def load(name):
    try:
        with open(_path(name)) as file:
            data = json.load(file)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def everyone():
    """Every enrolled person, by name."""
    found = {}
    try:
        names = sorted(os.listdir(FOLDER))
    except OSError:
        return found

    for entry in names:
        if entry.endswith(".json"):
            try:
                with open(os.path.join(FOLDER, entry)) as file:
                    data = json.load(file)
                if isinstance(data, dict) and data.get("name"):
                    found[data["name"]] = data
            except (OSError, ValueError):
                continue
    return found


def save(person):
    os.makedirs(FOLDER, exist_ok=True)
    tmp = _path(person["name"]) + ".tmp"
    with open(tmp, "w") as file:
        json.dump(person, file)
    os.replace(tmp, _path(person["name"]))


def add_prints(name, kind, vectors, pronouns=None):
    """Add face or voice prints to a person (made if new). Returns how many
    they have of that kind now."""
    with _lock:
        person = load(name) or {"name": str(name).strip()}
        if pronouns:
            person["pronouns"] = pronouns
        prints = list(person.get(kind) or [])
        prints.extend([float(x) for x in v] for v in vectors)
        person[kind] = prints[-MAX_PRINTS:]
        save(person)
        return len(person[kind])


def forget(name, kind=None):
    """Forget one kind of print, or the whole person. True if anything went."""
    with _lock:
        person = load(name)
        if person is None:
            return False
        if kind is None:
            try:
                os.remove(_path(name))
            except OSError:
                return False
            return True
        if kind not in person:
            return False
        del person[kind]
        save(person)
        return True


def _cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _people_with(kind):
    """Everyone with prints of this kind: enrolled first, then guests met
    this session."""
    out = [(name, person.get(kind) or []) for name, person in everyone().items()]
    with _lock:
        out += [(name, list(g.get(kind) or [])) for name, g in _session.items()]
    return out


def verdict(kind, vector, threshold):
    """(who, best score): a name when a print clears the threshold,
    STRANGER when it clearly isn't the owner (their own best score is
    MARGIN under the line), None when she can't tell."""
    best_name, best, owner_best = None, -1.0, None
    for name, prints in _people_with(kind):
        mine = is_owner(name)
        for stored in prints:
            if len(stored) != len(vector):
                continue          # a print from a different model
            score = _cosine(vector, stored)
            if score > best:
                best_name, best = name, score
            if mine:
                owner_best = score if owner_best is None else max(owner_best, score)
    if best >= threshold:
        return best_name, best
    if owner_best is not None and owner_best < threshold - MARGIN.get(kind, 0.1):
        # only a print that's clearly not the owner can be met later: a near
        # miss might be the owner, and naming it "Mike" would teach her that
        # the owner's own voice is Mike's
        with _lock:
            _unknown[kind] = ([float(x) for x in vector], time.monotonic())
        return STRANGER, best
    return None, best


def match(kind, vector, threshold):
    """(name, score) of the best match over threshold, else (None, best score)."""
    who, score = verdict(kind, vector, threshold)
    return (None, score) if who == STRANGER else (who, score)


# ---------------------------------------------------------------------------
# Guests met this session: in memory only
# ---------------------------------------------------------------------------
def _clean_name(name):
    name = re.sub(r"\s+", " ", str(name or "")).strip().strip(".,!?\"'")
    return name[:40]


def session_guest(name):
    """The session guest called name (any case), or None."""
    with _lock:
        for known, guest in _session.items():
            if known.lower() == str(name or "").strip().lower():
                return guest
    return None


def session_guests():
    with _lock:
        return [dict(g) for g in _session.values()]


def meet(name):
    """Give the latest unknown face and voice a name for this session.
    Returns (ok, message). Nothing goes to disk."""
    name = _clean_name(name)
    if not name or name.lower() == STRANGER:
        return False, "That isn't a name."
    if is_owner(name) or load(name) is not None:
        # never a hint about who's enrolled: a name alone proves nothing
        return False, (f"Not met: {name} is someone she already knows by face or voice, "
                       "and saying a name doesn't make someone that person.")
    now = time.monotonic()
    with _lock:
        fresh = {kind: vec for kind, (vec, at) in _unknown.items() if now - at <= MEET_WINDOW}
        if not fresh:
            return False, ("She hasn't seen or heard anyone new in the last few minutes, "
                           "so there's nothing to put the name to. (She can only tell someone "
                           "is new once the owner is enrolled by face or voice.)")
        guest = next((g for k, g in _session.items() if k.lower() == name.lower()), None)
        if guest is None:
            guest = _session[name] = {"name": name, "face": [], "voice": [], "facts": []}
        for kind, vector in fresh.items():
            guest[kind] = (guest[kind] + [vector])[-MAX_PRINTS:]
            _unknown.pop(kind, None)
    _forget_last_look()
    kinds = " and ".join(sorted(fresh))
    return True, f"Met {name} (by {kinds}), for this session only."


def _forget_last_look():
    """The face check's cached answer predates this: look again next turn."""
    try:
        from senses import facecheck

        facecheck.forget_last()
    except Exception:
        pass


def keep(name):
    """Make a session guest a registered person: their prints and facts go
    to agent/people/. The owner's call (/people keep). Returns (ok, message)."""
    guest = session_guest(name)
    if guest is None:
        return False, f"No guest called {name} this session."
    with _lock:
        _session.pop(guest["name"], None)      # first: from here on, their facts go to disk
    for kind in ("face", "voice"):
        if guest.get(kind):
            add_prints(guest["name"], kind, guest[kind])
    if not any(guest.get(k) for k in ("face", "voice")):
        save({"name": guest["name"]})
    for fact in guest.get("facts") or []:
        add_fact(guest["name"], fact)
    return True, f"Kept {guest['name']}: she'll know them after a restart too."


def forget_guest(name):
    """Drop a session guest. True if there was one."""
    guest = session_guest(name)
    if guest is None:
        return False
    with _lock:
        _session.pop(guest["name"], None)
    return True


def reset_session():
    """Forget every session guest and unknown print (tests, a fresh start)."""
    with _lock:
        _session.clear()
        _unknown.clear()


def pronouns(name):
    """A person's pronouns from their file, or agent.json's people list."""
    if name == STRANGER or session_guest(name) is not None:
        return ""
    person = load(name) or {}
    if person.get("pronouns"):
        return person["pronouns"]
    for entry in getattr(config, "PEOPLE", []) or []:
        if str(entry.get("name", "")).lower() == str(name).lower():
            return entry.get("pronouns", "")
    return ""


# ---------------------------------------------------------------------------
# Who's talking this turn
# ---------------------------------------------------------------------------
def is_owner(name):
    """Is this the person agent.json's user block names (the owner)?"""
    own = str(getattr(config, "USER_NAME", "") or "").strip().lower()
    return bool(name) and bool(own) and str(name).strip().lower() == own


def decide(voice_name=None, voice_checked=False, voice_score=None, at_desk=True):
    """Who's talking, from the voice (voices.identify: a name, STRANGER,
    or None) and, at the desk, the face. Returns a name for a registered
    person or a session guest, STRANGER for someone who clearly isn't the
    owner, or None for the owner (and whenever she can't tell). Never raises.

    - a voice she recognises wins
    - the face at the desk is asked when voices couldn't be compared, when
      the voice said "not the owner" (a face can overrule that), and when
      the voice only just missed (facecheck.unsure)
    - a relay station or satellite (at_desk False) has only the voice: the
      face at the desk says nothing about who's in that room"""
    try:
        voice = voice_name or None
        if voice and voice != STRANGER:
            return _not_owner(voice)
        if at_desk:
            unsure = False
            if voice_checked and voice is None:
                try:
                    from senses import facecheck

                    unsure = facecheck.unsure(voice_score)
                except Exception:
                    unsure = False
            if not voice_checked or voice == STRANGER or unsure:
                reason = ("no voice prints" if not voice_checked
                          else "voice says someone new" if voice == STRANGER else "voice not sure")
                # a voice that's clearly someone else outweighs a cached
                # "it's the owner": look again rather than reuse it
                face = _face(reason, fresh=voice == STRANGER)
                if face:
                    return _not_owner(face)
        return STRANGER if voice == STRANGER else None
    except Exception:
        return None


def _not_owner(name):
    return None if not name or is_owner(name) else name


def typed_speaker():
    """Who's typing: the owner (None), unless the face check is on
    (people.face_check) and sees someone else at the desk: a name, or
    STRANGER for a face that clearly isn't the owner's. Never raises."""
    try:
        from senses import facecheck

        if not facecheck.enabled():
            return None
        return _not_owner(_face("typed"))
    except Exception:
        return None


def _face(reason, fresh=False):
    """The face at the desk: presence's when it's watching, otherwise one
    look (facecheck, when it's on; fresh skips its cached answer). A
    name, STRANGER, or None."""
    try:
        from senses import presence

        seen = presence.verdict()                # None unless presence is watching
        if seen or presence.running():
            return seen
    except Exception:
        pass
    try:
        from senses import facecheck

        return facecheck.check(reason, fresh=fresh)
    except Exception:
        return None


def guest():
    """The non-owner talking in the running turn, or None."""
    try:
        from core import turnctx

        return turnctx.current().speaker
    except Exception:
        return None


def user_line():
    """The system prompt's who-you're-talking-to line, for this turn."""
    name = guest()
    if not name:
        return config.user_line()
    owner = getattr(config, "USER", "the user")
    if name == STRANGER:
        return (f"This time you're talking with someone new, not {owner}: you can see or hear it "
                f"isn't {owner}, and you don't know who they are. Be yourself and be friendly, "
                f"but keep {owner}'s private life private: nothing you know about {owner} is "
                f"theirs to hear. If they tell you their name, call meet_guest with it.\n")
    if session_guest(name) is not None:
        return (f"This time you're talking with {name}, not {owner}: someone you met this "
                f"session. You'll forget them when you restart unless {owner} keeps them. "
                f"Keep {owner}'s private life private. The facts below are what {name} told you.\n")
    said = pronouns(name)
    return (f"This time you're talking with {name}{' (' + said + ')' if said else ''}, "
            f"not {owner}: someone else in the house, recognised by voice or face. "
            f"The facts below are what you've learned about {name}.\n")


def tools_for(speaker):
    """The tools a speaker may use: None (all of them) for the owner and
    registered people, GUEST_TOOLS for a stranger, plus their own memory
    for a session guest."""
    if not speaker:
        return None
    if speaker == STRANGER:
        return GUEST_TOOLS
    if session_guest(speaker) is not None:
        return GUEST_TOOLS | GUEST_MEMORY_TOOLS
    return None


# ---------------------------------------------------------------------------
# Their own memories (the owner's stay in mind/longterm.py's store)
# ---------------------------------------------------------------------------
MAX_FACTS = 500


def facts(name):
    if name == STRANGER:
        return []
    guest = session_guest(name)
    if guest is not None:
        return list(guest.get("facts") or [])
    return list((load(name) or {}).get("facts") or [])


def add_fact(name, fact):
    """Remember one fact about name. False if they already have it, and
    always for a stranger (nobody to keep it for). A session guest's
    facts stay in memory."""
    fact = str(fact or "").strip()
    if not fact or name == STRANGER:
        return False
    guest = session_guest(name)
    if guest is not None:
        with _lock:
            if fact.lower() in (f.lower() for f in guest["facts"]):
                return False
            guest["facts"] = (guest["facts"] + [fact])[-MAX_FACTS:]
            return True
    with _lock:
        person = load(name) or {"name": str(name).strip()}
        known = list(person.get("facts") or [])
        if fact.lower() in (f.lower() for f in known):
            return False
        known.append(fact)
        person["facts"] = known[-MAX_FACTS:]
        save(person)
        return True


def set_fact(name, old, new):
    """Rewrite one of name's facts (new=None forgets it). True if it was there."""
    if name == STRANGER:
        return False
    guest = session_guest(name)
    if guest is not None:
        with _lock:
            if old not in guest["facts"]:
                return False
            index = guest["facts"].index(old)
            if new is None:
                guest["facts"].pop(index)
            else:
                guest["facts"][index] = new
            return True
    with _lock:
        person = load(name)
        if not person or old not in (person.get("facts") or []):
            return False
        known = person["facts"]
        index = known.index(old)
        if new is None:
            known.pop(index)
        else:
            known[index] = new
        save(person)
        return True
