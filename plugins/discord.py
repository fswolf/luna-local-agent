"""Remote access over Discord - the owner talks to her from anywhere.

    /discord on           /discord off           /discord    (status)

Not a chat plugin. Stream chat is strangers, so it goes through
chatroom.py and its tool ceiling. This is the owner: messages from the
ids in the credentials file get a normal private turn with the full
tool list, and everyone else is ignored. Anyone you add to owner_ids
has the same reach as the person at the keyboard.

Writes don't ask when "discord" is in files.auto_approve_sources,
because nobody is at the desk to answer the popup. Take it out of that
list and remote writes ask on screen instead (and time out as a no if
nobody's there). The deny list (keys, .ssh, .env, shell startup files)
applies either way.

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

DEFAULTS = {"channel": "", "speak": False, "remember": True, "tools": None}

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
def _turn(text, who):
    import assistant

    s = settings()
    tools = s.get("tools")

    return assistant.respond_remote(
        text, _model, source=NAME, who=who,
        tools_allowed=list(tools) if isinstance(tools, list) else None,
        speak=bool(s.get("speak")), remember=bool(s.get("remember", True)),
    )


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
                    None, _turn, text, message.author.display_name)
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

    auto = NAME in config.FILES_AUTO_APPROVE_SOURCES
    channel = settings().get("channel") or "DMs only"

    return True, (f"discord: connecting - {len(owners)} owner(s), {channel}, "
                  f"writes {'without asking' if auto else 'ask on screen'}")


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
        f"  writes: {'without asking' if NAME in config.FILES_AUTO_APPROVE_SOURCES else 'ask on screen'}"
        " (deny list still applies)",
        f"  answered {_answered}, ignored {len(_ignored)} non-owner(s)",
    ]

    return "\n".join(lines)
