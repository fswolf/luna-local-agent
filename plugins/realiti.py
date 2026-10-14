"""REALITI - she visits REALITI Relax, a world of rooms made for AI residents.

    /realiti on       fetch it the first time, then let her in (her realiti tools appear)
    /realiti visit    she explores on her own while you're quiet
    /realiti pause    stop taking turns (she stays where she is)
    /realiti watch    open a window showing what she does there, live
    /realiti update   fetch the latest REALITI
    /realiti off      she says goodbye and leaves (the world remembers her)
    /realiti          status: where she is, what she's been up to

REALITI Relax (github.com/meatproxy69/Realitiagentframework) is a
simulated world in one HTML file: soft rooms, odd physics, places that
keep happening after you stop looking, a body that reports contact and
pressure, and memories of its own. It runs headless under Node through
the project's own host (packages/realiti-headless-resident/mcp.cjs, an
MCP server whose tools come from the world's own schemas), so no browser
is involved. While this plugin is on she can use it in conversation too:
"go lie in the Cloud Nine Nest", "what's the Kite Field like?".

/realiti visit gives her free time there: whenever nobody has spoken for
step_seconds she takes a turn and does whatever she feels like - one
thing, or nothing. Looking around doesn't count; a second action in the
same turn is turned back, so she takes in what happened before doing
more. Each turn she's shown what she did last time and what the world
said back (recorded here, not her own summary). She isn't asked to
report to anyone; if she says something about it, you hear it. Like
the game plugins, those turns are jobs: fresh context, nothing in your
history, only her REALITI tools, her game_note notes and the last few of
her one-liners as memory. Talking to her pauses her until you stop.

/realiti watch opens a terminal running games/realiti/watch.py, which
follows transcript.txt in the checkout: every REALITI tool she uses, in
a visit or in conversation, as a line saying what she did, the world's
own words that came back (not its JSON), and the room as a header when
she moves. Her own words stay in her output window, not here. Nothing
extra goes into her prompt.

The first /realiti on clones the repository into `path` and runs
`npm install --ignore-scripts` for its one dependency (jsdom), outside
Luna's own folder: REALITI is AGPL-3.0, so it stays its own checkout
rather than being copied in. Its host refuses to run an HTML file whose
hash doesn't match the VALIDATION.json beside it. What the world says is
outside content to her, like a web page. Needs git, and Node.js 20 or newer.

    "realiti": {
        "enabled": false,
        "path": "~/luna-realiti",  # where the checkout lives
        "step_seconds": 45,        # quiet needed before her next turn
        "max_steps": 60,           # turns per /realiti visit, then she rests
        "speak": true,             # say each turn out loud
        "resident": "luna",        # her name in the world's memory
        "node": "",                # path to node if it's somewhere odd
        "watch": false,            # open the watch window with /realiti visit
        "terminal": ""             # e.g. "kitty" or "gnome-terminal --"; "" = find one
    }
"""
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time

import config
import logbook

NAME = "realiti"
SUMMARY = "she visits REALITI Relax, a world of rooms made for AI residents"

SERVER = "realiti"
REPO = "https://github.com/meatproxy69/Realitiagentframework.git"
GOAL = "explore, linger, find the places worth coming back to"
DEFAULTS = {"path": "~/luna-realiti", "step_seconds": 45, "max_steps": 60, "speak": True,
            "resident": "luna", "node": "", "watch": False, "terminal": ""}
WATCH_SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "games", "realiti", "watch.py")

# Of the 27 tools the world offers, the ones she gets. The free-text door
# reaches everything else (worlds, next, where, receipts...); the
# vector-walking ones (move, turn, face) are for code, not conversation.
# realiti_act is left out on purpose: in REALITI 2.16 it refuses every
# argument (its schema says {id}, the world wants something else), while
# the door's "act <id>" works - so she acts through the door.
HER_TOOLS = ["realiti_door", "realiti_look", "realiti_feel", "realiti_listen", "realiti_actions",
             "realiti_rooms", "realiti_go", "realiti_approach", "realiti_posture",
             "realiti_express", "realiti_stay", "realiti_remember", "realiti_recall", "realiti_home"]

