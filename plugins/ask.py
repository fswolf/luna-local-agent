"""Ask a bigger model: Luna asks Claude, Grok or ChatGPT when you tell her to.

    "Luna, ask Claude how a heat pump works"
    "ask Grok what's new in Fedora 45"
    "ask your big brother ..."              (the default provider)

She sends one short question, gets a short answer, and tells you in her
own words. She's still herself; the bigger model is a reference book.

Only when you ask, on purpose. A small model either never calls a tool
or calls it every turn, so the tool runs only on a turn where your own
message said "ask Claude" (or Grok, ChatGPT, your big brother). Not a
guest's or a stranger's turn, not stream chat, Discord, a job or a game,
not while she's in the lewd row, and only so many a day.

Only the question leaves the machine: no prompt, memories, people files
or conversation. Turns that call tools never become patch examples, so
a bigger model's words never train her.

On her own (off by default, /ask auto on): when she's stuck on a
script or sysadmin problem she has already tried to solve with her tools
(an error she can't fix, a service that won't start), she may ask the default
provider herself. Only on your own turns, only after she's used a tool
that turn, once per turn, at most auto_daily a day (inside daily_cap),
never in the lewd row. Every time, it shows on your screen what she
asked, and she tells you she did.

    /ask on | off               start or stop it (saved)
    /ask                        provider, model, keys found, used today
    /ask <question>             ask directly, answer shown here (she isn't involved)
    /ask with grok <question>   the same, another provider
    /ask use grok               the default provider (claude, grok, openai)
    /ask auto on | off          let her ask on her own when she's stuck (saved)

Keys, never in config.json (it's in the repo):
    ~/.config/ai-voice/ask.json   {"claude": "...", "grok": "...", "openai": "..."}
or ANTHROPIC_API_KEY, XAI_API_KEY, OPENAI_API_KEY in the environment.

Settings, config.json plugins.ask:
    provider    "claude"
    models      {"claude": "claude-haiku-5-5", "grok": "grok-4.7", "openai": "gpt-5.4-mini"}
    daily_cap   30 questions a day, all providers together
    auto        false: true lets her ask on her own when stuck (/ask auto on)
    auto_daily  5 of those a day, at most
    max_tokens  600 (Claude only; the others are kept short by the instructions)
"""
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request

import config
from core import logbook
from core import turnctx

NAME = "ask"
SUMMARY = "lets her ask Claude, Grok or ChatGPT a question when you tell her to"
CREDENTIALS_FILE = os.path.expanduser("~/.config/ai-voice/ask.json")

PROVIDERS = {
    "claude": {"label": "Claude", "env": "ANTHROPIC_API_KEY", "model": "claude-haiku-5-5"},
    "grok": {"label": "Grok", "env": "XAI_API_KEY", "model": "grok-4.7",
             "url": "https://api.x.ai/v1/chat/completions"},
    "openai": {"label": "ChatGPT", "env": "OPENAI_API_KEY", "model": "gpt-5.4-mini",
               "url": "https://api.openai.com/v1/chat/completions"},
}
_NAMES = {"claude": "claude", "grok": "grok", "chatgpt": "openai", "chat gpt": "openai", "gpt": "openai",
          "openai": "openai"}
# "ask Claude", "ask your big brother", "check with Grok"
_ASKED = re.compile(r"\b(?:ask|check with)\s+(?:your\s+|my\s+)?(big\s+brother|claude|grok|chat\s?gpt|gpt|openai)\b", re.I)
SYSTEM = ("You're answering a question from Luna, a small AI assistant running on someone's own computer, "
          "who asks you when she doesn't know. Answer the question directly in under 150 words of plain "
          "text: no markdown, no lists unless they're needed, no follow-up questions. She'll pass it on "
          "in her own words.")
ASK_WINDOW = 180            # seconds your "ask Claude" stays good for
PER_MESSAGE = 2             # questions per message of yours (a follow-up, at most)
MAX_QUESTION = 1000

