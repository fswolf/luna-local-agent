"""The Final Fantasy Legend (SaGa, English): her party, the battle and the
text on screen, read from the game's memory.

Worked out on the real cartridge (title "SAGA"): the party is four 0x1F-byte
records at 0xCC00 (name, type, HP, stats, eight items with their uses), the
bag is eight item/uses pairs at 0xCC7C, gold is packed BCD at 0xCC8D, and in
battle the fighters are 0x20-byte records at 0xD000 (her party) and 0xD080
(the enemies), with the enemy groups as id/count pairs at 0xD3E9; 0xFFE0 says
whether a battle is on (outside one, that memory holds the town's map). Names of
monsters, races and items come from the cartridge's own tables. The screen
text is the background and window tile maps read through the game's font,
with the pointing-hand cursor shown as >.
"""

from . import _saga1_tables as _t              # monster/race and item names, from the cartridge

NAME = "Final Fantasy Legend"
TITLES = ("SAGA",)
EXACT = True                       # "SAGA2" and "SAGA3" are other games
GOAL = "climb the tower in the center of the world to Paradise"

# -- memory ----------------------------------------------------------------------
PARTY, MEMBER, SLOTS = 0xCC00, 0x1F, 4    # +0 0xFF = empty slot, +1 name (4), +5 type, +6 HP,
#                                           +8 max HP, +B str, +C def, +D agl, +E mana,
#                                           +F 8 x (item, uses); the bag follows the fourth
BAG = 0xCC7C                              # 8 x (item, uses), 0xFF = empty
GOLD = 0xCC8D                             # 3 bytes BCD
MAP, Y, X = 0xCCC7, 0xCCC8, 0xCCC9        # map number, position in half-tiles
MODE = 0xFFE0                             # what the game is doing: 1 walking, 8 a battle, 12 a battle ending
BATTLE_MODES = (8, 12)
FIGHTER = 0x20                            # battle record: +2 0xFF = empty, +3 HP, +5 max HP, +1F type
BATTLE_PARTY, BATTLE_ENEMY, ENEMY_SLOTS = 0xD000, 0xD080, 16   # party slot n is battle record n
GROUPS = 0xD3E9                           # 3 x (monster type, how many)
CURSOR_TILE = 0x7C                        # the pointing hand, a sprite

UNLIMITED = 0xFE                          # an item's uses: never runs out

CHARS = {0x70: ".", 0x71: "..", 0x72: "-", 0x73: "!", 0x74: "?", 0x75: ":", 0x76: "·",
         0x7F: " ", 0xF0: "H", 0xF1: "P", 0xF5: "/"}
CHARS.update({0x0A + i: chr(ord("A") + i) for i in range(26)})
CHARS.update({0x24 + i: chr(ord("a") + i) for i in range(26)})
CHARS.update({i: str(i) for i in range(10)})
ICONS = set(range(0x68, 0x70))          # sword, armor, book... drawn before item names
#                                         (0xF0, 0xF1 and 0xF5 are H, P and / in menus, map tiles elsewhere:
#                                         a map row has no letters, so it's left out anyway)
BORDER = set(range(0x77, 0x7F))

W, H = 20, 18


def _name(raw):
    """A name as the game stores it (letters with the top bit set, 0xFF or 0x7F as blanks)."""
    out = []
    for b in raw:
        c = b & 0x7F
        if b == 0 or b == 0xFF or c == 0x7F:
            out.append(" ")
        elif c in ICONS:
            continue
        else:
            out.append(CHARS.get(c, ""))
    return " ".join("".join(out).split())


def _bcd(m, a, n):
    digits = "".join(f"{m[a + i] >> 4}{m[a + i] & 15}" for i in range(n))
    return int(digits) if digits.isdigit() else 0


def _word(m, a):
    return m[a] | m[a + 1] << 8


def kind(n):
    return _t.KINDS[n] if n < len(_t.KINDS) else f"type {n}"


def item(n):
    return _t.ITEMS[n] if n < len(_t.ITEMS) else f"item {n}"


def _items(m, a, count):
    out = []
    for i in range(count):
        n, uses = m[a + i * 2], m[a + i * 2 + 1]
        if n == 0xFF or (n == 0 and uses == 0):         # empty, or memory not set up yet
            continue
        out.append(item(n) + ("" if uses == UNLIMITED else f" x{uses}"))
    return out