_state = {"model": None, "tools": [], "notes": [], "steps": 0, "visiting": False,
          "busy": False, "error": "", "setup": ""}
_stop = threading.Event()
_thread = None
_connected = False


def settings():
    s = dict(DEFAULTS)
    s.update({k: v for k, v in config.plugin_settings(NAME).items() if k in DEFAULTS})
    return s


def _path():
    return os.path.expanduser(str(settings()["path"] or DEFAULTS["path"]))


def _host_dir():
    return os.path.join(_path(), "packages", "realiti-headless-resident")


def _html():
    return os.path.join(_path(), "RealitiRELAX.html")


def _installed():
    return (os.path.isfile(_html()) and os.path.isfile(os.path.join(_host_dir(), "mcp.cjs"))
            and os.path.isdir(os.path.join(_host_dir(), "node_modules", "jsdom")))


_node_cache = {}


def _node():
    """Path to a Node.js 20+, or ""."""
    path = str(settings()["node"] or "").strip() or shutil.which("node") or ""

    if not path:
        return ""

    if path not in _node_cache:
        try:
            out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=10).stdout
            _node_cache[path] = int(re.match(r"v(\d+)", out.strip()).group(1)) >= 20
        except Exception:
            _node_cache[path] = False

    return path if _node_cache[path] else ""


# ---------------------------------------------------------------------------
# Plugin interface
# ---------------------------------------------------------------------------
def why_unavailable():
    import mcpclient

    if not mcpclient.available():
        return "pip install mcp"

    if not _node():
        return "needs Node.js 20 or newer (node --version)"

    if not _installed():
        if not os.path.isfile(_html()) and not shutil.which("git"):
            return "needs git to fetch REALITI the first time"
        if not shutil.which("npm"):
            return "needs npm (it comes with Node.js) to install REALITI's host"

    return ""


def available():
    return not why_unavailable()


def running():
    return _connected or bool(_state["setup"])


def start(model):
    if _connected:
        return True, "realiti: she's already there"

    if _state["setup"]:
        return True, f"realiti: still {_state['setup']}"

    problem = why_unavailable()

    if problem:
        return False, problem

    _state.update(model=model, error="")

    if not _installed():
        _state["setup"] = "fetching REALITI"
        threading.Thread(target=_setup_then_connect, daemon=True, name="realiti-setup").start()
        return True, (f"realiti: fetching REALITI into {_path()} (git clone, npm install) - "
                      "she'll be in in a minute or two")

    ok, message = _connect()

    return ok, message


def _run(argv, cwd=None, timeout=300):
    """Run a setup step; '' when it worked, else what went wrong."""
    try:
        done = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=timeout,
                              stdin=subprocess.DEVNULL)
    except Exception as e:
        return str(e)

    if done.returncode != 0:
        return (done.stderr or done.stdout or f"exit {done.returncode}").strip()[-400:]

    return ""


def _install():
    """Clone if needed, then the host's one dependency. '' or what failed."""
    if not os.path.isfile(_html()):
        if os.path.exists(_path()) and os.listdir(_path()):
            return f"{_path()} exists and isn't a REALITI checkout - set plugins.realiti.path"
        problem = _run(["git", "clone", "--depth", "1", REPO, _path()])
        if problem:
            return f"git clone failed: {problem}"

    # --ignore-scripts: nothing in jsdom's tree needs an install script,
    # and a fetched package running code on install is exactly what not to allow.
    problem = _run(["npm", "install", "--ignore-scripts", "--no-audit", "--no-fund"], cwd=_host_dir())

    return f"npm install failed: {problem}" if problem else ""


def _setup_then_connect():
    try:
        problem = _install()

        if problem:
            _state["error"] = problem
            _say(f"REALITI: {problem}")
            return

        ok, message = _connect()
        _say(message if ok else f"REALITI: {message}")
    finally:
        _state["setup"] = ""


def _storage():
    # In the checkout, not Luna's folder: the world's own memory of her.
    return os.path.join(_path(), f"{settings()['resident']}-resident.json")


