"""Her moods (mind/mood.py): on/off, how far they swing, where they show,
walking away.

Part of the config package (it was one config.py); see config/__init__.py.
"""
from .base import flag, number, setting

# How she happens to be feeling - see mind/mood.py. Colours tone only, mostly
# from free signals (clock, session length, errors, barge-ins), plus one
# small model call after your turn (mood.affection). The names, lines,
# faces and voices of the moods themselves are in agent/moods.json.
#   "mood": { "enabled": true, "intensity": 1, "warmth": 0.45, "recovery": 0.25 }
_mood_cfg = setting("mood", {})
MOOD_ENABLED = flag(_mood_cfg.get("enabled", True))
# Where warmth settles when nothing is pushing it - the resting state
# she drifts back to.
# 0.45 rather than 0.40: the label bands break at 0.35, and resting a
# hair above an edge made the header flicker between two moods.
MOOD_WARMTH = number(_mood_cfg, "warmth", 0.45)
# How hard each turn pulls both dials home. 0 = moods never fade,
# 1 = nothing persists past a single turn.
MOOD_RECOVERY = number(_mood_cfg, "recovery", 0.25)
# Whether the mood also tints the voice - a sleepy Luna a few percent
# slower and lower. Small by design; see mood.voice_tint.
MOOD_VOICE = flag(_mood_cfg.get("voice", True))
# Whether being kind to her registers. It's the one mood signal that
# costs a model call - a small one, on a worker, after the turn - so
# it's the one worth being able to switch off.
MOOD_AFFECTION = flag(_mood_cfg.get("affection", True))
# How far her moods swing and how strongly they show: 0 = almost flat
# (the ship's computer end), 1 = as designed, 2 = very visibly emotional.
MOOD_INTENSITY = number(_mood_cfg, "intensity", 1.0, 0.0, 2.0)
# The two directions, apart. hurt: how hard a hostile message lands (2 =
# twice the old drop, so two insults take her from very warm to cold and
# angry). forgive: how fast she warms back up from below her resting
# warmth, by drift and by kind words alike (0.5 = half as fast as before;
# above her resting warmth, kind words count in full).
MOOD_HURT = number(_mood_cfg, "hurt", 2.0, 0.0, 4.0)
MOOD_FORGIVE = number(_mood_cfg, "forgive", 0.5, 0.05, 1.0)
# Winding down with time, talking or not (mind/mood/drift.py _decay), in
# minutes for half of it to go: warmth above her resting point and energy
# away from the hour's (settle), and desire.
MOOD_SETTLE_MINUTES = number(_mood_cfg, "settle_minutes", 45, 1.0)
MOOD_DESIRE_MINUTES = number(_mood_cfg, "desire_minutes", 20, 1.0)
# Where the mood shows. voice (above) is one; these are the others.
MOOD_PROMPT = flag(_mood_cfg.get("prompt", True))      # the line in her system prompt
MOOD_FACE = flag(_mood_cfg.get("face", True))          # the portrait's face and quick feelings
MOOD_GESTURES = flag(_mood_cfg.get("gestures", True))  # idle moves and feeling gestures
MOOD_EMOTES = flag(_mood_cfg.get("emotes", True))      # hearts beside her head (agent/moods.json "emote")
# Walking away: treated with real hostility a few exchanges running, she
# stops talking for a while (alarms, reminders and stop words still
# work). On by default; agent/moods.json has her lines and face.
MOOD_WALK_AWAY = flag(_mood_cfg.get("walk_away", True))
MOOD_WALK_AWAY_AFTER = int(number(_mood_cfg, "walk_away_after", 3, 1))   # hostile exchanges
MOOD_WALK_AWAY_MINUTES = number(_mood_cfg, "walk_away_minutes", 10, 0.0)

