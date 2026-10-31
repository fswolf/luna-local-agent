"""Pokemon Red and Blue (English): where she is, her team, the battle, and the
text on screen, read from the game's memory.

Addresses are from the pret/pokered disassembly (wram.asm). The screen text is
the game's own tile map (wTileMap, 20 x 18 tiles) read through the game's font,
so dialogue, menus and the battle screen come through as words, with the menu
cursor shown as >.
"""

NAME = "Pokemon Red/Blue"
TITLES = ("POKEMON RED", "POKEMON BLUE")
GOAL = "8 badges, then the Elite Four"

# -- memory (pokered wram.asm) ---------------------------------------------------
TILEMAP, W, H = 0xC3A0, 20, 18
PLAYER_NAME = 0xD158
PARTY_COUNT, PARTY_MONS, MON_SIZE, PARTY_NICKS = 0xD163, 0xD16B, 0x2C, 0xD2B5
MONEY, BADGES = 0xD347, 0xD356
CUR_MAP, Y, X = 0xD35E, 0xD361, 0xD362
FACING = 0xC109                   # the player sprite: 0 down, 4 up, 8 left, 12 right
IN_BATTLE = 0xD057                # 0 none, 1 wild, 2 trainer
ENEMY_NICK, ENEMY_MON = 0xCFDA, 0xCFE5        # battle struct: HP +1, level +0x0E, max HP +0x0F
BATTLE_NICK, BATTLE_MON = 0xD009, 0xD014

# -- the game's font -------------------------------------------------------------
CHARS = {0x7F: " ", 0x9A: "(", 0x9B: ")", 0x9C: ":", 0x9D: ";", 0x9E: "[", 0x9F: "]",
         0xBA: "é", 0xBB: "'d", 0xBC: "'l", 0xBD: "'s", 0xBE: "'t", 0xBF: "'v",
         0xE0: "'", 0xE1: "PK", 0xE2: "MN", 0xE3: "-", 0xE4: "'r", 0xE5: "'m", 0xE6: "?", 0xE7: "!",
         0xE8: ".", 0xEC: ">", 0xED: ">", 0xEE: "▼", 0xEF: "♂", 0xF0: "¥", 0xF1: "x", 0xF2: ".",
         0xF3: "/", 0xF4: ",", 0xF5: "♀"}
CHARS.update({0x80 + i: chr(ord("A") + i) for i in range(26)})
CHARS.update({0xA0 + i: chr(ord("a") + i) for i in range(26)})
CHARS.update({0xF6 + i: str(i) for i in range(10)})
BORDER = set(range(0x79, 0x7F))   # the text box's frame

MAPS = ["Pallet Town", "Viridian City", "Pewter City", "Cerulean City", "Lavender Town",
        "Vermilion City", "Celadon City", "Fuchsia City", "Cinnabar Island", "Indigo Plateau",
        "Saffron City", "", *[f"Route {n}" for n in range(1, 26)],
        "your house, downstairs", "your house, upstairs", "your rival's house", "Professor Oak's lab"]

MOVES = [None, "Pound", "Karate Chop", "Double Slap", "Comet Punch", "Mega Punch", "Pay Day", "Fire Punch",
         "Ice Punch", "Thunder Punch", "Scratch", "Vise Grip", "Guillotine", "Razor Wind", "Swords Dance",
         "Cut", "Gust", "Wing Attack", "Whirlwind", "Fly", "Bind", "Slam", "Vine Whip", "Stomp",
         "Double Kick", "Mega Kick", "Jump Kick", "Rolling Kick", "Sand Attack", "Headbutt", "Horn Attack",
         "Fury Attack", "Horn Drill", "Tackle", "Body Slam", "Wrap", "Take Down", "Thrash", "Double-Edge",
         "Tail Whip", "Poison Sting", "Twineedle", "Pin Missile", "Leer", "Bite", "Growl", "Roar", "Sing",
         "Supersonic", "Sonic Boom", "Disable", "Acid", "Ember", "Flamethrower", "Mist", "Water Gun",
         "Hydro Pump", "Surf", "Ice Beam", "Blizzard", "Psybeam", "Bubble Beam", "Aurora Beam",
         "Hyper Beam", "Peck", "Drill Peck", "Submission", "Low Kick", "Counter", "Seismic Toss",
         "Strength", "Absorb", "Mega Drain", "Leech Seed", "Growth", "Razor Leaf", "Solar Beam",
         "Poison Powder", "Stun Spore", "Sleep Powder", "Petal Dance", "String Shot", "Dragon Rage",
         "Fire Spin", "Thunder Shock", "Thunderbolt", "Thunder Wave", "Thunder", "Rock Throw",
         "Earthquake", "Fissure", "Dig", "Toxic", "Confusion", "Psychic", "Hypnosis", "Meditate",
         "Agility", "Quick Attack", "Rage", "Teleport", "Night Shade", "Mimic", "Screech", "Double Team",
         "Recover", "Harden", "Minimize", "Smokescreen", "Confuse Ray", "Withdraw", "Defense Curl",
         "Barrier", "Light Screen", "Haze", "Reflect", "Focus Energy", "Bide", "Metronome", "Mirror Move",
         "Self-Destruct", "Egg Bomb", "Lick", "Smog", "Sludge", "Bone Club", "Fire Blast", "Waterfall",
         "Clamp", "Swift", "Skull Bash", "Spike Cannon", "Constrict", "Amnesia", "Kinesis", "Soft-Boiled",
         "High Jump Kick", "Glare", "Dream Eater", "Poison Gas", "Barrage", "Leech Life", "Lovely Kiss",
         "Sky Attack", "Transform", "Bubble", "Dizzy Punch", "Spore", "Flash", "Psywave", "Splash",
         "Acid Armor", "Crabhammer", "Explosion", "Fury Swipes", "Bonemerang", "Rest", "Rock Slide",
         "Hyper Fang", "Sharpen", "Conversion", "Tri Attack", "Super Fang", "Slash", "Substitute",
         "Struggle"]

