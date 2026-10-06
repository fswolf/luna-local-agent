"""Scheduled jobs - she wakes up on a timer and does something.

    /cron on | off      start or stop the scheduler (saved)
    /cron               the job list, and when each last ran

Jobs live in agent/cron.json. She proposes one with schedule_job and
you approve it in the popup, or you edit the file by hand:

    [{"name": "disk-check", "schedule": "0 8 * * 1-5",
      "task": "Check free disk and VRAM; note anything under 10% in
               ~/luna-jobs/disk.md", "speak": false}]

A schedule is a 5-field cron line ("0 8 * * 1-5"), "every 30m" /
"every 2h", or a one-off "2026-10-07 08:00" (removed once it fires).
Day-of-month and weekday are ANDed, not cron's OR.

A firing is its own turn: fresh context, nothing stored in history,
and only the tools in plugins.cron.job_tools. Writes still go through
files.py - the popup, unless the path is inside files.job_write_dirs.
That list is yours, in config.json; nothing here can widen it. Away
from the keyboard, a write anywhere else times out as a no and she
says so in her report.

Runs missed while the app was closed are skipped, not caught up.
"""
import json
import os
import threading
from datetime import datetime

import config
import logbook
import tools

NAME = "cron"
SUMMARY = "scheduled jobs - she wakes up and does them"

JOBS_FILE = os.path.join(config.BASE_DIR, "agent", "cron.json")
DEFAULT_TOOLS = ["get_datetime", "time_until", "system_status", "web_search",
                 "list_files", "read_file", "write_file", "edit_file"]
OWN_TOOLS = {"schedule_job", "list_jobs", "cancel_job"}  # a job never schedules jobs

_lock = threading.Lock()
_stop = threading.Event()
_thread = None
_model = None
_jobs = []        # {"name", "schedule", "task", "speak", "_due", "_once", "_busy"}
_skipped = []     # (name, why, raw) - entries that didn't parse, kept in the file
_last = {}        # name -> (when, one-line outcome)


# ---------------------------------------------------------------------------
# Schedules
# ---------------------------------------------------------------------------
def _field(spec, lo, hi):
    out = set()

    for part in spec.split(","):
        rng, _, step = part.partition("/")

        if rng == "*":
            a, b = lo, hi
        elif "-" in rng:
            a, b = (int(x) for x in rng.split("-", 1))
        else:
            a = b = int(rng)
            b = hi if step else b  # "5/15" - from 5, every 15

        if not lo <= a <= b <= hi:
            raise ValueError(f"{part!r} is outside {lo}-{hi}")

        out.update(range(a, b + 1, int(step or 1)))

    return out


def parse(schedule):
    """-> (due(minute) -> bool, one_off). Raises ValueError with a reason
    she can repeat back."""
    s = " ".join(str(schedule or "").split()).lower()

    if s.startswith("every "):
        unit = {"m": 1, "h": 60, "d": 1440}.get(s[-1:])

        if unit is None or not s[6:-1].isdigit():
            raise ValueError('use "every 30m", "every 2h" or "every 1d"')

        every = int(s[6:-1]) * unit

        if every < 5:
            raise ValueError("every needs to be at least 5m")

        return (lambda t: int(t.timestamp()) // 60 % every == 0), False

    parts = s.split()

    if len(parts) == 5:
        ranges = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))
        mi, hr, dom, mon, dow = (_field(p, lo, hi) for p, (lo, hi) in zip(parts, ranges))
        dow = {d % 7 for d in dow}  # 0 and 7 are both Sunday

        return (lambda t: t.minute in mi and t.hour in hr and t.day in dom
                and t.month in mon and (t.weekday() + 1) % 7 in dow), False

    try:
        at = datetime.fromisoformat(s).replace(second=0, microsecond=0)
    except ValueError:
        raise ValueError('not a cron line, "every 30m", or a date like '
                         '"2026-10-07 08:00"') from None

    if at <= datetime.now():
        raise ValueError(f"{at:%Y-%m-%d %H:%M} has already passed")

    return (lambda t: t == at), True


