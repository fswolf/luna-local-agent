"""Readers: a game's state as text, read from the Game Boy's memory.

Any game plays without one, from the screen alone. A reader is what makes a
game easy for her: where she is, her team or stats, and the text on screen
(dialogue, menus, the battle) as words instead of pixels.

A reader is a module here with:
    NAME = "Pokemon Red/Blue"
    TITLES = ("POKEMON RED", "POKEMON BLUE")    # cartridge titles it knows
    def describe(memory) -> str                 # memory[addr] -> byte
and optionally
    GOAL = "..."                                # her goal for a playthrough
    def place(memory) -> str                    # where she is, for her notes

A new one is picked up by itself: drop the file here.
"""
import importlib
import os
import pkgutil

_HERE = os.path.dirname(os.path.abspath(__file__))


def all_readers():
    out = []
    for info in pkgutil.iter_modules([_HERE]):
        if info.name.startswith("_"):
            continue
        try:
            out.append(importlib.import_module(f"{__name__}.{info.name}"))
        except Exception:
            continue                         # a broken reader never stops the game
    return out


def find(title):
    """The reader for a cartridge title ("POKEMON RED"), or None."""
    title = str(title or "").strip().upper()
    for module in all_readers():
        if any(title.startswith(t.upper()) for t in getattr(module, "TITLES", ())):
            return module
    return None