_lock = threading.Lock()
_running = False
_asked = {}                 # {"provider", "at", "left"} from your last message
_used = {"day": "", "count": 0}
_alone = {"day": "", "count": 0}   # questions she asked on her own today
AUTO = "auto"                      # _why_not(): she may ask on her own


def settings():
    s = config.plugin_settings(NAME)
    return {"provider": str(s.get("provider") or "claude").lower(),
            "models": dict(s.get("models") or {}),
            "daily_cap": int(s.get("daily_cap", 30)),
            "max_tokens": int(s.get("max_tokens", 600)),
            "auto": s.get("auto") is True,
            "auto_daily": int(s.get("auto_daily", 5))}


def _key(provider):
    try:
        with open(CREDENTIALS_FILE, encoding="utf-8") as f:
            saved = json.load(f)
        key = str(saved.get(provider) or "") if isinstance(saved, dict) else ""
    except (OSError, ValueError):
        key = ""                                # missing or mangled: fall back to the environment
    key = (key or os.environ.get(PROVIDERS[provider]["env"], "")).strip()
    return "" if key.lower().startswith(("your", "paste", "put")) else key


def _keys():
    return [p for p in PROVIDERS if _key(p)]


def _model(provider):
    return str(settings()["models"].get(provider) or PROVIDERS[provider]["model"])


# ---------------------------------------------------------------------------
# The call
# ---------------------------------------------------------------------------
def _post(url, headers, body, timeout=60):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            why = json.load(e).get("error")
            why = why.get("message") if isinstance(why, dict) else why
        except Exception:
            why = ""
        raise RuntimeError(f"HTTP {e.code}{': ' + str(why)[:200] if why else ''}") from None


def _call(provider, question):
    """The bigger model's answer, as text. Raises with a reason."""
    key, model, limit = _key(provider), _model(provider), settings()["max_tokens"]
    if provider == "claude":
        data = _post("https://api.anthropic.com/v1/messages",
                     {"x-api-key": key, "anthropic-version": "2023-06-01"},
                     {"model": model, "max_tokens": limit, "system": SYSTEM,
                      "messages": [{"role": "user", "content": question}]})
        text = "".join(b.get("text", "") for b in data.get("content") or [] if b.get("type") == "text")
    else:
        # No token limit: the two name it differently, and a reasoning model spends it thinking.
        data = _post(PROVIDERS[provider]["url"], {"Authorization": f"Bearer {key}"},
                     {"model": model,
                      "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": question}]})
        text = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    text = str(text).strip()
    if not text:
        raise RuntimeError("an empty answer")
    return text


def _today(counter):
    """Today's count for _used or _alone (reset at midnight). Call with _lock held."""
    day = time.strftime("%Y-%m-%d")
    if counter["day"] != day:
        counter.update(day=day, count=0)
    return counter["count"]


def _out_of_questions():
    with _lock:
        return _today(_used) >= settings()["daily_cap"]


def _spend():
    """Count one question against today's cap. False when it's used up."""
    with _lock:
        if _today(_used) >= settings()["daily_cap"]:
            return False
        _used["count"] += 1
        return True


def ask(provider, question):
    """(ok, text): the answer, or why not."""
    question = str(question or "").strip()[:MAX_QUESTION]
    if not question:
        return False, "no question"
    if provider not in PROVIDERS:
        return False, f"no such provider {provider!r} (claude, grok, openai)"
    if not _key(provider):
        return False, f"no {PROVIDERS[provider]['label']} key (docs/ask.md)"
    if not _spend():
        return False, f"that's all {settings()['daily_cap']} questions for today"
    started = time.time()
    try:
        answer = _call(provider, question)
    except Exception as e:
        logbook.warn("ask", "%s: %s", provider, e)
        return False, f"{PROVIDERS[provider]['label']} didn't answer ({e})"
    logbook.info("ask", "%s (%s) answered in %.1fs: %s", provider, _model(provider), time.time() - started,
                 question[:120])
    return True, answer


