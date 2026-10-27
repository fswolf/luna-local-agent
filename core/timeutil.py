"""Everything that knows what time it is.

Three different places used to answer "when": tools.get_datetime built
its own string, life/reminders.py did its own clock arithmetic, and llm.py
stamped history with isoformat(). They agreed with each other by
accident, and a small model saw three different formats for the same
concept.

Two ideas run through this whole file:

  * The model never does arithmetic. It repeats the words the user
    actually said - "next tuesday at 9", "in half an hour" - and
    parse_when() turns that into a datetime here, in Python. Asking a
    9B model for "2 days in minutes" is asking it to be wrong.

  * Time shown to the model is relative. "17 minutes ago" is something
    a small model reads correctly; "2026-09-19T14:32:07" is something
    it has to subtract, badly, before it can use it.

Everything here is naive local time, the same as datetime.now(). Making
it timezone-aware would mean every stored reminder written before the
change compares as a different type, for no benefit on a machine that
lives in one timezone. The timezone name is reported to the model as
information, not carried around as state - and daily repeats recompute
from the wall clock rather than adding 24 hours, which is where the
DST bug would actually have bitten.

This file shows time to the model (describe_now, relative, friendly,
stamp). The rest is beside it and re-exported, so `timeutil.X` still works:

    core/timewords.py   now(), parts of the day, weekday, month and number words
    core/timeparse.py   parse_when() and next_occurrence(): words into datetimes
"""
import time as _time
from datetime import timedelta
from core.timewords import WEEKDAY_NAMES, day_part, now
from core.timewords import (  # noqa: F401  re-exported: timeutil.X keeps working
    DAY_PARTS,
    DAY_SETS,
    MONTHS,
    UNITS,
    WEEKDAYS,
    WORD_NUMBERS,
)
from core.timeparse import (  # noqa: F401  re-exported: timeutil.X keeps working
    _FILLER,
    _MORNING,
    _add_months,
    _at_wall_clock,
    _bare,
    _clean,
    _clock,
    _day_set,
    _day_set_repeat,
    _delta,
    _hm,
    _number,
    _resolve_date,
    _resolve_once,
    _resolve_repeat,
    _shift_pm,
    _step,
    _time_or_part,
    next_in_days,
    next_occurrence,
    next_weekday,
    parse_when,
)