# ---------------------------------------------------------------------------
# The file
# ---------------------------------------------------------------------------
def _job(entry):
    name = str(entry.get("name", "")).strip()
    task = str(entry.get("task", "")).strip()

    if not name or not task:
        raise ValueError("needs a name and a task")

    due, once = parse(entry.get("schedule"))

    return {"name": name, "schedule": str(entry["schedule"]), "task": task,
            "speak": bool(entry.get("speak", True)),
            "_due": due, "_once": once, "_busy": False}


def _load():
    """Missing file is no jobs; a broken one is an error, not no jobs - a
    stray comma shouldn't look like everything got cancelled."""
    try:
        with open(JOBS_FILE) as f:
            data = json.load(f)
    except FileNotFoundError:
        data = []

    if not isinstance(data, list):
        raise ValueError("agent/cron.json should be a list of jobs")

    jobs, skipped = [], []

    for entry in data:
        try:
            jobs.append(_job(entry))
        except Exception as e:
            skipped.append((str(entry.get("name", "?")) if isinstance(entry, dict) else "?", str(e), entry))

    return jobs, skipped


def _save():
    os.makedirs(os.path.dirname(JOBS_FILE), exist_ok=True)
    tmp = JOBS_FILE + ".tmp"

    with open(tmp, "w") as f:
        # Skipped entries go back as they were: a typo in one you wrote by
        # hand shouldn't cost you the job the next time she saves.
        json.dump([{k: v for k, v in j.items() if not k.startswith("_")} for j in _jobs]
                  + [raw for _n, _w, raw in _skipped], f, indent=2)

    os.replace(tmp, JOBS_FILE)


def _tilde(path):
    home = os.path.expanduser("~")

    return "~" + path[len(home):] if path == home or path.startswith(home + os.sep) else path


def _tools():
    wanted = config.plugin_settings(NAME).get("job_tools", DEFAULT_TOOLS)

    return [t for t in wanted if t not in OWN_TOOLS]


# ---------------------------------------------------------------------------
# Running them
# ---------------------------------------------------------------------------
def _fire(job):
    import assistant

    prompt = (f'(Scheduled job "{job["name"]}", set up earlier by the user. '
              f"Do it now: {job['task']}\n"
              "Nobody may be at the keyboard. If a write is denied, don't "
              "retry - say what you would have written. End with a short report.)")

    try:
        answer = assistant.respond_to_job(prompt, _model, job["name"], _tools(),
                                          speak=job["speak"])
        outcome = " ".join((answer or "(no reply)").split())[:120]
        logbook.info(NAME, "%s done: %s", job["name"], outcome)
    except Exception as e:
        outcome = f"failed: {e}"
        logbook.exception(NAME, "job %s failed", job["name"])
    finally:
        job["_busy"] = False

    _last[job["name"]] = (datetime.now(), outcome)

    if job["_once"]:
        with _lock:
            if job in _jobs:
                _jobs.remove(job)
                _save()


def _run():
    seen = None

    while not _stop.is_set():
        now = datetime.now().replace(second=0, microsecond=0)

        if now != seen:
            seen = now

            with _lock:
                due = [j for j in _jobs if not j["_busy"] and j["_due"](now)]

                for job in due:
                    job["_busy"] = True  # a slow one isn't fired again on top of itself

            for job in due:
                threading.Thread(target=_fire, args=(job,), daemon=True,
                                 name=f"cron-{job['name']}").start()

        _stop.wait(60.5 - datetime.now().second)


# ---------------------------------------------------------------------------
# Plugin interface
# ---------------------------------------------------------------------------
def running():
    return _thread is not None and _thread.is_alive()


def start(model):
    global _thread, _model, _jobs, _skipped

    if running():
        return True, "cron: already running"

    try:
        jobs, skipped = _load()
    except Exception as e:
        return False, f"agent/cron.json is broken: {e}"

    with _lock:
        _jobs, _skipped, _model = jobs, skipped, model

    _stop.clear()
    _thread = threading.Thread(target=_run, daemon=True, name="cron")
    _thread.start()

    extra = f", {len(skipped)} skipped - /cron says why" if skipped else ""

    return True, f"cron: running, {len(jobs)} job(s){extra}"


