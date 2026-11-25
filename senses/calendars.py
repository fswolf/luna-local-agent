"""Your calendars, read-only: Google Calendar (its secret iCal link), calcurse,
and anything else that publishes iCal.

    "calendar": {
        "enabled": false,
        "google": "",           # Google Calendar's "Secret address in iCal format" (Settings ->
                                #   your calendar -> Integrate calendar); a password, kept masked
        "ics": [],              # any other iCal links or files: a holidays feed, a shared
                                #   family calendar, ~/cal/work.ics...
        "calcurse": false,      # read calcurse on this PC (calcurse --export=ical)
        "refresh_minutes": 30   # how often they're read again, while she's in use
    }

Each calendar is read in the background, at most every refresh_minutes, and
kept in memory; a turn never waits on a slow server, only the calendar tool
(asked outright) waits for a first read. Only while she's in use: a read is
started by a turn (its live details, its offer) or the tool, so a Luna nobody
is talking to doesn't poll Google all night. Repeating events (a weekly call, a
birthday) are expanded properly, times come out in your local time, an
all-day event is a date, and a cancelled one is left out.

What she does with it:

    calendar tool     "what's on tomorrow?", "am I free Friday?", "when's the dentist?"
    situation block   today's events, or the next one (mind/situation.py), so she
                      knows the day without being asked; her hello sees it too
    offers            an event in the next two days with no reminder from you and
                      none of its own gets offered a reminder (life/offers.py)

Read-only, for good: nothing here writes to a calendar. And yours alone: a
guest's turn, stream chat, Discord and jobs never see it.

    /calendar           the next seven days, and where each calendar stands
    /calendar refresh   read them again now

A Google secret link is a password to your calendar: it lives in your
config.json (never in git), and it's never logged or shown; status names
a link by its host.
"""
import os
import re
import shutil
import subprocess
import threading
import time
from datetime import date, datetime, timedelta
from urllib.parse import urlparse

import config
from core import logbook

DEFAULTS = {"enabled": False, "google": "", "ics": [], "calcurse": False, "refresh_minutes": 30}
TIMEOUT = 20                  # seconds for one calendar to answer
MAX_BYTES = 20 * 1024 * 1024  # a calendar bigger than this isn't read
WAIT_FIRST = 25               # seconds the tool waits for a first read

_lock = threading.Lock()
_cache = {}                   # source key -> {"cal": Calendar or None, "at": time, "error": str, "name": str}
_reading = {"busy": False, "at": 0.0}


def settings():
    out = dict(DEFAULTS)
    for k in DEFAULTS:
        v = config.current(f"calendar.{k}")
        if v is not None:
            out[k] = v
    return out


def enabled():
    return bool(settings()["enabled"]) and bool(sources())


def available():
    """The two packages it reads iCal with."""
    try:
        import icalendar  # noqa: F401
        import recurring_ical_events  # noqa: F401
        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Where the calendars are
# ---------------------------------------------------------------------------
def sources():
    """[(key, kind, where)]: ("ics", link) for Google and each "ics" entry,
    and ("calcurse", "") when calcurse is on."""
    s = settings()
    ics = s["ics"]
    if isinstance(ics, str):
        ics = [ics]
    out = []
    for item in [s["google"]] + (ics if isinstance(ics, list) else []):
        where = str(item or "").strip()
        if where:
            out.append((f"ics:{where}", "ics", where))
    if s["calcurse"]:
        out.append(("calcurse", "calcurse", ""))
    return out


def shown(kind, where):
    """A calendar's name for status lines: never a secret link itself."""
    if kind == "calcurse":
        return "calcurse"
    if re.match(r"(?i)^(https?|webcal)://", where):
        host = urlparse(where).hostname or "a link"
        return "Google Calendar" if host.endswith("google.com") else host
    return os.path.basename(os.path.expanduser(where)) or where