# -- the screen ------------------------------------------------------------------
def _tiles(m):
    lcdc, scx, scy, wx, wy = m[0xFF40], m[0xFF43], m[0xFF42], m[0xFF4B], m[0xFF4A]
    bg = 0x9C00 if lcdc & 0x08 else 0x9800
    win = 0x9C00 if lcdc & 0x40 else 0x9800
    rows = [[m[bg + ((scy // 8 + y) % 32) * 32 + (scx // 8 + x) % 32] for x in range(W)] for y in range(H)]
    if lcdc & 0x20 and wy < 144:
        for y in range(wy // 8, H):
            for x in range(max(0, (wx - 7) // 8), W):
                rows[y][x] = m[win + (y - wy // 8) * 32 + (x - (wx - 7) // 8)]
    return rows


def _cursor(m):
    for i in range(40):
        y, x, t = m[0xFE00 + i * 4], m[0xFE01 + i * 4], m[0xFE02 + i * 4]
        if t == CURSOR_TILE and 16 <= y < 160 and 8 <= x < 168:
            return (y - 16) // 8, (x - 8) // 8 + 1         # the cell the hand points from
    return None


def screen_text(m):
    """The words on screen, row by row: the font's letters, everything else
    (the map, monsters, frames) as blanks; rows without words are left out."""
    rows = [[CHARS.get(b, " ") if b < 0x7F or b in (0xF0, 0xF1, 0xF5) else " " for b in r] for r in _tiles(m)]
    spot = _cursor(m)
    if spot and 0 <= spot[0] < H and 0 <= spot[1] < W and not rows[spot[0]][spot[1]].strip():
        rows[spot[0]][spot[1]] = ">"
    out = []
    for r in rows:
        text = "".join(r).rstrip()
        if sum(c.isalnum() for c in text) >= 2:
            out.append(text)
    return "\n".join(out)


# -- what she's told -------------------------------------------------------------
PLACES = {1: "the town you start in", 88: "the first world outside town"}   # the two checked so far


def place(m):
    return PLACES.get(m[MAP], f"map {m[MAP]}")


def _members(m):
    """(slot, base) for each party member there is. An empty slot starts with
    0xFF; before a new game is set up the memory is all zeros, so no name either."""
    return [(i, PARTY + i * MEMBER) for i in range(SLOTS)
            if m[PARTY + i * MEMBER] != 0xFF and m[PARTY + i * MEMBER + 1] not in (0, 0xFF)]


def describe(m):
    fighting = m[MODE] in BATTLE_MODES
    lines = [f"Where: {place(m)}, x {m[X] // 2}, y {m[Y] // 2}"
             + ("  ·  in a battle" if fighting else ""),
             f"Gold: {_bcd(m, GOLD, 3)}GP"]

    members = _members(m)
    lines.append("Party:" if members else "Party: nobody yet")
    for i, base in members:
        hp, top = _word(m, base + 6), _word(m, base + 8)
        if fighting:                                   # the battle keeps its own HP
            b = BATTLE_PARTY + i * FIGHTER
            if m[b + 2] != 0xFF:
                hp, top = _word(m, b + 3), _word(m, b + 5)
        stats = f"Str {m[base + 0xB]}, Def {m[base + 0xC]}, Agl {m[base + 0xD]}, Mana {m[base + 0xE]}"
        things = _items(m, base + 0xF, 8)
        lines.append(f"  {i + 1}. {_name(m[base + 1 + k] for k in range(4)) or '?'} ({kind(m[base + 5])})"
                     f" HP {hp}/{top}" + (" DOWN" if hp == 0 else "") + f" - {stats}"
                     + (f" - {', '.join(things)}" if things else ""))

    bag = _items(m, BAG, 8)
    lines.append("Bag: " + (", ".join(bag) if bag else "empty"))

    if fighting:
        groups = []
        for g in range(3):
            n, count = m[GROUPS + g * 2], m[GROUPS + g * 2 + 1]
            if n == 0xFF or not count:
                continue
            hps = [f"{_word(m, e + 3)}/{_word(m, e + 5)}"
                   for e in (BATTLE_ENEMY + k * FIGHTER for k in range(ENEMY_SLOTS))
                   if m[e + 2] != 0xFF and m[e + 0x1F] == n]
            groups.append(f"{kind(n)} x{count}" + (f" (HP {', '.join(hps)})" if hps else ""))
        if groups:
            lines.append("Against: " + "; ".join(groups))

    text = screen_text(m)
    lines.append("On screen:" + ("\n" + text if text else " no text (walking around)"))
    return "\n".join(lines)