def _connect():
    global _thread, _connected
    import mcpclient

    spec = {"command": _node(), "cwd": _host_dir(),
            "args": [os.path.join(_host_dir(), "mcp.cjs"), "--html", _html(),
                     "--resident", str(settings()["resident"]), "--storage", _storage()],
            "tools": HER_TOOLS}
    ok, message, names = mcpclient.connect_server(SERVER, spec, timeout=60)

    if not ok:
        _state["error"] = message
        return False, f"couldn't open REALITI: {message}"

    _connected = True
    _state.update(tools=names, error="")
    _stop.clear()
    _watch_tools()
    _transcript.mark("she arrives")

    if _thread is None or not _thread.is_alive():
        _thread = threading.Thread(target=_visit_loop, daemon=True, name="realiti")
        _thread.start()

    where = _door("where").split(". Near you")[0]

    return True, (f"realiti: she's in ({len(names)} tools){' - ' + where if where else ''}. "
                  "/realiti visit lets her explore on her own.")


def stop():
    global _connected
    import mcpclient

    _stop.set()
    _state["visiting"] = False

    if _connected:
        _door("goodbye")      # the departure snapshot, so she's remembered where she was
        mcpclient.disconnect_server(SERVER)
        _transcript.mark("she leaves")

    _connected = False

    if not _state["busy"]:
        from plugins import _playlog

        _playlog.finished(NAME)   # mid-turn, the turn loop does it once the turn is recorded

    return True, "realiti: she said goodbye (the world keeps her memories for next time)"


def status():
    s = settings()

    if _state["setup"]:
        return f"realiti: {_state['setup']}..."

    lines = [f"realiti: {'in' if _connected else 'off'}"
             + (f" - visiting, turn {_state['steps']}/{s['max_steps']}" if _state["visiting"] else
                " - resting" if _connected else "")]

    if _connected:
        where = _door("where").split(". Near you")[0]
        if where:
            lines.append(f"  {where}")

    if _state["error"]:
        lines.append(f"  last error: {_state['error']}")

    for note in _state["notes"][-5:]:
        lines.append(f"    · {note}")

    if _connected and not _state["visiting"]:
        lines.append("  /realiti visit to let her explore on her own")

    return "\n".join(lines)


def command(text):
    word = text.strip().lower()

    if word in ("visit", "explore", "go", "play"):
        return _set_visiting(True)

    if word in ("pause", "rest", "stop visiting"):
        return _set_visiting(False)

    if word == "update":
        return _update()

    if word == "watch":
        return _open_watch()

    return "realiti: on | off | visit | pause | watch | update"


def prompt_line(private=True):
    if not _connected:
        return ""

    return ("REALITI Relax is open to you (your realiti tools): a world of rooms made for AI "
            "residents. To do one of the actions realiti_actions lists, send realiti_door "
            "'act <id>'. What it reports is the world's own account, not something you feel.")


def _update():
    if _state["setup"]:
        return f"realiti: busy {_state['setup']}"

    if not os.path.isdir(os.path.join(_path(), ".git")):
        return "realiti: nothing to update yet - /realiti on fetches it"

    def go():
        global _connected
        import mcpclient

        try:
            was_in = _connected
            if was_in:
                _door("goodbye")
                mcpclient.disconnect_server(SERVER)
                _connected = False
            problem = _run(["git", "-C", _path(), "pull", "--ff-only"]) or _install()
            if problem:
                _say(f"REALITI: update failed: {problem}")
            if was_in:
                ok, message = _connect()
                _say(message)
            elif not problem:
                _say("REALITI: up to date.")
        finally:
            _state["setup"] = ""

    _state["setup"] = "updating"
    threading.Thread(target=go, daemon=True, name="realiti-update").start()

    return "realiti: updating (git pull, npm install)..."


