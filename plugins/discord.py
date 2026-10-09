"""Remote access over Discord - the owner talks to her from anywhere.

    /discord on           /discord off           /discord    (status)

Not a chat plugin. Stream chat is strangers, so it goes through
chatroom.py and its tool ceiling. This is the owner: messages from the
ids in the credentials file get a normal private turn with the full
tool list, and everyone else is ignored. Anyone you add to owner_ids
has the same reach as the person at the keyboard.

When a Discord turn wants to write a file or run a command, "approval"
decides who says yes: auto (nobody - automation), discord (she asks in
the same chat, you reply y or n or tap a reaction) or desk (the popup
here). /discord approval <mode> switches it and saves it. Her own
folder, ~/.config and ~/.local always get a question, even on auto. The
deny list (keys, .ssh, .env, shell startup files) applies either way.

Credentials stay outside the repo:

    // ~/.config/ai-voice/discord.json
    {"token": "your-bot-token", "owner_ids": [123456789012345678]}

The token comes from the Discord Developer Portal (Bot -> Reset
Token). Turn on Message Content Intent on that page too. Get owner
ids with Settings -> Advanced -> Developer Mode, then right-click your
name -> Copy User ID. DISCORD_TOKEN in the environment also works.

    "discord": {
        "enabled": false,
        "channel": "",       # name or id; "" = DMs only
        "speak": false,      # read replies aloud at the desk too
        "remember": true,    # part of the normal history, like a typed turn
        "tools": null        # null = every tool; or a list to narrow it
    }

In the channel or a DM:  !stop  cuts off the reply in progress,
!status  shows what /discord would.

    pip install discord.py
"""
import asyncio
import json
import os
import threading

import config
import logbook
import state

NAME = "discord"
SUMMARY = "remote access - the owner talks to her from Discord"

CREDENTIALS_FILE = os.path.expanduser("~/.config/ai-voice/discord.json")
MAX_CHUNK = 1900  # Discord's limit is 2000

DEFAULTS = {"channel": "", "speak": False, "remember": True, "tools": None,
            "approval": "discord", "approval_timeout": 300}

# Who says yes when a Discord turn wants to write a file or run a command:
#   auto     nobody - it goes straight through (automation)
#   discord  she asks in the same chat; you reply y or n, or tap a reaction
#   desk     the popup on the desk screen, as if you'd asked at the keyboard
APPROVAL_MODES = ("auto", "discord", "desk")
_current = threading.local()   # the channel this worker thread's turn came from
_pending = {}                  # channel id -> {"event", "answer", "message_id"}

_thread = None
_loop = None
_client = None
_model = None
_error = ""
_ignored = set()
_answered = 0


def settings():
    merged = dict(DEFAULTS)
    merged.update({k: v for k, v in config.plugin_settings(NAME).items() if k in DEFAULTS
                   or k == "enabled"})

    return merged


def _credentials():
    """(token, {owner ids}). Raises ValueError on a file that exists but
    is broken - a stray comma shouldn't look like "no token"."""
    try:
        with open(CREDENTIALS_FILE) as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {}
    except ValueError as e:
        raise ValueError(f"{CREDENTIALS_FILE} isn't valid JSON: {e}") from None

    token = str(data.get("token") or os.environ.get("DISCORD_TOKEN", "")).strip()
    ids = data.get("owner_ids", data.get("owner_id", []))
    ids = ids if isinstance(ids, list) else [ids]
    owners = set()

    for i in ids:
        try:
            owners.add(int(i))
        except (TypeError, ValueError):
            pass

    if token.lower().startswith(("your", "paste", "put")):
        token = ""  # a placeholder passes every check and fails at the far end

    return token, owners


def available():
    return not why_unavailable()


def why_unavailable():
    try:
        import discord  # noqa: F401
    except ImportError:
        return "pip install discord.py"

    try:
        token, owners = _credentials()
    except ValueError as e:
        return str(e)

    if not token:
        return f"no bot token - put it in {CREDENTIALS_FILE}"

    if not owners:
        return f"no owner_ids in {CREDENTIALS_FILE} - nobody would be obeyed"

    return ""


def running():
    return _thread is not None and _thread.is_alive()


# ---------------------------------------------------------------------------
# The turn - runs on a worker thread, never on the Discord event loop
# ---------------------------------------------------------------------------
def _turn(text, who, channel=None):
    import assistant

    s = settings()
    tools = s.get("tools")
    _current.channel = channel

    try:
        return assistant.respond_remote(
            text, _model, source=NAME, who=who,
            tools_allowed=list(tools) if isinstance(tools, list) else None,
            speak=bool(s.get("speak")), remember=bool(s.get("remember", True)),
            approver=_approve,
        )
    finally:
        _current.channel = None