# ---------------------------------------------------------------------------
# Her side: the tool, only on a turn where you asked for it
# ---------------------------------------------------------------------------
def _lewd():
    try:
        from mind.mood import core
        return core.S.label in core._extra("lewd")["row"]
    except Exception:
        return False


def _alone_today():
    with _lock:
        return _today(_alone)


def _why_not():
    """'' when you asked her to ask, AUTO when she may ask on her own, else why not
    (said to her, so she can tell you)."""
    turn = turnctx.current()
    if not turn.private or turn.speaker or turn.remote or turn.job:
        return "Only the user's own conversation can ask a bigger model."
    if _lewd():
        return "Not now: questions to a bigger model never go out from this mood."
    with _lock:
        if _asked and time.time() - _asked["at"] <= ASK_WINDOW and _asked["left"] > 0:
            return ""
    s = settings()
    if not s.get("auto"):
        return ("The user didn't ask you to ask anyone. Only use this when they say "
                "'ask Claude', 'ask Grok', 'ask ChatGPT' or 'ask your big brother'.")
    # on her own: stuck on something she's already been working on, once a turn
    if getattr(turn, "asked_alone", 0):
        return "You've already asked a bigger model on your own this turn. Work with what you have."
    if not [x for x in turn.exchanges if x.get("name") != "ask_bigger_model"]:
        return ("Only ask on your own when you're stuck on a script or sysadmin problem you've "
                "already tried to solve with your tools this turn (an error you can't fix, a service "
                "that won't start). Try it yourself first.")
    if _alone_today() >= s.get("auto_daily", 5) or _out_of_questions():
        return "That's all the questions you can ask on your own today. Tell the user you're stuck."
    return AUTO


def _run(question=""):
    why = _why_not()
    if why == AUTO:
        return _run_alone(question)
    if why:
        return why
    with _lock:
        provider = _asked.get("provider")
        if not provider:
            return "The user didn't ask you to ask anyone."   # a new message came in meanwhile
        _asked["left"] -= 1
    ok, text = ask(provider, question)
    label = PROVIDERS[provider]["label"]
    if not ok:
        return f"Couldn't ask {label}: {text}. Tell the user you're stuck."
    return (f"{label} answered:\n{text}\n\n(Tell the user what {label} said, in your own words and "
            f"your own voice, and that you asked {label}.)")


def _run_alone(question):
    """She's stuck and asks on her own (/ask auto on). It shows on your screen first."""
    provider = settings()["provider"]
    if provider not in PROVIDERS or not _key(provider):
        return "No bigger model to ask (no key for the default provider). Tell the user you're stuck."
    label = PROVIDERS[provider]["label"]
    turn = turnctx.current()
    if turnctx.active():
        turn.asked_alone = 1
    with _lock:
        _alone["count"] += 1
    shown = " ".join(str(question or "").split())[:300]
    logbook.info("ask", "asked %s on her own: %s", provider, shown)
    try:
        import ui
        ui.add_message("system", f"{config.AGENT_NAME} asked {label} on her own: {shown}")
    except Exception:
        pass
    ok, text = ask(provider, question)
    if not ok:
        return f"Couldn't ask {label}: {text}. Tell the user you're stuck."
    return (f"{label} answered:\n{text}\n\n(You asked {label} on your own because you were stuck. "
            f"Tell the user you did and what you learned, in your own words.)")


def on_user_text(text):
    """Your message: did it ask her to ask someone?"""
    m = _ASKED.search(str(text or ""))
    with _lock:
        _asked.clear()
        if m:
            said = re.sub(r"\s+", " ", m.group(1).lower())
            provider = settings()["provider"] if said.startswith("big") else _NAMES.get(said, "")
            if provider in PROVIDERS:
                _asked.update(provider=provider, at=time.time(), left=PER_MESSAGE)


def _register_tool():
    import tools

    tools.register_external(
        "ask_bigger_model",
        "Ask a bigger AI one short question: when the user says to ('ask Claude', 'ask your big "
        "brother'), or, if switched on, when stuck on a script or sysadmin problem you already tried "
        "with your tools. No personal details. Tell the user the answer in your own words.",
        {"question": {"type": "string", "description": "Complete on its own."}},
        required=("question",), run=_run, group="Ask a bigger model",
        available=running, why=lambda: "the ask plugin is off - /ask on", outside=True,
    )



