"""Who's who: the people Luna can recognise, by face (presence.py) and by
voice (voices.py).

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
"""
import json
import math
import os
import re
import threading

import config

FOLDER = os.path.join(config.BASE_DIR, "agent", "people")
_lock = threading.Lock()
MAX_PRINTS = 40            # per kind per person: plenty of angles, bounded file


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


def match(kind, vector, threshold):
    """(name, score) of the best match over threshold, else (None, best score)."""
    best_name, best = None, -1.0
    for name, person in everyone().items():
        for stored in person.get(kind) or []:
            if len(stored) != len(vector):
                continue          # a print from a different model
            score = _cosine(vector, stored)
            if score > best:
                best_name, best = name, score
    return (best_name, best) if best >= threshold else (None, best)


def pronouns(name):
    """A person's pronouns from their file, or agent.json's people list."""
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


def decide(voice_name=None, voice_checked=False):
    """Who's talking: a recognised voice first. When voices couldn't be
    compared at all (nobody has voice prints), the recognised face in view
    stands in - but a voice that was compared and matched nobody is the
    owner, whoever else is in the room. Returns a name for someone other
    than the owner, or None for the owner (and for anyone unknown)."""
    name = voice_name
    if not name and not voice_checked:
        try:
            import presence

            name = presence.who()
        except Exception:
            name = None
    return None if not name or is_owner(name) else name


def guest():
    """The non-owner talking in the running turn, or None."""
    try:
        import turnctx

        return turnctx.current().speaker
    except Exception:
        return None


def user_line():
    """The system prompt's who-you're-talking-to line, for this turn."""
    name = guest()
    if not name:
        return config.user_line()
    said = pronouns(name)
    owner = getattr(config, "USER", "the user")
    return (f"This time you're talking with {name}{' (' + said + ')' if said else ''}, "
            f"not {owner}: someone else in the house, recognised by voice or face. "
            f"The facts below are what you've learned about {name}.\n")


# ---------------------------------------------------------------------------
# Their own memories (the owner's stay in longterm.py's store)
# ---------------------------------------------------------------------------
MAX_FACTS = 500


def facts(name):
    return list((load(name) or {}).get("facts") or [])


def add_fact(name, fact):
    """Remember one fact about name. False if they already have it."""
    fact = str(fact or "").strip()
    if not fact:
        return False
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