STATUS = {0x40: "paralyzed", 0x20: "frozen", 0x10: "burned", 0x08: "poisoned"}
FACINGS = {0: "down", 4: "up", 8: "left", 12: "right"}


# -- reading ---------------------------------------------------------------------
def _word(m, a):
    return m[a] << 8 | m[a + 1]


def _text(m, a, n=11):
    out = []
    for i in range(n):
        b = m[a + i]
        if b == 0x50:              # the end of a name
            break
        out.append(CHARS.get(b, ""))
    return "".join(out).strip()


def _bcd(m, a, n):
    return int("".join(f"{m[a + i] >> 4}{m[a + i] & 15}" for i in range(n)))


def _status(byte):
    if byte & 7:
        return "asleep"
    return next((name for bit, name in STATUS.items() if byte & bit), "")


def screen_text(m):
    """The text on screen, row by row: letters through the game's font, the
    world's own tiles (below 0x60) as blanks; rows with no words are left out."""
    rows = []
    for y in range(H):
        line = []
        for x in range(W):
            b = m[TILEMAP + y * W + x]
            line.append("|" if b in BORDER else CHARS.get(b, " ") if b >= 0x60 else " ")
        text = "".join(line).replace("|", " ").rstrip()
        if sum(c.isalnum() for c in text) >= 2:
            rows.append(text)
    return "\n".join(rows)


def place(m):
    n = m[CUR_MAP]
    return MAPS[n] if n < len(MAPS) and MAPS[n] else f"map {n}"


def _mon(m, base, nick):
    hp, level, maxhp = _word(m, base + 1), m[base + 0x21], _word(m, base + 0x22)
    moves = [MOVES[i] for i in (m[base + 8 + k] for k in range(4)) if 0 < i < len(MOVES)]
    status = _status(m[base + 4])
    return (f"{_text(m, nick) or '?'} L{level} HP {hp}/{maxhp}" + (f" ({status})" if status else "")
            + (" FAINTED" if hp == 0 else "") + (f" - moves: {', '.join(moves)}" if moves else ""))


def describe(m):
    lines = [f"Where: {place(m)}, x {m[X]}, y {m[Y]}, facing {FACINGS.get(m[FACING], '?')}"]
    badges = bin(m[BADGES]).count("1")
    lines.append(f"Player: {_text(m, PLAYER_NAME) or '?'}  ·  money ¥{_bcd(m, MONEY, 3)}  ·  badges {badges}/8")

    count = min(m[PARTY_COUNT], 6)
    if count:
        lines.append("Team:")
        lines += [f"  {i + 1}. " + _mon(m, PARTY_MONS + i * MON_SIZE, PARTY_NICKS + i * 11) for i in range(count)]
    else:
        lines.append("Team: none yet")

    fight = m[IN_BATTLE]
    if fight in (1, 2):
        e, me = ENEMY_MON, BATTLE_MON
        lines.append(f"In a {'wild' if fight == 1 else 'trainer'} battle: "
                     f"{_text(m, ENEMY_NICK)} L{m[e + 0x0E]} HP {_word(m, e + 1)}/{_word(m, e + 0x0F)}"
                     f" against your {_text(m, BATTLE_NICK)} L{m[me + 0x0E]} HP {_word(m, me + 1)}/{_word(m, me + 0x0F)}")

    text = screen_text(m)
    lines.append("On screen:" + ("\n" + text if text else " no text (walking around)"))
    return "\n".join(lines)