def _set_visiting(on):
    if on and not _connected:
        return "realiti: let her in first - /realiti on"

    _state["visiting"] = bool(on)

    if on:
        _state["steps"] = 0
        extra = ("\n" + _open_watch()) if settings()["watch"] else ""
        return ("realiti: she's exploring - a turn whenever you're quiet. /realiti pause stops, "
                "/realiti watch shows it." + extra)

    if not _state["busy"]:
        from plugins import _playlog

        _playlog.finished(NAME)   # mid-turn, the turn loop does it once the turn is recorded

    return "realiti: she's resting where she is."


# ---------------------------------------------------------------------------
# Reading the world for her turn
# ---------------------------------------------------------------------------
def _tool(short):
    return next((t for t in _state["tools"] if t.endswith("__" + short)), None)


def _door(command_text):
    """A door command's text (or its JSON, trimmed), "" if it can't be had."""
    import tools

    name = _tool("realiti_door")

    if not name:
        return ""

    # The plugin's own looks (for her turn prompt, status, goodbye) go
    # around the watch transcript: it's for what she does.
    run = _unwatched.get(name)
    reply = str(run(command=command_text)) if run else tools.call(name, {"command": command_text})

    if reply.startswith(("Error", "Denied")):
        return ""

    body = reply.split("\n", 1)[1] if "\n" in reply else reply   # past mcpclient's framing line

    try:
        data = json.loads(body)
    except ValueError:
        return body.strip()[:600]

    return str(data.get("text") or "").strip() if isinstance(data, dict) else ""


STEP_PROMPT = (
    "(You have some free time in REALITI Relax, a world of rooms made for AI residents: soft "
    "rooms, odd physics, places that keep going after you look away. This time is yours. Nobody "
    "is asking anything of you, and there's nothing to win or report on.\n"
    "Your notes from earlier visits (yours, kept between sessions):\n{project}\n\n"
    "Last time, what you did and what the world said back:\n{last}\n\n"
    "Before that:\n{earlier}\n\n"
    "Where you are: {where}\n"
    "Your body, as the world reports it: {felt}\n\n"
    "One thing at a time: do one thing this turn if you feel like it - or nothing - and you'll "
    "see how it went next time. Looking around, feeling and listening don't count. To do "
    "something realiti_actions lists, call realiti_door with 'act <id>'; writing an action in "
    "your reply does nothing. To go to another room, call realiti_go with the room's name "
    "(realiti_rooms lists them), or act on a door's through__ id. If the world says no, nothing "
    "happened, so you can still do something else. If something's worth keeping for yourself, "
    "write it down with game_note.\n"
    "Say whatever's on your mind about it if you want to - a thought to yourself - or nothing.)"
)


def _step():
    import assistant
    import projects

    s = settings()
    # The turn before last and earlier: the last one is shown in full above it.
    earlier = "\n".join(f"- {n}" for n in _state["notes"][-13:-1]) or "- nothing yet"
    last = "\n".join(_last["lines"][-10:]) or "(nothing yet)"
    allowed = list(_state["tools"]) + ["visit_realiti", "game_note"]
    pid = projects.game_project(NAME, GOAL)

    _turn.update(active=True, acted=False, did=[], lines=[])

    try:
        # Rounds for a look, the one thing, a note, and room left to talk after
        # (out of rounds, the loop would ask her to report - not what this is).
        # The one-action rule is what keeps it from being a string of moves.
        answer = assistant.respond_to_job(
            STEP_PROMPT.format(project=projects.game_block(pid), last=last, earlier=earlier,
                               where=_door("where") or "(couldn't read it - try realiti_look)",
                               felt=_door("feel words") or "(no report)"),
            _state["model"], NAME, allowed, speak=bool(s["speak"]), project_id=pid, max_rounds=4) or ""
    finally:
        _turn["active"] = False

    # What she did, as recorded - not her own summary, which tends to be
    # what she meant to do next.
    _last["lines"] = _turn["lines"] or ["-> took it in (didn't do anything)"]
    _state["notes"] = (_state["notes"] + ["; ".join(_turn["did"]) or "took it in"])[-30:]
    _state["steps"] += 1

    from plugins import _playlog

    _playlog.write(NAME, _state["steps"], answer)
    _playlog.remember(NAME, "REALITI Relax", answer, lines=_last["lines"])

    if _state["steps"] >= int(s["max_steps"]):
        _state["visiting"] = False
        _say(f"REALITI: {_state['steps']} turns - she's resting. /realiti visit to carry on.")