def stop():
    _stop.set()

    if _thread is not None:
        _thread.join(timeout=2)

    return True, "cron: stopped (jobs kept in agent/cron.json)"


def status():
    lines = [f"cron: {'running' if running() else 'off'}, {len(_jobs)} job(s)"]

    for j in _jobs:
        when, what = _last.get(j["name"], (None, ""))
        last = f"  last {when:%m-%d %H:%M} - {what}" if when else ""
        lines.append(f"  {j['name']:16} {j['schedule']:16}{last}")

    for name, why, _raw in _skipped:
        lines.append(f"  [skipped] {name}: {why}")

    dirs = ", ".join(_tilde(d) for d in config.FILES_JOB_WRITE_DIRS) or "none - every write asks"
    lines.append(f"  writes without asking in: {dirs}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Her side: proposing, listing, cancelling. Only offered while cron is on,
# never to a job turn (OWN_TOOLS), and never to stream chat (not in the
# chat ceiling).
# ---------------------------------------------------------------------------
def _why_off():
    return "the cron plugin is off - /cron on"


def tool(name, description, properties, required=(), available=None, why=None):
    """@tool, but through register_external so they group as Jobs in the
    tools pane without the core having to know this plugin exists."""
    def decorator(fn):
        tools.register_external(name, description, properties, required, run=fn,
                                group="Jobs", available=available, why=why)
        return fn

    return decorator


@tool(
    "schedule_job",
    "Schedule something for you to DO later, on your own - a check, a "
    "summary, a note written to a file. Not for pinging the user; that's "
    "set_reminder. The user approves it in a popup first; if denied, "
    "don't retry.",
    {
        "name": {"type": "string", "description": "Short unique id, e.g. 'disk-check'."},
        "schedule": {"type": "string", "description":
                     "Cron line '0 8 * * 1-5', 'every 30m' / 'every 2h', "
                     "or one-off 'YYYY-MM-DD HH:MM'."},
        "task": {"type": "string", "description":
                 "Complete instructions - at run time you won't see this conversation."},
        "speak": {"type": "boolean", "description": "Say the result aloud. Default true."},
    },
    required=("name", "schedule", "task"),
    available=running,
    why=_why_off,
)
def _schedule_job(name, schedule, task, speak=True):
    import ui

    try:
        job = _job({"name": name, "schedule": schedule, "task": task, "speak": speak})
    except ValueError as e:
        return f"Not scheduled: {e}"

    if any(j["name"] == job["name"] for j in _jobs):
        return f"There's already a job called {job['name']} - cancel it first or pick another name."

    dirs = ", ".join(_tilde(d) for d in config.FILES_JOB_WRITE_DIRS) or "nowhere"
    body = [f"when:  {job['schedule']}", f"task:  {job['task']}",
            f"tools: {', '.join(_tools())}", f"writes without asking in: {dirs}"]

    if not ui.ask_approval(title=f"schedule job {job['name']}", body=body,
                           note="runs on its own", timeout=config.FILES_APPROVAL_TIMEOUT):
        return "Denied by the user - not scheduled. Do not retry."

    with _lock:
        _jobs.append(job)
        _save()

    return f"Scheduled {job['name']} ({job['schedule']})."


@tool("list_jobs", "List the scheduled jobs and when each last ran.", {},
      available=running, why=_why_off)
def _list_jobs():
    return status()


@tool(
    "cancel_job",
    "Cancel a scheduled job by name.",
    {"name": {"type": "string", "description": "The job's name, from list_jobs."}},
    required=("name",),
    available=running,
    why=_why_off,
)
def _cancel_job(name):
    with _lock:
        hit = [j for j in _jobs if j["name"] == str(name).strip()]

        if not hit:
            return f"No job called {name}."

        _jobs.remove(hit[0])
        _save()

    return f"Cancelled {hit[0]['name']}."
