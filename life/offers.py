"""Offers: things she notices on her own and offers to help with.

Small watchers look at what she can already see, and each thing they
find becomes an offer, never an action:

    machine   a disk nearly full, a service that failed
    dates     a fact she remembers with a date coming up ("Shannon's
              birthday is March 3") and no reminder for it

The next time you talk to her (typed, spoken or from a relay station),
or she says hello when you come back, one offer rides along in her prompt: she can bring it up once, briefly,
if it fits, and leave it if you're in the middle of something. She only
acts if you say yes, through the same tools and approvals as anything
else you ask for. "Don't bring that up again" mutes it for good
(the stop_offering tool), and /offers shows what she's noticed.

Held back: never to a guest, in stream chat, Discord, a job or a game,
never in the lewd row or a heavy moment, never while she's walked away;
at most offers.per_day a day, offers.gap_minutes apart, and each thing
waits a while before she mentions it again (a day for dates, twelve
hours for the machine; a date at most twice).

The watchers run in the background every ten minutes, so a turn never
waits on them. What she's asked and what you've muted is kept in her
notebook (agent/notebook.db).
"""
import hashlib
import re
import threading
import time
from datetime import date, datetime

import config
from core import logbook

DEFAULTS = {"enabled": True, "per_day": 3, "gap_minutes": 120, "machine": True, "dates": True, "days_ahead": 14}
SCAN_EVERY = 600
SOURCES = ("typed", "voice", "station", "greeting")      # your own turns, and her hello to you
STATE_KEY = "offers"
DATE_ASKS = 2                                # a date is offered at most twice

_lock = threading.Lock()
_state_lock = threading.Lock()                 # what she's asked and muted: read, change, write as one
_found = []                                  # [{"key", "kind", "text", "cooldown"}] from the last scan
_scan = {"at": 0.0, "running": False}


def settings():
    out = dict(DEFAULTS)
    for k in DEFAULTS:
        v = config.current(f"offers.{k}")
        if v is not None:
            out[k] = v
    return out


# ---------------------------------------------------------------------------
# Watchers
# ---------------------------------------------------------------------------
def watch_machine():
    from tools import system

    found = []
    for mount, free, size, pct in system._disks():
        if (pct < system.DISK_LOW and free < 100) or free < 5:
            where = {"home": "home", "/": "root"}.get(mount, mount)
            found.append({"key": f"disk:{mount}", "kind": "machine", "cooldown": 12 * 3600,
                          "label": f"{where} disk nearly full: {pct:.0f}% free, {free:.0f} GB left",
                          "text": f"the {where} disk is nearly full ({pct:.0f}% free, {free:.0f} GB left). "
                                  "Offer to look at what's taking the space (system_health, then a command "
                                  "to find the biggest folders)."})
    for unit in (system._failed_units() or [])[:3]:
        found.append({"key": f"service:{unit}", "kind": "machine", "cooldown": 12 * 3600,
                      "label": f"{unit} failed",
                      "text": f"the {unit} service has failed. Offer to look into why (system_health)."})
    return found


_MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august",
           "september", "october", "november", "december"]