def _fetch_ics(where):
    """The text of one iCal link or file."""
    if re.match(r"(?i)^webcal://", where):
        where = "https://" + where[len("webcal://"):]
    if re.match(r"(?i)^https?://", where):
        import requests

        with requests.get(where, timeout=TIMEOUT, stream=True,
                          headers={"User-Agent": "Luna (calendar, read-only)"}) as r:
            r.raise_for_status()
            body = r.raw.read(MAX_BYTES + 1, decode_content=True)
        if len(body) > MAX_BYTES:
            raise ValueError("it's over 20 MB")
        # iCal is UTF-8 by its spec; requests' guess for a text/* reply with no
        # charset is Latin-1, which turns every accent and emoji into mojibake
        return body.decode("utf-8", errors="replace")
    path = os.path.expanduser(where)
    if os.path.getsize(path) > MAX_BYTES:
        raise ValueError("it's over 20 MB")
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def _fetch_calcurse():
    """calcurse's appointments and events as iCal, read-only."""
    exe = shutil.which("calcurse")
    if not exe:
        raise FileNotFoundError("calcurse isn't installed (or isn't on the PATH)")
    first = ""
    # --export=ical, not "-x ical": -x's format is an optional argument, so a
    # separate word is read as something else and calcurse refuses the lot
    # ("invalid argument combination"). Older calcurse has no --read-only.
    for args in (["--read-only", "--export=ical"], ["--export=ical"]):
        r = subprocess.run([exe, *args], capture_output=True, text=True, timeout=TIMEOUT,
                           stdin=subprocess.DEVNULL)
        if r.returncode == 0 and "BEGIN:VCALENDAR" in r.stdout:
            return r.stdout
        said = (r.stderr or r.stdout or f"exit {r.returncode}").strip().splitlines()
        first = first or (said[-1] if said else "")
    raise RuntimeError(f"calcurse said: {first[:200]}")


def _parse(text):
    import icalendar

    return icalendar.Calendar.from_ical(text)


def _read_one(key, kind, where):
    try:
        text = _fetch_calcurse() if kind == "calcurse" else _fetch_ics(where)
        cal = _parse(text)
        name = str(cal.get("X-WR-CALNAME") or "").strip() or shown(kind, where)
        entry = {"cal": cal, "at": time.time(), "error": "", "name": name[:60]}
    except Exception as e:
        # the reason, never the link: a Google link is a password
        # any link in it goes (an error can carry the link re-encoded: %40 for @)
        why = re.sub(r"(?i)\b(?:https?|webcal)://\S+", shown(kind, where), str(e))
        logbook.info("calendar", "reading %s failed: %s", shown(kind, where), why[:200])
        with _lock:
            old = _cache.get(key) or {}
        # keep the last good copy: a server down for a minute isn't an empty week
        entry = {"cal": old.get("cal"), "at": time.time(), "error": why[:200] or type(e).__name__,
                 "name": old.get("name") or shown(kind, where)}
    with _lock:
        _cache[key] = entry


def refresh(wait=False):
    """Read every calendar again, in the background (wait=True: here, now)."""
    with _lock:
        if _reading["busy"]:
            busy = True
        else:
            busy = False
            _reading["busy"] = True
    if busy:
        if wait:
            _wait_idle(WAIT_FIRST)
        return

    def run():
        try:
            want = sources()
            for key, kind, where in want:
                _read_one(key, kind, where)
            keep = {k for k, _kind, _w in want}
            with _lock:
                for gone in set(_cache) - keep:          # one taken out of the settings
                    _cache.pop(gone, None)
        finally:
            with _lock:
                _reading.update(busy=False, at=time.time())

    if wait:
        run()
    else:
        threading.Thread(target=run, daemon=True, name="calendar").start()