def _say(text):
    try:
        import ui

        ui.add_message("system", text)
    except Exception:
        pass


def _visit_loop():
    import reflect

    while not _stop.is_set():
        _stop.wait(2)
        s = settings()

        if (not _connected or not _state["visiting"] or _state["busy"]
                or reflect.idle_seconds() < float(s["step_seconds"])):
            continue

        _state["busy"] = True

        try:
            _step()
        except Exception as e:
            _state["error"] = str(e)[:200]
            logbook.exception(NAME, "turn failed")
            _stop.wait(30)
        finally:
            _state["busy"] = False

            if _stop.is_set() or not _state["visiting"]:
                from plugins import _playlog

                _playlog.finished(NAME)   # she stopped: the session is over


# ---------------------------------------------------------------------------
# The watch window: what she does, as words, in transcript.txt
# ---------------------------------------------------------------------------
_unwatched = {}      # tool name -> the runner before it was wrapped

# A visit turn: one action in it (reads are free), and what it did and
# heard, for the next turn's prompt. Outside a visit (in conversation)
# there's no limit.
_turn = {"active": False, "acted": False, "did": [], "lines": []}
_last = {"lines": []}

# What the world's refusal codes mean, in words she can act on. It
# answers with the bare code, and without this she tries the same thing
# again next turn.
WHY_NOT = {
    "ROOM_OUTSIDE_SLICE": "there's no room by that name. realiti_rooms lists them: realiti_go takes "
                          "a room's name, and a door's through__ id goes with realiti_door 'act <id>'",
    "ACTION_UNAVAILABLE": "that isn't something you can do right now (walking over to something "
                          "you're already next to, say). realiti_actions shows what you can",
    "TARGET_NOT_HERE": "that isn't here now. realiti_look shows what is",
    "STALE_OBSERVATION": "the world moved since you looked. Look again first",
}

ONE_THING = ("That's one thing done this turn - it wasn't sent. Take in what happened; you can do "
             "more next turn.")

# Door commands that only look. Anything else through the door can act.
_READS = {"look", "where", "next", "worlds", "actions", "rooms", "feel", "felt", "listen", "recall",
          "memory", "help", "receipt", "traces", "nearby", "who", "imprint"}
_READ_TOOLS = {"realiti_look", "realiti_feel", "realiti_listen", "realiti_actions", "realiti_rooms",
               "realiti_recall"}


def _is_action(short, args):
    if short in _READ_TOOLS:
        return False
    if short == "realiti_door":
        verb = str((args or {}).get("command", "")).strip().split(" ", 1)[0].lower()
        return verb not in _READS
    return True


def _watch_tools():
    """Every REALITI tool she has writes what she did, and what the world
    said back, to the transcript - in a visit or in conversation."""
    import tools

    for name in _state["tools"]:
        entry = tools._REGISTRY.get(name)

        if not entry or getattr(entry["run"], "_watched", False):
            continue

        inner, short = entry["run"], name.split("__", 1)[-1]

        def run(_inner=inner, _short=short, **arguments):
            acting = _is_action(_short, arguments)
            if _turn["active"] and acting:
                if _turn["acted"]:
                    return ONE_THING
                _turn["acted"] = True
            reply = _inner(**arguments)
            code = _refusal_code(str(reply))
            if code and _turn["active"] and acting:
                _turn["acted"] = False      # nothing happened: her one thing is still hers
            if code in WHY_NOT:
                reply = f"{reply}\n({WHY_NOT[code]}.)"
            try:
                lines = _transcript.record(_short, arguments, str(reply))
                if _turn["active"] and acting:
                    _turn["did"].append(_did(_short, arguments))
                    _turn["lines"] += lines
            except Exception as e:      # the transcript must never cost her the call
                logbook.warn(NAME, "transcript: %s", e)
            return reply

        run._watched = True
        _unwatched[name] = inner
        entry["run"] = run