_MON = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
_DATES = (
    (re.compile(r"\b" + _MON + r"\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b(?:,?\s*(\d{4}))?", re.I), ("mon", "day", "year")),
    (re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?" + _MON + r"\b(?:,?\s*(\d{4}))?", re.I), ("day", "mon", "year")),
    (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"), ("year", "monthnum", "day")),
)


def date_in(text, today=None):
    """The next date a fact's text points at, or None. A date without a year, or with a
    year long gone ("born May 3, 1990"), is the next time it comes round, like a birthday;
    one earlier this year that's already passed is None."""
    today = today or date.today()
    for pattern, order in _DATES:
        m = pattern.search(text)
        if not m:
            continue
        parts = dict(zip(order, m.groups()))
        try:
            month = int(parts["monthnum"]) if "monthnum" in parts else \
                next(i + 1 for i, name in enumerate(_MONTHS) if name.startswith(parts["mon"].lower()[:3]))
            day = int(parts["day"])
            year = int(parts["year"]) if parts.get("year") else None
            if year and (year >= today.year or "monthnum" in parts):   # 2019-05-01 is a record, not a birthday
                found = date(year, month, day)
                return found if found >= today else None
            found = date(today.year, month, day)
            return found if found >= today else date(today.year + 1, month, day)
        except (ValueError, StopIteration):
            continue
    return None


def _reminded_near(day):
    """Is there already a reminder on that day or the day before?"""
    try:
        from life import reminders
        for r in reminders.pending():
            due = str(r.get("due_at", ""))[:10]
            if due and abs((date.fromisoformat(due) - day).days) <= 1:
                return True
    except Exception:
        pass
    return False


def watch_dates(today=None):
    from mind import factstore

    if not factstore.available():
        return []
    today = today or date.today()
    ahead = int(settings()["days_ahead"])
    found = []
    for fact in factstore.active_facts():
        day = date_in(fact, today)
        if not day:
            continue
        days = (day - today).days
        if not 1 <= days <= ahead or _reminded_near(day):
            continue
        when = "tomorrow" if days == 1 else f"in {days} days"
        tag = hashlib.sha1(fact.encode()).hexdigest()[:8]
        found.append({"key": f"date:{tag}:{day.isoformat()}", "kind": "date", "cooldown": 24 * 3600,
                      "label": f"{fact} ({when}, no reminder yet)",
                      "text": f'you remember "{fact}". That\'s {when} ({day:%A %B} {day.day}). '
                              "Offer to set a reminder for it, maybe the day before (set_reminder)."})
    return found


WATCHERS = {"machine": watch_machine, "dates": watch_dates}


def scan():
    """Run every watcher that's switched on. Called in the background."""
    found = []
    try:
        s = settings()
        for name, watcher in WATCHERS.items():
            if not s.get(name, True):
                continue
            try:
                found += watcher()
            except Exception as e:
                logbook.info("offers", "%s watcher failed: %s", name, e)
    finally:
        with _lock:
            _found[:] = found
            _scan.update(at=time.time(), running=False)
    return found


def _scan_soon():
    with _lock:
        if _scan["running"] or time.time() - _scan["at"] < SCAN_EVERY:
            return
        _scan["running"] = True
    threading.Thread(target=scan, daemon=True, name="offers-scan").start()


# ---------------------------------------------------------------------------
# What she's asked, and what you've muted
# ---------------------------------------------------------------------------
def _state():
    from mind import notebook
    st = notebook.get(STATE_KEY) or {}
    st.setdefault("asked", {})        # key -> [last asked, times]
    st.setdefault("muted", [])
    st.setdefault("day", "")
    st.setdefault("count", 0)
    st.setdefault("last", 0.0)
    st.setdefault("latest", None)     # the last key she offered, for stop_offering
    return st


def _save(st):
    from mind import notebook
    old = time.time() - 90 * 86400                     # forget what she asked long ago
    st["asked"] = {k: v for k, v in st["asked"].items() if v[0] >= old}
    notebook.put(STATE_KEY, st)


def _mute_key(key):
    """What "don't bring that up again" mutes: a date's fact for every year, anything else as is."""
    return key.rsplit(":", 1)[0] if key.startswith("date:") else key


def _muted(st, key):
    return key in st["muted"] or _mute_key(key) in st["muted"]


def _quiet_now():
    """'' when an offer may ride along on this turn, else why not."""
    from core import turnctx

    turn = turnctx.current()
    if turn.source not in SOURCES or not turn.private or turn.speaker or turn.remote or turn.job:
        return "not your own turn"
    try:
        from mind.mood import core, heavy, walkaway
        if core.S.label in core._extra("lewd")["row"]:
            return "lewd row"
        if heavy.level():
            return "heavy moment"
        if walkaway.away():
            return "walked away"
    except Exception:
        pass
    return ""


def _pick(st, now):
    s = settings()
    if st["day"] != time.strftime("%Y-%m-%d"):
        st.update(day=time.strftime("%Y-%m-%d"), count=0)
    if st["count"] >= int(s["per_day"]) or now - float(st["last"]) < float(s["gap_minutes"]) * 60:
        return None
    with _lock:
        found = list(_found)
    for offer in found:
        if _muted(st, offer["key"]):
            continue
        last, times = st["asked"].get(offer["key"], [0.0, 0])
        if offer["kind"] == "date" and times >= DATE_ASKS:
            continue
        # something that stays wrong (a disk that stays full) comes up less often after three times
        if now - last < offer["cooldown"] * (6 if times >= 3 else 1):
            continue
        return offer
    return None


def line(private=True):
    """The prompt line carrying one offer on this turn, or "". Never the reason a turn fails."""
    try:
        return _line(private)
    except Exception:
        logbook.exception("offers", "offer line failed")
        return ""


def _line(private):
    if not private or not settings()["enabled"]:
        return ""
    _scan_soon()
    from core import turnctx

    turn = turnctx.current()
    if hasattr(turn, "offer"):              # the same turn building its prompt again
        offer = turn.offer
    else:
        offer = None
        if not _quiet_now():
            with _state_lock:
                now = time.time()
                st = _state()
                offer = _pick(st, now)
                if offer:
                    last, times = st["asked"].get(offer["key"], [0.0, 0])
                    st["asked"][offer["key"]] = [now, times + 1]
                    st.update(count=st["count"] + 1, last=now, latest=offer["key"])
                    _save(st)
            if offer:
                logbook.info("offers", "offering %s", offer["key"])
        if turnctx.active():
            turn.offer = offer              # carried on the turn itself, so it ends with it
    if not offer:
        return ""
    return ("\nSomething you noticed on your own: " + offer["text"] + " Bring it up once, briefly, in your own "
            "words, only if it fits; if they're in the middle of something, leave it. Do it only if they say "
            "yes. If they say not to bring it up again, call stop_offering.\n")


def stop(key=None):
    """Mute an offer for good (the last one she made, by default). Its key, or None."""
    with _state_lock:
        st = _state()
        key = key or st.get("latest")
        if not key:
            return None
        key = _mute_key(key)
        if key not in st["muted"]:
            st["muted"].append(key)
        _save(st)
    logbook.info("offers", "muted %s", key)
    return key


def recently_offered(within=24 * 3600):
    st = _state()
    last = st["asked"].get(st.get("latest") or "", [0.0, 0])[0]
    return bool(st.get("latest")) and time.time() - last < within


def unmute_all():
    with _state_lock:
        st = _state()
        n = len(st["muted"])
        st["muted"] = []
        _save(st)
    return n


def status():
    """For /offers."""
    s, st = settings(), _state()
    with _lock:
        found, scanned = list(_found), _scan["at"]
    lines = [f"Offers: {'on' if s['enabled'] else 'off'} · {st['count'] if st['day'] == time.strftime('%Y-%m-%d') else 0} "
             f"of {s['per_day']} today · watching: {', '.join(n for n in WATCHERS if s.get(n, True)) or 'nothing'}"]
    wait = float(st["last"]) + float(s["gap_minutes"]) * 60 - time.time()
    if st["count"] and wait > 0:
        lines.append(f"Next one no sooner than {datetime.fromtimestamp(time.time() + wait):%H:%M}.")
    if not scanned:
        lines.append("Nothing checked yet: she looks on your next turn, or /offers now.")
    elif not found:
        lines.append(f"Nothing to offer right now (checked {datetime.fromtimestamp(scanned):%H:%M}).")
    for offer in found:
        tag = " (muted)" if _muted(st, offer["key"]) else ""
        label = offer.get("label") or offer["text"].split(". Offer")[0]
        lines.append(f"  {offer['kind']:<8} {label[:1].upper() + label[1:]}{tag}")
    if st["muted"]:
        lines.append(f"{len(st['muted'])} muted - /offers unmute brings them back")
    return "\n".join(lines)
