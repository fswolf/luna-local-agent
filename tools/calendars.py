"""Your calendars, read-only (senses/calendars.py): Google Calendar through its
secret iCal link, calcurse, any iCal feed. One tool, in the Time group.

Yours alone: on a guest's turn, in stream chat, Discord or a job it says no,
even if a model names it without being offered it.
"""
import re
from datetime import date, timedelta

from . import OUTSIDE, tool

_DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


# Event titles are written by whoever made the event, and a calendar takes
# invitations from strangers (Google adds them unasked): what this returns
# counts as someone else's words, like a web page (tools.OUTSIDE).
OUTSIDE.add("calendar")


def _yours():
    """'' on your own turn, else why not."""
    from core import turnctx

    turn = turnctx.current()
    if not turn.private or turn.speaker or turn.remote or turn.job:
        return "Your calendar is only for the person it belongs to, on their own turns."
    return ""


def _day(words, today=None):
    """(first day, how many days it means) from 'today', 'tomorrow', 'friday',
    'this week', 'next week', '2026-12-03', or anything set_reminder reads as
    a day ('december 3', 'in 3 days'); (None, 0) if not a day at all.

    A weekday is today when it's today: on a Monday, "monday" asks about
    today's calendar. Scheduling a reminder reads it as next week instead,
    which is right for that and wrong here."""
    today = today or date.today()
    w = " ".join(str(words or "").lower().replace("this coming", "this").split())
    if w in ("", "today", "now", "tonight"):
        return today, 1
    if w == "tomorrow":
        return today + timedelta(days=1), 1
    if w == "yesterday":
        return today - timedelta(days=1), 1
    if w in ("this week", "the week", "week"):
        return today, 7
    if w == "next week":
        return today + timedelta(days=7 - today.weekday()), 7      # Monday to Sunday
    if w in ("this weekend", "the weekend", "weekend"):
        if today.weekday() == 6:                                        # Sunday: what's left of it
            return today, 1
        return today + timedelta(days=5 - today.weekday()), 2          # Saturday and Sunday (or today, a Saturday)
    try:
        return date.fromisoformat(w), 1
    except ValueError:
        pass
    m = re.fullmatch(r"(next |this )?(" + "|".join(_DAYS) + r")", w)
    if m:
        ahead = (_DAYS.index(m.group(2)) - today.weekday()) % 7
        if m.group(1) == "next " and ahead == 0:
            ahead = 7
        return today + timedelta(days=ahead), 1
    from core import timeutil

    moment, _repeat = timeutil.parse_when(w)
    return (moment.date(), 1) if moment is not None else (None, 0)


def _available():
    from senses import calendars

    return calendars.enabled()


@tool(
    "calendar",
    "Read the user's own calendar (Google Calendar, calcurse): what's on a day or a "
    "stretch of days, whether they're free, or when something is. Use it before saying "
    "what's planned. Read-only: it can't add or change events - for 'remind me', use "
    "set_reminder.",
    {
        "day": {"type": "string",
                "description": "Which day: 'today', 'tomorrow', a weekday ('friday'), 'this week', "
                               "'next week', 'december 3' or YYYY-MM-DD. Default today."},
        "days": {"type": "integer", "description": "How many days from that day, 1 to 31. Leave it out for "
                                                    "the day (or the week, for a week)."},
        "search": {"type": "string",
                   "description": "Find an event by words in its title or place ('dentist') over the next "
                                  "year, instead of a day."},
    },
    available=_available,
    why=lambda: "no calendar set up (calendar.enabled, calendar.google / calendar.ics / calendar.calcurse)",
)
def _calendar(day="today", days=1, search=""):
    no = _yours()
    if no:
        return no
    from senses import calendars

    search = " ".join(str(search or "").split())[:80]
    when, means = _day(day)
    if when is None and not search:
        return f"{day!r} isn't a day I can read: try today, tomorrow, a weekday, next week or YYYY-MM-DD."
    try:
        n = int(days) if days not in (None, "", 1, "1") else means      # "next week" means seven unless she says
    except (TypeError, ValueError):
        n = means
    return calendars.agenda(when or date.today(), max(1, min(31, n or 1)), search)