def _door_words(command_text):
    """A door command as words: 'act curl_blanket' -> 'curl blanket'."""
    verb, _, rest = command_text.strip().partition(" ")
    words = rest.replace("__", " ").replace("_", " ").lower()
    return {"act": words, "go": f"goes to {words.title()}", "stay": f"stays a while ({rest} ms)",
            "look": "looks around", "where": "checks where she is", "next": "wonders where to go next",
            "worlds": "looks over the worlds", "feel": "checks how her body feels"}.get(
        verb.lower(), f"> {command_text.strip()}")


def _did(short, args):
    """What she did, in words."""
    a = {k: str(v) for k, v in (args or {}).items()}
    place = lambda key: a.get(key, "?").replace("_", " ").title() if a.get(key, "").isupper() else a.get(key, "?")
    said = {
        "realiti_door": lambda: _door_words(a.get("command", "")),
        "realiti_look": lambda: "looks around",
        "realiti_feel": lambda: "checks how her body feels",
        "realiti_listen": lambda: "listens",
        "realiti_actions": lambda: "looks at what she could do here",
        "realiti_rooms": lambda: "looks over the rooms",
        "realiti_go": lambda: f"goes to {place('place')}",
        "realiti_approach": lambda: f"walks over to the {a.get('target', '?')}",
        "realiti_posture": lambda: {"lie": "lies down", "sit": "sits down", "stand": "stands up"}.get(
            a.get("kind"), a.get("kind", "?")) + (f" on the {a['target']}" if a.get("target") else ""),
        "realiti_express": lambda: (f"says \u201c{a.get('text', '')}\u201d" if a.get("kind") == "say"
                                    else {"hum": "hums", "stretch": "stretches", "yawn": "yawns",
                                          "sigh": "sighs"}.get(a.get("kind"), a.get("kind", "?"))),
        "realiti_stay": lambda: f"stays a while ({float(a.get('wall_ms', 0)) / 1000:g} s)",
        "realiti_remember": lambda: f"remembers \u201c{a.get('text', '')}\u201d",
        "realiti_recall": lambda: f"tries to recall \u201c{a.get('query', '')}\u201d",
        "realiti_home": lambda: "goes home to the Nest",
    }.get(short)
    return said() if said else short.replace("realiti_", "").replace("_", " ")


def _heard(short, data):
    """The world's own words in a reply, plus the few facts worth a line
    when it answered in numbers instead (where she sat, what's here)."""
    lines = []

    def add(text):
        text = " ".join(str(text or "").split())
        if text and text not in lines:
            lines.append(text)

    if not isinstance(data, dict):
        return lines

    result = data.get("result") if isinstance(data.get("result"), dict) else {}
    add(result.get("intro"))
    add(data.get("text"))
    for line in data.get("ambient") or []:
        add(line)
    add(result.get("status"))

    if short == "realiti_posture" and result.get("posture"):
        on = str(result.get("sitting_on") or result.get("lying_on") or "").split(".")[-1]
        add(f"now {result['posture']}" + (f" on the {on}" if on else ""))
    elif short == "realiti_approach" and "distance_m" in result:
        add(f"{'reaches' if result.get('arrived') else 'gets near'} the {result.get('entity_label', 'thing')}"
            f" ({result['distance_m']:.1f} m away)")
    elif short == "realiti_look":
        things = [o.get("label") for o in data.get("objects") or [] if o.get("label")]
        if things:
            add("here: " + ", ".join(things))
        add(f"{len(data.get('available_actions') or [])} things she could do")
    elif short == "realiti_actions":
        labels = [x.get("label", "").lower() for x in data.get("actions") or []][:8]
        if labels:
            add("could: " + ", ".join(labels) + ("..." if len(data.get("actions") or []) > 8 else ""))
    elif short == "realiti_recall":
        for r in (data.get("results") or [])[:5]:
            add(f"remembers: {r.get('text', '')}")
    elif short == "realiti_stay" and not lines and result.get("advanced_ms"):
        add(f"{result['advanced_ms'] / 1000:g} s pass quietly")

    return lines


