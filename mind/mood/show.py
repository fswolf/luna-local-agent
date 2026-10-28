"""Reading her mood back: the label (sticky, so it doesn't flicker), the line in
her prompt, her voice, face, idles and emotes, what the portrait is sent, and
the tame mode that steps the lewd row down while a stream is live.

Part of mind/mood (see mind/mood/__init__.py).
"""
import config
from mind.mood.core import S, _extra, _grudging, _intensity, _lock, _row_of, _state, _walk
from mind.mood.files import moods
from mind.mood import walkaway


def preview_list():
    """Every mood, top to bottom (lewd, very warm ... cool, grudge), each with
    dials in the middle of its cell and its face, idle moves and emote, as the
    portrait gets them: for the debug viewer's mood menu."""
    m = moods()
    grid = m.get("grid") or []
    words = (m.get("warmth") or {}).get("words") or []

    def middle(edges, i, n):
        lo = edges[i - 1] if i > 0 else -1.0
        hi = edges[i] if i < len(edges) else 1.0
        if i == 0:
            lo = max(-1.0, hi - 0.6)
        if i == n - 1:
            hi = min(1.0, lo + 0.6)
        return round((lo + hi) / 2, 2)

    e_edges = (m.get("energy") or {}).get("edges") or [-0.2, 0.35]
    w_edges = (m.get("warmth") or {}).get("edges") or [-0.2, 0.35, 0.66]
    energies = [middle(e_edges, j, len(e_edges) + 1) for j in range(len(e_edges) + 1)]
    rows = [("lewd", _extra("lewd")["row"], 0.95, "lewd")]
    for i in range(len(grid) - 1, -1, -1):
        rows.append((words[i] if i < len(words) else f"row {i}", grid[i], middle(w_edges, i, len(grid)), ""))
    rows.append(("grudge", _extra("grudge")["row"], -0.6, "grudge"))

    out = []
    for group, names, warmth, row in rows:
        for j, name in enumerate(names):
            spec = _state(name)
            out.append({"name": name, "group": group, "row": row, "warmth": warmth,
                        "energy": energies[min(j, len(energies) - 1)], "energy_step": j,
                        "face": dict(spec.get("face") or {}), "idle": [str(g) for g in spec.get("idle") or []],
                        "emote": str(spec.get("emote") or "")})
    return out


def _emote(name, sulking=False):
    """An emote name the portrait may show, or "" when emotes are off.
    While she's walked away only the sulk's own (walk_away.emote) shows:
    no hearts or question marks mid-sulk."""
    if not (config.MOOD_ENABLED and getattr(config, "MOOD_EMOTES", True)) or _intensity() <= 0:
        return ""

    if walkaway.away() and not sulking:
        return ""

    return str(name or "")


# ---------------------------------------------------------------------------
# Reading it back
# ---------------------------------------------------------------------------
# Hysteresis: a value has to clear the boundary by this much to change
# the band it's in. Without it the resting warmth sat a whisker above an
# edge and the header flickered between two labels every single turn.
_STICK = 0.07


def _band(value, edges, current=None):
    edges = list(edges)

    if current is not None:
        # Widen whichever band we are already in, so leaving one costs
        # more than staying in it. Band `current` sits between edge
        # `current - 1` below and edge `current` above: push every edge
        # at or above us up, and every edge below us down.
        for i, edge in enumerate(edges):
            edges[i] = edge + (_STICK if i >= current else -_STICK)

    for i, edge in enumerate(edges):
        if value < edge:
            return i

    return len(edges)


def _cell():
    """(label, phrasings) for where the dials are, sticky about changing."""

    data = moods()
    grid = data["grid"]
    current_row = next((i for i, row in enumerate(grid) if S.label in row), None)

    lewd, grudge = _extra("lewd"), _extra("grudge")
    if S.label in lewd["row"]:
        current_row = len(grid) - 1        # lewd sits on very warm: keep that band sticky
    elif S.label in grudge["row"]:
        current_row = 0

    warmth_band = _band(S.warmth, data["warmth"]["edges"], current_row)
    row = grid[warmth_band]

    if _grudging():
        row = list(grudge["row"])
    elif warmth_band == len(grid) - 1:
        enter = float(lewd.get("enter", 0.6))
        if S.desire >= enter or (S.label in lewd["row"] and S.desire >= enter - 0.1):
            row = list(lewd["row"])

    energy_band = _band(S.energy, data["energy"]["edges"],
                        row.index(S.label) if S.label in row else None)
    name = row[energy_band]
    phrases = list(_state(name).get("lines") or []) or [name]

    if name != S.label:
        # Rotate on arrival, so a mood she returns to doesn't sound the
        # same twice running. A random pick would have been simpler and
        # is worse: it can hand you the same sentence five times, which
        # is exactly the staleness the phrasings exist to avoid.
        S.label = name
        S.phrasing[name] = S.phrasing.get(name, -1) + 1

    return name, phrases[S.phrasing.get(name, 0) % len(phrases)]


