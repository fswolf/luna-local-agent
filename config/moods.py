"""Her moods (mood.py): on/off, how far they swing, where they show,
walking away.

Part of the config package (it was one config.py); see config/__init__.py.
"""
from .base import setting

# How she happens to be feeling - see mood.py. Colours tone only, mostly
# from free signals (clock, session length, errors, barge-ins), plus one
# small model call after your turn (mood.affection). The names, lines,
# faces and voices of the moods themselves are in agent/moods.json.
#   "mood": { "enabled": true, "intensity": 1, "warmth": 0.45, "recovery": 0.25 }
_mood_cfg = setting("mood", {})
MOOD_ENABLED = bool(_mood_cfg.get("enabled", True))
# Where warmth settles when nothing is pushing it - the resting state
# she drifts back to.
# 0.45 rather than 0.40: the label bands break at 0.35, and resting a
# hair above an edge made the header flicker between two moods.
MOOD_WARMTH = float(_mood_cfg.get("warmth", 0.45))
# How hard each turn pulls both dials home. 0 = moods never fade,
# 1 = nothing persists past a single turn.
MOOD_RECOVERY = float(_mood_cfg.get("recovery", 0.25))
# Whether the mood also tints the voice - a sleepy Luna a few percent
# slower and lower. Small by design; see mood.voice_tint.
MOOD_VOICE = bool(_mood_cfg.get("voice", True))
# Whether being kind to her registers. It's the one mood signal that
# costs a model call - a small one, on a worker, after the turn - so
# it's the one worth being able to switch off.
MOOD_AFFECTION = bool(_mood_cfg.get("affection", True))
# How far her moods swing and how strongly they show: 0 = almost flat
# (the ship's computer end), 1 = as designed, 2 = very visibly emotional.
MOOD_INTENSITY = max(0.0, min(2.0, float(_mood_cfg.get("intensity", 1.0))))
# Where the mood shows. voice (above) is one; these are the others.
MOOD_PROMPT = bool(_mood_cfg.get("prompt", True))      # the line in her system prompt
MOOD_FACE = bool(_mood_cfg.get("face", True))          # the portrait's face and quick feelings
MOOD_GESTURES = bool(_mood_cfg.get("gestures", True))  # idle moves and feeling gestures
MOOD_EMOTES = bool(_mood_cfg.get("emotes", True))      # hearts beside her head (agent/moods.json "emote")
# Walking away: treated with real hostility a few exchanges running, she
# stops talking for a while (alarms, reminders and stop words still
# work). On by default; agent/moods.json has her lines and face.
MOOD_WALK_AWAY = bool(_mood_cfg.get("walk_away", True))
MOOD_WALK_AWAY_AFTER = int(_mood_cfg.get("walk_away_after", 3))        # hostile exchanges
MOOD_WALK_AWAY_MINUTES = float(_mood_cfg.get("walk_away_minutes", 10))