def timezone_label():
    """'America/New_York (UTC-04:00)', or as close as the machine knows.

    time.tzname only gives the abbreviation ('EDT'), which is ambiguous
    worldwide, so the IANA name is read from the environment or
    /etc/localtime when it's there.
    """
    import os

    name = os.environ.get("TZ") or ""

    if not name:
        try:
            link = os.path.realpath("/etc/localtime")

            if "zoneinfo/" in link:
                name = link.split("zoneinfo/", 1)[1]
        except OSError:
            pass

    if not name:
        name = _time.tzname[_time.daylight and _time.localtime().tm_isdst > 0]

    offset = -(_time.altzone if _time.localtime().tm_isdst > 0 else _time.timezone)
    sign = "+" if offset >= 0 else "-"
    hours, minutes = divmod(abs(offset) // 60, 60)

    return f"{name} (UTC{sign}{hours:02d}:{minutes:02d})"


def describe_now(moment=None):
    """The block handed to the model by get_datetime().

    Deliberately more than the bare clock: a model that only has
    "14:32" still can't answer "what day is it next Friday", and if it
    tries it will guess. Everything it might need to reason about a
    date is spelled out so it never has to compute one.
    """
    moment = moment or now()
    tomorrow = moment + timedelta(days=1)

    return "\n".join([
        moment.strftime("%A %d %B %Y, %H:%M") + f" ({day_part(moment)})",
        f"Timezone: {timezone_label()}",
        f"Today is {moment.strftime('%A')}; tomorrow is "
        f"{tomorrow.strftime('%A %d %B')}.",
        f"ISO date {moment.strftime('%Y-%m-%d')}, week "
        f"{moment.isocalendar()[1]} of {moment.year}.",
    ])


# ---------------------------------------------------------------------------
# Formatting for humans (and for small models, which read the same way)
# ---------------------------------------------------------------------------
def relative(target, reference=None):
    """'in 20 minutes', '3 hours ago', 'just now'.

    Rounded and worded, not precise - this exists so nobody, model or
    person, has to subtract two timestamps in their head.
    """
    reference = reference or now()
    seconds = (target - reference).total_seconds()
    future = seconds >= 0
    seconds = abs(seconds)

    if seconds < 45:
        return "in a moment" if future else "just now"

    if seconds < 90:
        amount = "a minute"
    elif seconds < 3600:
        amount = f"{round(seconds / 60)} minutes"
    elif seconds < 5400:
        amount = "an hour"
    elif seconds < 21600:
        # Half hours are worth saying up to about six hours out, and
        # noise after that - nobody needs "in 12.5 hours".
        hours = round(seconds / 1800) / 2
        amount = f"{hours:g} hours"
    elif seconds < 86400:
        amount = f"{round(seconds / 3600)} hours"
    elif seconds < 129600:
        # Up to a day and a half. Not 48h: "in 2 days" stored to
        # second precision measures a hair under two days by the time
        # it's read back, and reading out as "a day" was just wrong.
        amount = "a day"
    elif seconds < 1209600:
        amount = f"{round(seconds / 86400)} days"
    elif seconds < 5184000:
        amount = f"{round(seconds / 604800)} weeks"
    else:
        amount = f"{round(seconds / 2592000)} months"

    return f"in {amount}" if future else f"{amount} ago"


def friendly(target, reference=None):
    """'today 14:32', 'tomorrow 09:00', 'Monday 09:00', 'Mon 22 Sep 09:00'.

    Named days inside the coming week, because "Monday 9am" is how the
    reminder was asked for and how it should be read back - and because
    it survives being spoken aloud, which '2026-09-22T09:00' does not.
    """
    reference = reference or now()
    days = (target.date() - reference.date()).days
    clock = target.strftime("%H:%M")

    if days == 0:
        return f"today {clock}"
    if days == 1:
        return f"tomorrow {clock}"
    if days == -1:
        return f"yesterday {clock}"
    if 2 <= days <= 6:
        return f"{target.strftime('%A')} {clock}"
    if -6 <= days <= -2:
        return f"last {target.strftime('%A')} {clock}"

    if target.year == reference.year:
        return target.strftime("%a %d %b ") + clock

    return target.strftime("%a %d %b %Y ") + clock


def stamp(target, reference=None):
    """The prefix on a history message: 'today 14:32, 17 minutes ago'.

    Both halves earn their place. The relative half is what the model
    actually reasons with; the absolute half is what lets it answer
    "what time did I say that" without another tool call.
    """
    reference = reference or now()

    return f"{friendly(target, reference)}, {relative(target, reference)}"


def describe_repeat(repeat):
    if not repeat:
        return ""

    if repeat.get("days"):
        days = sorted(set(repeat["days"]))
        at = repeat.get("at", "?")

        # "every weekday" rather than a five-name list, because this is
        # spoken aloud and nobody says Monday-Tuesday-Wednesday-Thursday-
        # Friday out loud.
        if days == [0, 1, 2, 3, 4]:
            return f"every weekday at {at}"

        if days == [5, 6]:
            return f"every weekend day at {at}"

        names = [WEEKDAY_NAMES[d] for d in days]

        return "every {} and {} at {}".format(
            ", ".join(names[:-1]), names[-1], at
        )

    if repeat.get("weekday") is not None:
        return f"every {WEEKDAY_NAMES[repeat['weekday']]} at {repeat.get('at', '?')}"

    if repeat.get("unit"):
        amount = repeat["amount"]
        amount = f"{amount:g}"
        unit = repeat["unit"]

        return f"every {amount} {unit}" if amount != "1" else f"every {unit[:-1]}"

    return f"every day at {repeat.get('at', '?')}"