# Plugins live somewhere lewd isn't allowed (twitch, youtube with
# "lewd": false). While any is, the lewd row shows as the row below it -
# teasing / frisky / heated as cuddly / loving / flirty - in her face,
# idles, voice, portrait and mood line. The dials and desire keep going
# underneath, so she's back where she was when the stream ends.


def set_tame(source, on):
    """A plugin saying lewd is (not) allowed where it's live."""
    with _lock:
        (S.tamed_by.add if on else S.tamed_by.discard)(source)

    _announce()


def tame():
    """The plugins holding the lewd row back right now, or an empty list."""
    return sorted(S.tamed_by)


def _view():
    """_cell(), as she shows it: the lewd row stepped down while tame."""
    name, described = _cell()
    lewd = _extra("lewd")["row"]

    if S.tamed_by and name in lewd:
        name = moods()["grid"][-1][lewd.index(name)]
        described = (_state(name).get("lines") or [name])[0]

    return name, described


def label():
    """One word for the header: 'happy', 'mad'."""
    if not config.MOOD_ENABLED:
        return ""

    if walkaway.away():
        return str(_walk().get("label") or "withdrawn")

    with _lock:
        return _view()[0]


def _public(name):
    """A mood marked private never colours a stream or Discord turn: the
    nearest one in the same row that isn't, or the middle of the grid."""
    if not _state(name).get("private"):
        return name

    grid = moods()["grid"]

    for row in grid:
        if name in row:
            at = row.index(name)
            for other in sorted(row, key=lambda n: abs(row.index(n) - at)):
                if not _state(other).get("private"):
                    return other

    middle = grid[len(grid) // 2]
    return middle[len(middle) // 2]


def line(private=True):
    """The line that goes into the system prompt, or "" when off.

    Phrased as a state of affairs rather than an instruction. "You are
    tired, act tired" produces a model narrating its own tiredness;
    "right now you feel tired and glad of the company" colours the
    voice and then gets out of the way.
    """
    if not (config.MOOD_ENABLED and getattr(config, "MOOD_PROMPT", True)):
        return ""

    # Walked away: the only turns that get here are the ones that ring on
    # their own - an alarm, a reminder. She delivers them, in character.
    if walkaway.away():
        said = str(_walk().get("prompt") or "").strip()

        if said:
            return f"\n{said}\n"

    with _lock:
        name, described = _view()

    if not private and _public(name) != name:
        lines = _state(_public(name)).get("lines") or [_public(name)]
        described = lines[0]

    user = getattr(config, "USER", "the user")

    row = _row_of(name)

    if row == "grudge":
        return (
            f"\nRight now you feel {described}: {user} was hostile and hasn't made up, and you're "
            "holding a grudge. Let it show - short, prickly, not warm. Grumble at requests; you "
            "may refuse what isn't urgent until you get an apology, but alarms, reminders, safety "
            "and anything urgent always get done. A real apology ends it: let it go.\n"
        )

    if row == "lewd":
        return (
            f"\nRight now you feel {described}. Let that colour how you sound and what you're "
            f"in the mood for. Don't announce it unasked. Practical requests still get done.\n"
        )

    not_now = ("" if name in moods()["grid"][-1] else
               " Pushed for sex or intimate roleplay now, you're not in the mood: say so your "
               "own way and hint at what would change that. No lecture.")

    return (
        f"\nRight now you feel {described}. Let that colour how you "
        "sound - length, warmth, how playful you are - and nothing "
        f"else. Don't announce it or explain it unasked; if {user} asks how "
        "you are, answer honestly and briefly. Never let it make you "
        f"less helpful or less careful.{not_now}\n"
    )


def voice_tint():
    """(speed multiplier, pitch shift in semitones) for the TTS.

    Small on purpose. The point is that a sleepy Luna sounds a little
    slower, not that the voice audibly breaks - anything past a few
    percent reads as a misconfigured setting rather than a mood.
    """
    if not (config.MOOD_ENABLED and config.MOOD_VOICE):
        return 1.0, 0.0

    with _lock:
        energy = S.energy
        name = _view()[0]

    # The mood's own tint from moods.json if it has one, else a little
    # slower when tired and quicker when wired, straight off the dial.
    voice = _state(name).get("voice") or {}
    speed = float(voice.get("speed", 1.0 + 0.07 * energy)) - 1.0
    pitch = float(voice.get("pitch", 0.45 * energy))
    k = _intensity()

    return 1.0 + max(-0.07, min(0.07, speed * k)), max(-0.45, min(0.45, pitch * k))


def face():
    """What the portrait shows for the current mood, scaled by intensity."""
    if not (config.MOOD_ENABLED and getattr(config, "MOOD_FACE", True)):
        return {}

    with _lock:
        name = _view()[0]

    k = min(1.0, _intensity())

    return {f: round(float(v) * k, 3) for f, v in (_state(name).get("face") or {}).items()}


def idle():
    """Gestures she drifts into now and then in this mood."""
    if not (config.MOOD_ENABLED and getattr(config, "MOOD_GESTURES", True)) or _intensity() <= 0:
        return []

    with _lock:
        name = _view()[0]

    return [str(g) for g in (_state(name).get("idle") or [])]


def emote():
    """An emote this mood shows now and then (loving, flirty: hearts)."""
    with _lock:
        name = _view()[0]

    return _emote(_state(name).get("emote"))


def state():
    """(label, energy, warmth, [recent reasons]) for /mood."""
    with _lock:
        return (
            _view()[0],
            round(S.energy, 2),
            round(S.warmth, 2),
            [why for why, _when in S.recent[-4:]],
        )


def layers():
    """{"desire": 0..1, "grudge": seconds left} for /mood and tests."""
    with _lock:
        return {"desire": round(S.desire, 2), "grudge": round(_grudging())}


def last_rating():
    """What the last message you sent scored, 0-3, or None.

    So "is the warmth sensing even firing?" is something you can look
    at rather than infer from a dial that barely moved.
    """
    with _lock:
        return S.last_rating


def bands():
    """(energy word, warmth word) - which band each dial is sitting in.

    /mood printed bare numbers, which is no help: '+0.66' does not tell
    you whether being nice to her is landing. Knowing it reads as 'fond,
    one band short of the top' does.
    """
    data = moods()

    def word(dial, value):
        words = list(data[dial].get("words") or [])
        band = _band(value, data[dial]["edges"])
        return words[band] if band < len(words) else f"band {band + 1}"

    with _lock:
        row = _row_of(_view()[0])
        return word("energy", S.energy), row or word("warmth", S.warmth)


def energy_step(name=None):
    """Her energy as a step, 0 (tired) .. 2 (wired): where her mood sits in its row
    (teasing, frisky, heated), so it agrees with the name she's showing even while
    the dial hovers near an edge; the dial's own band for anything not in a row."""
    data = moods()
    name = S.label if name is None else name
    for row in [(data.get("lewd") or {}).get("row"), (data.get("grudge") or {}).get("row"), *data.get("grid", [])]:
        if row and name in row:
            return row.index(name)
    return _band(S.energy, data["energy"]["edges"])


def portrait_state():
    """What the live monitor and the portrait get: the mood, the dials,
    its face and idle moves. With mood.face off she shows nothing - the
    dials go out as neutral so nothing else reads a mood off them."""
    name, energy, warmth, _why = state()
    show = config.MOOD_ENABLED and getattr(config, "MOOD_FACE", True) and _intensity() > 0

    if walkaway.away():
        spec = _walk()
        moves = config.MOOD_GESTURES and _intensity() > 0
        return {"label": str(spec.get("label") or "withdrawn"), "row": "", "energy": energy if show else 0.0,
                "warmth": warmth if show else 0.0,
                "face": dict(spec.get("face") or {}) if show else {}, "idle": [],
                "hold": str(spec.get("hold") or "") if moves else "",
                "emote": _emote(spec.get("emote"), sulking=True), "energy_step": energy_step("")}

    return {"label": name, "row": _row_of(name), "energy": energy if show else 0.0,
            "warmth": warmth if show else 0.0, "face": face() if show else {}, "idle": idle(),
            "hold": "", "emote": emote(), "tame": bool(S.tamed_by), "energy_step": energy_step(name)}


def _announce():
    try:
        import ui

        ui.set_mood(label())
    except Exception:
        pass  # headless, or the UI isn't up yet

    try:
        from web import livefeed

        livefeed.emit("mood", **portrait_state())
    except Exception:
        pass