def _mode():
    mode = str(settings().get("approval", "discord")).lower()
    return mode if mode in APPROVAL_MODES else "discord"


def _approve(kind, title, body, guarded=False):
    """Called from the tool, on the turn's worker thread. True = go ahead."""
    mode = _mode()

    if mode == "auto" and not guarded:
        logbook.info(NAME, "auto-approved %s: %s", kind, title)
        return True

    if mode == "desk":
        import ui

        return bool(ui.ask_approval(title=f"[discord] {title}", note="asked from Discord",
                                    body=body, timeout=config.FILES_APPROVAL_TIMEOUT))

    # discord - and auto for the guarded folders (her own code, ~/.config,
    # ~/.local), which always get a question.
    return _ask_in_discord(kind, title, body, guarded)


FENCE = "`" * 3


def _ask_in_discord(kind, title, body, guarded):
    channel = getattr(_current, "channel", None)

    if channel is None or _loop is None:
        return False

    timeout = max(30, int(settings().get("approval_timeout", 300)))
    shown = "\n".join(str(line) for line in body).replace(FENCE, "'''")

    if len(shown) > 1500:
        shown = shown[:1500] + "\n..."

    what = {"command": "run a command", "write": "change a file", "read": "read a file",
            "mcp": "use"}.get(kind, kind)
    warn = ("\n**This is her own code or a config folder.**" if kind in ("write", "read")
            else "\n**Flagged: it always asks.**") if guarded else ""
    head = f"**Luna wants to {what}**" + ("" if kind == "command" else f"{'' if kind == 'mcp' else ':'} {title}")
    wait = f"{timeout // 60} min" if timeout >= 60 else f"{timeout}s"
    text = (f"{head}{warn}\n{FENCE}\n{shown}\n{FENCE}\n"
            f"Reply **y** or **n** (or tap a reaction) - {wait}, then it's a no.")
    slot = {"event": threading.Event(), "answer": None, "message_id": None}
    _pending[channel.id] = slot

    async def post():
        message = await channel.send(text[:1990])
        slot["message_id"] = message.id

        for emoji in ("✅", "❌"):
            try:
                await message.add_reaction(emoji)
            except Exception:
                pass

    try:
        asyncio.run_coroutine_threadsafe(post(), _loop).result(15)
        slot["event"].wait(timeout)
    except Exception as e:
        logbook.warn(NAME, "couldn't ask in Discord: %s", e)
    finally:
        _pending.pop(channel.id, None)

    answer = slot["answer"] is True
    logbook.info(NAME, "%s %s: %s", "approved" if answer else
                 ("denied" if slot["answer"] is False else "timed out"), kind, title)

    if slot["answer"] is None:
        try:
            asyncio.run_coroutine_threadsafe(channel.send("(no answer - not done)"), _loop).result(10)
        except Exception:
            pass

    return answer


_YES = {"y", "yes", "ok", "okay", "yep", "sure", "go", "do it", "✅"}
_NO = {"n", "no", "nope", "stop", "cancel", "❌"}


def _resolve(channel_id, word):
    slot = _pending.get(channel_id)

    if not slot:
        return False

    word = word.strip().lower().rstrip(".!")

    if word in _YES:
        slot["answer"] = True
    elif word in _NO:
        slot["answer"] = False
    else:
        return False

    slot["event"].set()
    return True


def _chunks(text):
    text = text.strip() or "(no reply)"

    while text:
        if len(text) <= MAX_CHUNK:
            yield text
            return

        cut = text.rfind("\n", 0, MAX_CHUNK)
        cut = cut if cut > MAX_CHUNK // 2 else MAX_CHUNK
        yield text[:cut]
        text = text[cut:].lstrip("\n")


def _wanted_channel(message):
    import discord

    if isinstance(message.channel, discord.DMChannel):
        return True

    want = str(settings().get("channel", "")).strip().lstrip("#")

    return bool(want) and want in (str(message.channel.id), getattr(message.channel, "name", ""))


