"""Her own manual: Luna answering "how do I make you...?" from her docs.

The docs folder (and the README) is the manual for everything she can do:
commands, settings, plugins, what to install. read_manual searches it, so
"how do I get you to play chess?" gets the real /chess commands instead
of a confident guess, and "can you see me?" gets what presence does.

Kept apart from the knowledge base on purpose. That one is your notes and
your documents ("from the user's own documents"); this is hers, about
herself, and it's always there: no folder to fill, no embedding server.
The docs are small (a few hundred passages), so word matching (BM25,
headings counted twice) is quick and good enough, and the index is
rebuilt only when a doc changes.
"""
import math
import os
import re
import threading

from collections import Counter

import config

from . import tool

_cache = {"stamp": None, "items": []}
_lock = threading.Lock()


def _files():
    root = config.BASE_DIR
    docs = os.path.join(root, "docs")
    found = [os.path.join(root, "README.md")]

    try:
        found += [os.path.join(docs, n) for n in sorted(os.listdir(docs))
                  if n.endswith(".md") and not n.startswith("_")]
    except OSError:
        pass

    return [f for f in found if os.path.isfile(f)]


def _items():
    """Every passage of the manual, re-read when a doc changes."""
    from mind import knowledge

    files = _files()
    stamp = tuple((f, os.path.getmtime(f)) for f in files)

    with _lock:
        if _cache["stamp"] == stamp:
            return _cache["items"]

        items = []

        for path in files:
            try:
                with open(path, encoding="utf-8") as f:
                    text = f.read()
            except OSError:
                continue

            title = _title(text, path)

            for heading, passage in knowledge.chunks(text):
                items.append({"path": path, "heading": heading, "text": passage,
                              "title": title,
                              "words": _terms(passage),
                              "head": _terms(f"{title} {heading}")})

        _cache.update(stamp=stamp, items=items)

        return items


def _where(item):
    rel = os.path.relpath(item["path"], config.BASE_DIR).replace(os.sep, "/")
    return rel + (f" > {item['heading']}" if item["heading"] else "")


# Words that say nothing about WHICH feature: every question has them, and
# knowledge.md's "how do I..." examples used to win on them alone.
_STOP = set("""a an the and or but of to in on at for with from by about as is are was be
been it its this that these those there here i me my mine you your yours she her hers he
him his we us our they them their do does did doing done can could would should will
shall may might must how what which who whom why when where get got make made let use
using used want wanna need set up turn put go going work works working thing things
something anything way please just really also so if then than too very some any all
luna lunas""".split())
_WORD = re.compile(r"[a-z0-9]+")


def _stem(w):
    """Light and blunt, enough that station/stations and setting/settings meet."""
    for end in ("ings", "ing", "ies", "es", "ed", "s"):
        if len(w) > len(end) + 2 and w.endswith(end):
            return w[:-len(end)] + ("y" if end == "ies" else "")
    return w


def _terms(text):
    return Counter(_stem(w) for w in _WORD.findall(str(text or "").lower()) if w not in _STOP)


# Everyday words for things the docs call by their own names. One-way: they
# only add the doc's word to the question, never take the person's away.
_ALSO = {"phone": "station", "tablet": "station", "android": "station", "room": "station",
         "kitchen": "station", "bedroom": "station", "remember": "memory", "forget": "memory",
         "recall": "memory", "toy": "device", "vibrator": "device", "look": "card",
         "outfit": "card", "avatar": "portrait", "model": "portrait", "feel": "mood",
         "feeling": "mood", "speak": "voice", "talk": "voice", "sound": "voice",
         "kokoro": "voice", "hear": "voice", "mic": "voice", "see": "vision", "webcam": "camera"}


def _question(text):
    words = _terms(text)

    for w in list(words):
        if w in _ALSO:
            words[_stem(_ALSO[w])] += 1

    return set(words)


def _title(text, path):
    """The page's # title and its file name: a passage deep in stations.md is
    still about stations even when its own heading is 'Pairing'."""
    m = re.search(r"^#\s+(.+)$", text, re.M)
    name = os.path.splitext(os.path.basename(path))[0]
    return f"{m.group(1) if m else ''} {'' if name.lower() == 'readme' else name}".strip()


def search(query, limit=3):
    """[(score, item)] best first. BM25 on the passage, plus the page title
    and the passage heading counted as a strong hint of what it's about."""
    items = _items()
    q = _question(" ".join(str(query or "").split())[:300])

    if not q or not items:
        return []

    n = len(items)
    avg = sum(sum(i["words"].values()) for i in items) / n or 1
    df = Counter(w for i in items for w in q if w in i["words"] or w in i["head"])
    ranked = []

    for i in items:
        length = sum(i["words"].values())
        s = 0.0

        for w in q:
            if not df[w]:
                continue

            idf = math.log(1 + (n - df[w] + 0.5) / (df[w] + 0.5))
            tf = i["words"].get(w, 0)

            if tf:
                s += idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * length / avg))

            if w in i["head"]:
                s += idf * 1.5

        if s > 0:
            ranked.append((s, i))

    ranked.sort(key=lambda p: p[0], reverse=True)

    return ranked[:limit]


@tool(
    "read_manual",
    "Look something up in your own manual: how YOU work and how to use you. Use it whenever "
    "someone asks what you can do, how to turn something on or off, which command or setting "
    "does something, or how to set up a feature (voice, wake word, camera, presence, people, "
    "portrait, hologram fans, games like chess or Zork, stream chat, plugins, memory, "
    "settings, presets, installing). Answer with the exact command or setting it gives; "
    "never invent commands that aren't in it.",
    {
        "query": {"type": "string", "description": "What they want to know, in plain words."},
        "limit": {"type": "integer", "description": "How many passages, default 3."},
    },
    required=("query",),
    available=lambda: bool(_files()),
    why=lambda: "the docs folder is missing",
)
def _read_manual(query, limit=3):
    try:
        limit = max(1, min(6, int(limit or 3)))
    except (TypeError, ValueError, OverflowError):
        limit = 3

    found = search(query, limit)

    if not found:
        return (f"Your manual says nothing about {query!r}. Say you're not sure rather than "
                "guessing a command; /help lists every command.")

    return "\n\n".join(
        ["From your own manual (give the exact commands and settings it names, and the "
         "page to read for more; the settings page is /settings):"]
        + [f"[{n}] {_where(i)}\n{i['text'][:1400]}" for n, (_s, i) in enumerate(found, 1)])