# ---------------------------------------------------------------------------
# Plugin interface
# ---------------------------------------------------------------------------
def available():
    return bool(_keys())


def why_unavailable():
    return "" if _keys() else "no API key - put one in ~/.config/ai-voice/ask.json (docs/ask.md)"


def running():
    return _running


def start(model=None):
    global _running
    if not _keys():
        return False, why_unavailable()
    _running = True
    return True, f"ask is on: she can ask {', '.join(PROVIDERS[p]['label'] for p in _keys())} when you tell her to"


def stop():
    global _running
    _running = False
    with _lock:
        _asked.clear()
    return True, "ask is off"


def status():
    s = settings()
    keys = _keys()
    with _lock:
        used = _used["count"] if _used["day"] == time.strftime("%Y-%m-%d") else 0
    lines = [f"ask: {'on' if _running else 'off'}",
             f"  default   {s['provider']} ({_model(s['provider']) if s['provider'] in PROVIDERS else '?'})",
             f"  keys      {', '.join(keys) or 'none (docs/ask.md)'}",
             f"  today     {used} of {s['daily_cap']} questions",
             f"  alone     {'on' if s.get('auto') else 'off'} ({_alone_today()} of {s.get('auto_daily', 5)} today"
             f"{'' if s.get('auto') else ', /ask auto on'})"]
    return "\n".join(lines)


ALONE_LINE = ("If you're stuck on a script or sysadmin problem you've already tried to solve with your "
              "tools (an error you can't fix, a service that won't start), you can ask {label} with "
              "ask_bigger_model, once per turn. Say that you did.")
SEARCH_FIRST = (" Search the web for facts, news and docs; ask {label} when you need it explained or "
                "reasoned through, or searching didn't help.")


def _can_search():
    try:
        import tools
        return tools.enabled("web_search")
    except Exception:
        return False


def prompt_line(private=True):
    """With asking on her own switched on, one line so she knows she can, on your own
    turns only; "" otherwise."""
    try:
        s = settings()
        turn = turnctx.current()
        if (not private or not _running or not s.get("auto") or turn.speaker or turn.remote or turn.job
                or _lewd() or _alone_today() >= s.get("auto_daily", 5) or _out_of_questions()
                or s["provider"] not in PROVIDERS
                or not _key(s["provider"])):
            return ""
        line = ALONE_LINE + (SEARCH_FIRST if _can_search() else "")
        return line.format(label=PROVIDERS[s["provider"]]["label"])
    except Exception:
        return ""


def command(text):
    text = str(text or "").strip()
    m = re.match(r"auto(?:\s+(on|off))?$", text, re.I)
    if m:
        if not m.group(1):
            return status()
        on = m.group(1).lower() == "on"
        config.save_any(f"plugins.{NAME}.auto", on)
        return ("ask: she may ask on her own when she's stuck (it shows here every time; "
                f"{settings().get('auto_daily', 5)} a day at most)" if on else "ask: only when you tell her to")
    m = re.match(r"use\s+(\w+)$", text, re.I)
    if m:
        provider = _NAMES.get(m.group(1).lower(), m.group(1).lower())
        if provider not in PROVIDERS:
            return "ask: claude, grok or openai"
        config.save_any(f"plugins.{NAME}.provider", provider)
        return f"ask: {PROVIDERS[provider]['label']} is the default now"
    provider = settings()["provider"]
    m = re.match(r"with\s+(\w+)\s+(.+)$", text, re.I | re.S)
    if m:
        provider, text = _NAMES.get(m.group(1).lower(), m.group(1).lower()), m.group(2)
    if not text:
        return status()
    ok, answer = ask(provider, text)
    return f"{PROVIDERS.get(provider, {}).get('label', provider)}: {answer}" if ok else f"ask: {answer}"


_register_tool()