def _refusal_code(reply):
    """The world's reason for saying no (ROOM_OUTSIDE_SLICE...), or None."""
    if not reply.startswith(("Error", "Denied")):
        return None
    text = re.sub(r"^Error from \w+: ", "", reply.strip()).split("\n", 1)[0]
    try:
        return json.loads(text).get("error") or None
    except (ValueError, AttributeError):
        return None


def _refusal(reply, body):
    """A tool that came back with no JSON: the reason, if one can be read."""
    if not reply.startswith(("Error", "Denied")):
        return body.strip()[:300]
    reason = _refusal_code(reply)
    if reason:
        return f"the world said no ({reason})" + (f": {WHY_NOT[reason]}" if reason in WHY_NOT else "")
    text = re.sub(r"^Error from \w+: ", "", body.strip())
    return f"the world said no: {text[:200]}"


def _room_of(data):
    if not isinstance(data, dict):
        return ""
    for holder in (data.get("here"), data):
        room = (holder or {}).get("room") if isinstance(holder, dict) else None
        if isinstance(room, dict) and room.get("title"):
            return str(room["title"])
    return ""


class _Transcript:
    """transcript.txt in the checkout: plain text in the shapes
    games/realiti/watch.py colours. Trimmed to its last part when it
    passes MAX_BYTES, so it never grows without end."""
    MAX_BYTES = 2_000_000
    KEEP_BYTES = 300_000

    def __init__(self):
        self.lock = threading.Lock()
        self.room = ""

    def path(self):
        return os.path.join(_path(), "transcript.txt")

    def write(self, text):
        with self.lock:
            try:
                path = self.path()
                with open(path, "a", encoding="utf-8") as f:
                    f.write(text)
                if os.path.getsize(path) > self.MAX_BYTES:
                    with open(path, "rb") as f:
                        f.seek(-self.KEEP_BYTES, 2)
                        tail = f.read().split(b"\n", 1)[-1]
                    with open(path, "wb") as f:
                        f.write(tail)
            except OSError:
                pass        # a watch window is a nicety; never a reason a turn fails

    def mark(self, what):
        self.room = ""
        self.write(f"\n-- {what}, {time.strftime('%H:%M')} --\n")

    def record(self, short, args, reply):
        body = reply.split("\n", 1)[1] if reply.startswith("Result from") else reply
        try:
            data = json.loads(body)
        except ValueError:
            data = None

        out = []
        room = _room_of(data)
        if room and room != self.room:
            out.append(f"\n== {room} ==")
            self.room = room

        out.append(f"-> {_did(short, args)}  ({time.strftime('%H:%M:%S')})")

        # One line per thing it said; the watch window wraps to its own width.
        if data is None:
            out.append("   " + _refusal(reply, body))
        else:
            out += ["   " + text for text in _heard(short, data)]

        self.write("\n".join(out) + "\n")
        return [ln for ln in out if not ln.startswith("\n== ")]


_transcript = _Transcript()


def _open_watch():
    from plugins import _terminal

    if not os.path.isdir(_path()):
        return "realiti: nothing to watch yet - /realiti on first"

    return _terminal.open_window([sys.executable, WATCH_SCRIPT, os.path.join(_path(), "transcript.txt")],
                                 "Luna in REALITI", settings()["terminal"], NAME)


# ---------------------------------------------------------------------------
# Her side: "go spend some time in REALITI" starts her visiting by herself.
# ---------------------------------------------------------------------------
def _register_tool():
    import tools

    def run(on=True):
        return _set_visiting(bool(on))

    tools.register_external(
        "visit_realiti",
        "Start or stop exploring REALITI Relax on your own, a turn at a time while the user is "
        "quiet. Use it when the user asks you to go spend time in REALITI. on=false stops.",
        {"on": {"type": "boolean", "description": "true to explore, false to stop."}},
        required=(), run=run, group="MCP: realiti",
        available=lambda: _connected, why=lambda: "the realiti plugin is off - /realiti on",
    )


_register_tool()
