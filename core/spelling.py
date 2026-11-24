"""Spelling suggestions for the right-click menu on her pages (web/head.js).

A page can't read the browser's own spellchecker: its suggestions live in
the browser's context menu and nowhere else, and that menu brings Back,
Reload and Inspect with it. So the pages keep their own menu and ask here.

pyspellchecker's word list, which knows how common each word is: a
misspelling's candidates are the known words one or two edits away, the
commoner first, two edits counting for much less than one ("skool" ->
"school"), and the more alike they look the better ("luv" -> "love"
rather than "but"). Off quietly when the package isn't installed: the
menu simply has no suggestions.
"""
import re
import threading
from difflib import SequenceMatcher

from core import logbook

LANGUAGE = "en"
MAX = 5
TWO_EDITS_UP_TO = 9           # letters: two edits of a longer word takes most of a second
FAR = 50                      # how much less a two-edit word counts than a one-edit one
ALIKE = 6                     # how much looking alike counts: likeness (0-1) to this power

_state = {"checker": None, "failed": False}
_lock = threading.Lock()
_seen = {}                    # word (lower case) -> (known, suggestions): the same word costs nothing twice
SEEN = 5000
BATCH = 40                    # most words one ask can bring (the page sends what you've typed)
_WORD = re.compile(r"^[A-Za-z][A-Za-z']*$")


def _checker():
    with _lock:
        if _state["checker"] is None and not _state["failed"]:
            try:
                from spellchecker import SpellChecker

                _state["checker"] = SpellChecker(language=LANGUAGE)
            except Exception as e:
                _state["failed"] = True
                logbook.info("spelling", "no spelling suggestions (pip install pyspellchecker): %s", e)
        return _state["checker"]


def _cased(word, like):
    """A suggestion written the way the word was: Skool -> School, SKOOL -> SCHOOL."""
    if like.isupper() and len(like) > 1:
        return word.upper()
    if like[:1].isupper():
        return word[:1].upper() + word[1:]
    return word


def check(word):
    """{"known": bool, "suggestions": [...]} for one word as typed. Anything
    that isn't a plain word (numbers, a path, a URL) counts as known."""
    word = str(word or "").strip()
    if not _WORD.match(word) or len(word) < 2 or len(word) > 30:
        return {"known": True, "suggestions": []}
    spell = _checker()
    if spell is None:
        return {"known": True, "suggestions": []}

    low = word.lower().strip("'")
    if low not in _seen:
        _seen[low] = _suggest(spell, low)
        if len(_seen) > SEEN:
            for old in list(_seen)[:SEEN // 5]:
                _seen.pop(old, None)
    known, best = _seen[low]
    return {"known": known, "suggestions": [_cased(w, word) for w in best]}


def _suggest(spell, low):
    """(known, suggestions) for a lower-case word."""
    with _lock:                                   # one at a time: its caches aren't thread-safe
        if low in spell:
            return True, []
        near = spell.known(spell.edit_distance_1(low))
        score = {w: spell.word_usage_frequency(w) for w in near}
        if len(low) <= TWO_EDITS_UP_TO or not near:
            for w in spell.known(spell.edit_distance_2(low)) - near:
                score[w] = spell.word_usage_frequency(w) / FAR
    score = {w: f * SequenceMatcher(None, low, w).ratio() ** ALIKE for w, f in score.items()}
    return False, sorted(score, key=lambda w: (-score[w], w))[:MAX]


def check_many(words):
    """{word: check(word)} for up to BATCH different words, as typed."""
    out = {}
    for word in words:
        word = str(word or "")[:40]
        if word not in out and len(out) < BATCH:
            out[word] = check(word)
    return out
