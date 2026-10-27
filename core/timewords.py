"""The clock and the words for time: now(), the part of the day, weekdays,
months, units and number words, shared by the parser and the describers.

Part of core/timeutil.py, which re-exports all of this.
"""
from datetime import datetime

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------
WEEKDAYS = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tue": 1, "tues": 1,
    "wednesday": 2, "wed": 2, "weds": 2,
    "thursday": 3, "thu": 3, "thur": 3, "thurs": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}

WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday",
                 "Friday", "Saturday", "Sunday"]

# Named sets of days, because "every weekday at 7" is the single most
# common alarm anyone sets and it is not a weekly repeat - it fires five
# times a week, which {"weekday": n} cannot express.
DAY_SETS = {
    "weekday": (0, 1, 2, 3, 4),
    "weekdays": (0, 1, 2, 3, 4),
    "workday": (0, 1, 2, 3, 4),
    "workdays": (0, 1, 2, 3, 4),
    "weekend": (5, 6),
    "weekends": (5, 6),
}

MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}

UNITS = {
    "second": "seconds", "seconds": "seconds", "sec": "seconds",
    "secs": "seconds", "s": "seconds",
    "minute": "minutes", "minutes": "minutes", "min": "minutes",
    "mins": "minutes", "m": "minutes",
    "hour": "hours", "hours": "hours", "hr": "hours", "hrs": "hours",
    "h": "hours",
    "day": "days", "days": "days", "d": "days",
    "week": "weeks", "weeks": "weeks", "wk": "weeks", "wks": "weeks",
    "month": "months", "months": "months",
    "year": "years", "years": "years",
}

# Spelled-out counts. People say "in a couple hours" far more often than
# they say "in 2 hours", and a model transcribing speech passes it
# through verbatim.
WORD_NUMBERS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40,
    "forty-five": 45, "fortyfive": 45, "sixty": 60, "ninety": 90,
    "half": 0.5, "couple": 2, "few": 3, "several": 3, "dozen": 12,
}

# Vague times of day, resolved to something specific. Picking a concrete
# hour is better than refusing: "remind me tonight" should produce a
# reminder at 20:00, not an error message.
DAY_PARTS = {
    "morning": (9, 0),
    "noon": (12, 0),
    "midday": (12, 0),
    "lunch": (12, 30),
    "lunchtime": (12, 30),
    "afternoon": (14, 0),
    "evening": (18, 0),
    "dinner": (18, 30),
    "dinnertime": (18, 30),
    "tonight": (20, 0),
    "night": (20, 0),
    "bed": (22, 0),
    "bedtime": (22, 0),
    "midnight": (0, 0),
}


# ---------------------------------------------------------------------------
# Now
# ---------------------------------------------------------------------------
def now():
    return datetime.now()


def day_part(moment=None):
    """Which part of the day it is, in the words a person would use."""
    hour = (moment or now()).hour

    if hour < 5:
        return "the middle of the night"
    if hour < 12:
        return "morning"
    if hour < 17:
        return "afternoon"
    if hour < 21:
        return "evening"

    return "night"
