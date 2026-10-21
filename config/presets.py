"""Presets: a few settings changed together, for what you mostly want her
for. Applied from the web settings page or /preset <name>; each value is
saved to config.json like any other change, so a preset is a starting
point, not a mode, and anything it set can be changed after.
"""

PRESETS = {
    "assistant": {
        "label": "Assistant",
        "about": "Calm and to the point: moods turned down, no sulking, no emotes. A capable helper first.",
        "values": {
            "mood.enabled": True, "mood.intensity": 0.3, "mood.walk_away": False,
            "mood.emotes": False, "mood.affection": False, "mood.voice": False,
            "portrait.touch_talk": False, "situation.enabled": True, "self.greet": True,
        },
    },
    "companion": {
        "label": "Companion",
        "about": "Luna as designed: moods that move, a voice that follows them, emotes, and the right to walk away.",
        "values": {
            "mood.enabled": True, "mood.intensity": 1.0, "mood.walk_away": True,
            "mood.emotes": True, "mood.affection": True, "mood.voice": True,
            "portrait.touch_talk": True, "self.greet": True,
        },
    },
    "streamer": {
        "label": "Streamer",
        "about": "Lively on camera: a bit more expressive, chat can set off gestures, nothing lewd while live.",
        "values": {
            "mood.enabled": True, "mood.intensity": 1.2, "mood.walk_away": True,
            "mood.emotes": True, "mood.voice": True, "portrait.chat_gestures": True,
            "plugins.twitch.lewd": False, "plugins.youtube.lewd": False,
        },
    },
}


def apply(name):
    """Save every value of a preset. Returns [(path, value, live)]; raises
    KeyError for an unknown preset."""
    import config

    preset = PRESETS[name]
    done = []

    for path, value in preset["values"].items():
        raw = ("true" if value else "false") if isinstance(value, bool) else str(value)
        saved, live = config.save_any(path, raw)
        done.append((path, saved, live))

    return done
