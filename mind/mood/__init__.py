"""What sort of shape she's in today.

The persona in agent.json is who she is; this is how she happens to be
feeling right now. It reaches the model as one line in the system
prompt and tints her voice slightly, and that is all. No rules about
how to behave: telling a 9B model to "act tired" gets you a
performance of tiredness in every sentence.

Two dials, both -1..+1:

    energy   tired ......... wired
    warmth   cross ......... fond

Two is enough for twelve distinguishable moods and few enough that every
signal has an obvious place to push. One dial can't tell "tired and
happy" from "awake and fed up", which are the two states that actually
turn up at 4am.

## Where it comes from

Almost all of it is the *shape* of the session, which is free and
turns out to be the more honest signal anyway:

    time of day        the baseline - 6am is not 9pm
    hours at it        a long session wears her down
    gap since you left away for hours, and she's brighter when you're back
    errors             a failed turn is dispiriting, a run of them more so
    a clean run        things going smoothly lifts her
    barge-in           being talked over, repeatedly, is wearing
    tempo              fast short turns read as engaged

plus one small model call after your turn that reads the exchange: how
warm you were, whether it livened her up or wore on her, and a quick
feeling (laughing, embarrassed...) that shows on her face for a moment.

## Three things learned the hard way

**It persists.** Moods that reset on restart aren't moods, they're
decoration - and this app gets restarted a lot. The dials are saved and
come back decayed by however long you were gone, so picking up after
five minutes resumes and picking up tomorrow doesn't.

**The label has hysteresis.** The bands sat close enough to the resting
point that a rounding-error nudge flipped her whole row, and the header
flickered between "warm" and "level" turn after turn. A label now has
to be clearly wrong before it changes.

**The wording varies.** The same sentence every turn is one a model
either stops seeing or starts performing. Each state has a few
phrasings and rotates when the state changes.

## What's data and what's code

The names, the lines she's told, her face, her voice and the idle moves
for each mood live in agent/moods.json, along with the quick feelings
the model can pick after a turn. Edit it and the next turn picks it up.
What stays in code is the engine and the rules below: those aren't a
matter of taste.

Two settings shape all of it: mood.intensity (0 = almost flat, the
ship's-computer end; 1 = as designed; 2 = wears her heart on her
sleeve) and mood.recovery (how fast she settles). mood.prompt,
mood.voice, mood.face and mood.gestures say where it shows.

## Past the edges of the grid

Two rows sit outside the warmth bands, each with its own way in and out:

    lewd     very warm AND desire past moods.json lewd.enter. Desire
             (0..1) only builds while she's warm - flirting, intimacy,
             touch - fades turn by turn and while you're away, and is
             wiped by hostility or by warmth falling below warm.
    grudge   real hostility while she's already cool. Holds for
             grudge.minutes (another insult restarts it); warmth can't
             climb out until you make up (an apology, clear warmth) or
             the time runs out.

Both are rows of three like the grid, picked by energy.

## What it never does

Moods colour how she sounds, not whether things get done. Outside a
grudge there is no state in which she is less useful. In a grudge she
grumbles and may turn down what isn't urgent until you make up -
never alarms, reminders, safety or anything urgent - and the walk-away
(three strikes) is still the only thing that stops her talking.

## The pieces

    core.py      her state (one object, S), its locks, the shared rules
    drift.py     the dials moving: baselines, drift, the session's shape
    exchange.py  what a turn did: warmth, desire, the grudge, feelings, spanks
    appraise.py  the one side question that reads how a turn landed
    walkaway.py  walking away and coming back
    show.py      reading it back: label, prompt line, voice, face, portrait
    saving.py    surviving a restart
    files.py     agent/moods.json, checked, with built-in moods if it's broken

Everything is re-exported here, so `mood.label()`, `mood.note_turn()` and the
rest work as they always did. The old loose values (`mood._warmth`...) read
and write S, for anything that still pokes them.
"""
import sys
import types

from mind.mood.core import (  # noqa: F401
    S,
    State,
    _away_lock,
    _ceiling,
    _clamp,
    _extra,
    _grudging,
    _intensity,
    _lock,
    _row_of,
    _settle,
    _state,
    _walk,
    _warm_enough,
    walk_away_on,
)
from mind.mood.files import (  # noqa: F401
    MOODS_FILE,
    _FALLBACK,
    _check,
    _moods,
    moods,
)
from mind.mood.appraise import (  # noqa: F401
    _APPRAISE_PROMPT,
    _RATING,
    _appraise,
    _parse_appraisal,
)
from mind.mood.saving import (  # noqa: F401
    STATE_FILE,
    _restore,
    _save,
)
from mind.mood.drift import (  # noqa: F401
    _BY_HOUR,
    _chat_shape,
    _day_shape,
    _energy_baseline,
    _machine_shape,
    _nudge,
    _returning,
    _sample_machine,
    _warmth_baseline,
    _watch_machine,
    note_bargein,
    note_denied,
    note_error,
    note_play,
    note_thanks,
    note_turn,
    reset,
    set_mood,
    start,
)
from mind.mood.exchange import (  # noqa: F401
    DESIRE_AFFECTION,
    DESIRE_FADE,
    DESIRE_FLIRT,
    HOSTILE_HIT,
    SPANK_DESIRE,
    SPANK_FORGET,
    SPANK_LIMIT,
    SPANK_WARMTH,
    _apply_exchange,
    _compliment,
    _feel,
    _layers,
    _make_up,
    last_feeling,
    note_affection,
    note_exchange,
    note_spank,
)
from mind.mood.walkaway import (  # noqa: F401
    _back,
    _count_hostility,
    _withdraw,
    away,
    heard_while_away,
    leaving_line,
)
from mind.mood.show import (  # noqa: F401
    _STICK,
    _announce,
    _band,
    _cell,
    _emote,
    _public,
    _view,
    bands,
    emote,
    face,
    idle,
    label,
    last_rating,
    layers,
    line,
    portrait_state,
    preview_list,
    set_tame,
    state,
    tame,
    voice_tint,
)
from mind.mood import core as _core

# The old loose values, kept as names for anything that still reads or sets
# them (mood._warmth = 0.5): they're S's fields now.
_OLD = {
    '_energy': 'energy',
    '_warmth': 'warmth',
    '_started': 'started',
    '_last_turn': 'last_turn',
    '_recent': 'recent',
    '_busy': 'busy',
    '_chat_seen': 'chat_seen',
    '_label': 'label',
    '_phrasing': 'phrasing',
    '_clean_run': 'clean_run',
    '_desire': 'desire',
    '_grudge_until': 'grudge_until',
    '_affection_recent': 'affection_recent',
    '_last_rating': 'last_rating',
    '_last_feeling': 'last_feeling',
    '_spanks': 'spanks',
    '_tame': 'tamed_by',
    '_away': 'away_state',
}


class _Mood(types.ModuleType):
    pass


for _old, _new in _OLD.items():
    setattr(_Mood, _old, property(lambda self, n=_new: getattr(_core.S, n),
                                  lambda self, v, n=_new: setattr(_core.S, n, v)))

sys.modules[__name__].__class__ = _Mood