def _wait_idle(seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        with _lock:
            if not _reading["busy"]:
                return
        time.sleep(0.1)


def _stale():
    minutes = settings()["refresh_minutes"]
    try:
        minutes = max(1.0, float(minutes))
    except (TypeError, ValueError):
        minutes = float(DEFAULTS["refresh_minutes"])
    with _lock:
        have = set(_cache)
        last = _reading["at"]
    return have != {k for k, _kind, _w in sources()} or time.time() - last >= minutes * 60


def _fresh(wait):
    """Read again if it's time. wait: block for a first read (the tool asked)."""
    if not enabled() or not available():
        return
    if _stale():
        with _lock:
            never = not _cache
        refresh(wait=wait and never)


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------
def _local(value):
    """A DTSTART/DTEND value as a naive local datetime, or a date for all-day."""
    if isinstance(value, datetime):
        return value.astimezone().replace(tzinfo=None) if value.tzinfo else value
    return value


def _event(component, calendar):
    start = component.get("DTSTART")
    if start is None:
        return None
    start = _local(start.dt)
    end = component.get("DTEND")
    if end is not None:
        end = _local(end.dt)
    elif component.get("DURATION") is not None:
        end = start + component.get("DURATION").dt
    else:
        end = start + (timedelta(days=1) if not isinstance(start, datetime) else timedelta(0))
    all_day = not isinstance(start, datetime)
    return {"title": " ".join(str(component.get("SUMMARY") or "(no title)").split())[:160],
            "where": " ".join(str(component.get("LOCATION") or "").split())[:120],
            "start": start, "end": end, "all_day": all_day, "calendar": calendar,
            "uid": str(component.get("UID") or ""),
            "alarm": any(sub.name == "VALARM" for sub in component.subcomponents)}


def _sort_key(e):
    s = e["start"]
    return (datetime.combine(s, datetime.min.time()) if e["all_day"] else s, not e["all_day"], e["title"])


def events(start, end, wait=False):
    """Every event overlapping [start, end) from every calendar, in order.
    start, end: datetimes (local). wait: a first read may happen here."""
    _fresh(wait)
    import recurring_ical_events

    # Bounds in local time, with the zone on: naive ones were compared with a
    # UTC event as if they were UTC too, so in Alberta anything after 5pm on
    # the last day asked for (Google writes times in UTC) fell out of the range
    start, end = (t.astimezone() if isinstance(t, datetime) and t.tzinfo is None else t for t in (start, end))
    with _lock:
        cals = [(c["cal"], c["name"]) for c in _cache.values() if c.get("cal") is not None]
    out, seen = [], set()
    for cal, name in cals:
        try:
            found = recurring_ical_events.of(cal).between(start, end)
        except Exception as e:
            logbook.info("calendar", "expanding %s failed: %s", name, e)
            continue
        for component in found:
            if component.name != "VEVENT" or str(component.get("STATUS") or "").upper() == "CANCELLED":
                continue
            e = _event(component, name)
            if not e:
                continue
            same = (e["title"].lower(), str(e["start"]))      # one event in two calendars: once
            if same in seen:
                continue
            seen.add(same)
            out.append(e)
    return sorted(out, key=_sort_key)


def errors():
    """[(name, why)] for calendars whose last read failed."""
    with _lock:
        return [(c["name"], c["error"]) for c in _cache.values() if c.get("error")]


# ---------------------------------------------------------------------------
# In words
# ---------------------------------------------------------------------------
def _day_word(day, today):
    if day == today:
        return "today"
    if day == today + timedelta(days=1):
        return "tomorrow"
    if 0 < (day - today).days < 7:
        return f"{day:%A}"
    return f"{day:%a %b} {day.day}"


def _clock(t):
    return t.strftime("%H:%M")


def describe(e, today=None, with_day=True):
    """'tomorrow 15:00-16:00 dentist (Main St)', 'Fri, all day: Shannon's birthday'."""
    today = today or date.today()
    s = e["start"]
    day = s if e["all_day"] else s.date()
    when = _day_word(day, today) if with_day else ""
    if e["all_day"]:
        span = (e["end"] - e["start"]).days if isinstance(e["end"], date) else 1
        last = day + timedelta(days=max(1, span) - 1)
        time_part = "all day" + (f" until {_day_word(last, today)}" if span > 1 else "")
    else:
        end = e["end"]
        if isinstance(end, datetime) and end.date() != s.date():       # runs past midnight
            time_part = f"{_clock(s)} until {_day_word(end.date(), today)} {_clock(end)}"
        else:
            time_part = _clock(s) + (f"-{_clock(end)}" if isinstance(end, datetime) and end > s else "")
    head = f"{when} {time_part}".strip()
    return f"{head}: {e['title']}" + (f" ({e['where']})" if e["where"] else "")


def situation_line(now=None):
    """Today's events still to come (and the next one when there are none),
    for the situation block. Never waits on a read; "" when there's nothing."""
    if not enabled() or not available():
        return ""
    now = now or datetime.now()
    today = now.date()
    try:
        found = events(datetime.combine(today, datetime.min.time()), now + timedelta(days=7))
    except Exception:
        return ""
    # still on today: started by the end of today (last night's, running past
    # midnight, too) and not over yet
    tomorrow = datetime.combine(today + timedelta(days=1), datetime.min.time())
    left = [e for e in found if (e["all_day"] and e["start"] <= today) or
            (not e["all_day"] and e["start"] < tomorrow and max(e["end"], e["start"]) > now)]
    if left:
        shown_ = [describe(e, today, with_day=False) for e in left[:4]]
        more = f" (+{len(left) - 4} more)" if len(left) > 4 else ""
        return "Calendar today: " + "; ".join(shown_) + more
    upcoming = [e for e in found if (e["start"] if e["all_day"] else e["start"].date()) > today]
    return f"Calendar: nothing more today; next {describe(upcoming[0], today)}" if upcoming else \
        "Calendar: nothing today or this week"


def _when_words(day, days):
    if days == 1:
        return _day_word(day, date.today())
    return f"{day:%a %b} {day.day} to {(day + timedelta(days=days - 1)):%a %b} {(day + timedelta(days=days - 1)).day}"


def agenda(day, days=1, search=""):
    """The tool's answer: events from day for days, or the ones matching
    search in the next year."""
    if not available():
        return "Calendar isn't installed: pip install icalendar recurring-ical-events (./update.sh does it)."
    if not enabled():
        return ("No calendar is set up: calendar.enabled, plus calendar.google, calendar.ics or "
                "calendar.calcurse (the settings page, or config.json).")
    if search:
        start = datetime.combine(date.today(), datetime.min.time())
        found = events(start, start + timedelta(days=366), wait=True)
        words = [w for w in re.findall(r"\w+", search.lower()) if len(w) > 2] or [search.lower()]
        found = [e for e in found if all(w in (e["title"] + " " + e["where"]).lower() for w in words)][:10]
        head = f"Events matching {search!r} in the next year:"
        empty = f"Nothing matching {search!r} in your calendar for the next year."
    else:
        start = datetime.combine(day, datetime.min.time())
        found = events(start, start + timedelta(days=days), wait=True)
        head = f"Your calendar, {_when_words(day, days)}:"
        empty = f"Nothing in your calendar {_when_words(day, days)}."
    broken = errors()
    note = ("\n(Couldn't read " + ", ".join(f"{n}: {why}" for n, why in broken) +
            " - this may be missing things.)") if broken else ""
    if not found:
        return empty + note
    return head + "\n" + "\n".join(f"- {describe(e)}" for e in found[:40]) + note


def status():
    s = settings()
    lines = []
    if not available():
        lines.append("calendar: needs pip install icalendar recurring-ical-events (./update.sh)")
    if not sources():
        lines.append("calendar: no calendars yet. Put Google's secret iCal link in calendar.google, "
                     "or set calendar.calcurse true (the settings page, or config.json).")
        return "\n".join(lines)
    lines.append("calendar: " + ("on" if s["enabled"] else "off (calendar.enabled)"))
    with _lock:
        cache = dict(_cache)
    for key, kind, where in sources():
        c = cache.get(key)
        state = "not read yet" if not c else (f"error: {c['error']}" if c["error"] else
                                              f"read {time.strftime('%H:%M', time.localtime(c['at']))}")
        lines.append(f"  {(c or {}).get('name') or shown(kind, where)}: {state}")
    return "\n".join(lines)