def _run(token, owners):
    global _loop, _client, _error, _answered

    import discord

    intents = discord.Intents.default()
    intents.message_content = True
    client = discord.Client(intents=intents)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    _loop, _client = loop, client

    @client.event
    async def on_raw_reaction_add(payload):
        slot = _pending.get(payload.channel_id)

        if (slot and payload.message_id == slot.get("message_id")
                and payload.user_id in owners and payload.user_id != getattr(client.user, "id", None)):
            _resolve(payload.channel_id, str(payload.emoji))

    @client.event
    async def on_ready():
        logbook.info(NAME, "connected as %s", client.user)

    @client.event
    async def on_message(message):
        global _answered

        if message.author == client.user or message.author.bot:
            return

        if not _wanted_channel(message):
            return

        if message.author.id not in owners:
            if message.author.id not in _ignored:
                _ignored.add(message.author.id)
                logbook.info(NAME, "ignoring %s (%s) - not an owner",
                             message.author, message.author.id)
            return

        text = message.content.strip()

        if not text:
            return

        # An answer to a pending approval, not a new turn.
        if message.channel.id in _pending and _resolve(message.channel.id, text):
            await message.add_reaction("👍")
            return

        if text == "!stop":
            state.stop_generating = state.stop_speaking = True
            await message.add_reaction("🛑")
            return

        if text == "!status":
            await message.channel.send(status()[:MAX_CHUNK])
            return

        try:
            async with message.channel.typing():
                answer = await loop.run_in_executor(
                    None, _turn, text, message.author.display_name, message.channel)
            _answered += 1
        except Exception as e:
            logbook.exception(NAME, "turn failed")
            answer = f"(that failed: {e})"

        for chunk in _chunks(answer):
            await message.channel.send(chunk)

    try:
        loop.run_until_complete(client.start(token))
    except discord.LoginFailure:
        _error = "Discord rejected the token - reset it in the Developer Portal"
    except discord.PrivilegedIntentsRequired:
        _error = "turn on Message Content Intent for the bot in the Developer Portal"
    except Exception as e:
        _error = f"{type(e).__name__}: {e}"
        logbook.exception(NAME, "client stopped")
    finally:
        try:
            loop.run_until_complete(client.close())
        except Exception:
            pass
        loop.close()


# ---------------------------------------------------------------------------
# Plugin interface
# ---------------------------------------------------------------------------
def start(model):
    global _thread, _model, _error

    if running():
        return True, "discord: already connected"

    problem = why_unavailable()

    if problem:
        return False, problem

    token, owners = _credentials()
    _model, _error = model, ""
    _thread = threading.Thread(target=_run, args=(token, owners), daemon=True, name="discord")
    _thread.start()

    channel = settings().get("channel") or "DMs only"

    return True, (f"discord: connecting - {len(owners)} owner(s), {channel}, "
                  f"approval: {_mode()}")


def stop():
    if _loop is not None and _client is not None and running():
        try:
            asyncio.run_coroutine_threadsafe(_client.close(), _loop).result(timeout=5)
        except Exception:
            pass

    if _thread is not None:
        _thread.join(timeout=5)

    return True, "discord: disconnected"


def status():
    user = getattr(_client, "user", None) if running() else None
    lines = [f"discord: {'connected as ' + str(user) if user else 'connecting' if running() else 'off'}"]

    if _error:
        lines.append(f"  last error: {_error}")

    s = settings()
    tools = s.get("tools")
    lines += [
        f"  channel: {s.get('channel') or 'DMs only'}",
        f"  tools: {'all' if not isinstance(tools, list) else ', '.join(tools)}",
        f"  approval: {_mode()} - /discord approval auto|discord|desk",
        f"  answered {_answered}, ignored {len(_ignored)} non-owner(s)",
    ]

    return "\n".join(lines)


def command(text):
    """/discord approval auto|discord|desk"""
    word, _, rest = text.partition(" ")

    if word.lower() != "approval":
        return "discord: on | off | approval auto|discord|desk"

    mode = rest.strip().lower()

    if mode not in APPROVAL_MODES:
        return (f"discord approval is {_mode()}. auto = no asking, discord = she asks in "
                "the chat (reply y/n), desk = the popup here. /discord approval <mode>")

    config._store(f"plugins.{NAME}.approval", mode)
    block = config._plugins_cfg.setdefault(NAME, {})

    if isinstance(block, dict):
        block["approval"] = mode

    extra = {"auto": " - commands and file changes from Discord run without asking "
                     "(her own folder and config folders still ask in the chat).",
             "discord": " - she'll ask in the chat; reply y or n.",
             "desk": " - she'll ask on this screen; from your phone that times out as a no."}[mode]

    return f"discord approval: {mode} (saved){extra}"
