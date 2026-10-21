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
import os
import threading

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
    import knowledge

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

            for heading, passage in knowledge.chunks(text):
                items.append({"path": path, "heading": heading, "text": passage})

        _cache.update(stamp=stamp, items=items)

        return items


def _where(item):
    rel = os.path.relpath(item["path"], config.BASE_DIR).replace(os.sep, "/")
    return rel + (f" > {item['heading']}" if item["heading"] else "")


def search(query, limit=3):
    """[(score, item)] best first."""
    import knowledge

    items = _items()
    query = " ".join(str(query or "").split())[:300]

    if not query or not items:
        return []

    # a heading saying what a passage is about counts twice
    weighted = [dict(i, heading=i["heading"] + " " + i["heading"]) for i in items]
    scores = knowledge._bm25(query, weighted)
    ranked = sorted(zip(scores, items), key=lambda p: p[0], reverse=True)

    return [(s, i) for s, i in ranked[:limit] if s > 0]


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
    except (TypeError, ValueError):
        limit = 3

    found = search(query, limit)

    if not found:
        return (f"Your manual says nothing about {query!r}. Say you're not sure rather than "
                "guessing a command; /help lists every command.")

    return "\n\n".join(
        ["From your own manual (give the exact commands and settings it names; "
         "the settings page is /settings):"]
        + [f"[{n}] {_where(i)}\n{i['text'][:1400]}" for n, (_s, i) in enumerate(found, 1)])
