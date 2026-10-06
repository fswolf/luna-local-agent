"""Twitch stream chat.

    /twitch on | off | status

Reads a channel's chat over Twitch's IRC gateway and answers anything
with her name in it - out loud by default, the same as pomf. Everything
about *who* gets answered and what she may do about it is chatroom.py's
job; this file is the transport.

## Reading needs nothing

Twitch lets anyone read a public chat by logging in as "justinfan"
plus a number, with no account and no token. That is the default, and
it means she can never post: there's nothing to post as.

## Posting needs a bot account

To have her reply in chat as well, make a separate Twitch account for
her - not your own; the same reason the pomf plugin never posts from
yours - get it a user access token with the chat:edit and chat:read
scopes, and put both outside the repo in ~/.config/ai-voice/twitch.json:

    {"username": "lunabot", "oauth": "oauth:abc123..."}

Then set "post_replies": true. Without the file, that setting is
refused at start rather than failing quietly.

Twitch recommends EventSub over IRC for new bots. IRC still works, needs
no registered app, and reads anonymously, which EventSub can't; if
Twitch ever turns it off, this is the file that changes.
"""
import json
import os
import random
import re
import socket
import ssl
import threading
import time

from datetime import datetime

import chatroom
import config
import logbook
import timeutil

NAME = "twitch"
SUMMARY = "answers Twitch stream chat out loud (and in chat, with a bot account)"

HOST = "irc.chat.twitch.tv"
PORT = 6697
CREDENTIALS_FILE = os.path.expanduser("~/.config/ai-voice/twitch.json")

DEFAULTS = {
    "channel": "",
    "speak": True,
    "post_replies": False,
    "max_reply_chars": 450,
    # The usual chat bots. Answering a bot is how a loop starts.
    "ignore": ["Nightbot", "StreamElements", "Streamlabs", "Moobot",
               "Fossabot", "Sery_Bot", "SoundAlerts"],
}

# Twitch's limit for an ordinary account is 20 messages in 30 seconds;
# going over gets the account locked out of chat for half an hour. One
# reply is one message here, so a two-second gap is far inside it.
SEND_INTERVAL = 2.0
MAX_CHARS = 500          # Twitch's own hard limit per message
RECV_TIMEOUT = 30
DEAD_AFTER = 360         # Twitch pings about every five minutes

_room = None
_thread = None
_stop = threading.Event()
_lock = threading.Lock()

_running = False
_connected = False
_last_error = ""
_login = ""

_sock = None
_send_lock = threading.Lock()
_last_send = 0.0

_lines = 0
_last_line_at = 0.0
_posted = 0


def settings():
    merged = dict(DEFAULTS)
    merged.update(config.plugin_settings(NAME))

    return merged


def _channel():
    """The channel's login name: lower case, no '#', no URL around it."""
    raw = str(settings().get("channel", "")).strip()
    raw = re.sub(r"^https?://(www\.)?twitch\.tv/", "", raw, flags=re.I)

    return raw.strip("/#").split("/")[0].lower()


def _credentials():
    """(username, oauth) for posting, from outside the repo, or ("", "")."""
    try:
        with open(CREDENTIALS_FILE) as handle:
            parsed = json.load(handle)
    except FileNotFoundError:
        return "", ""
    except (ValueError, OSError) as e:
        logbook.warn(NAME, "couldn't read %s: %s", CREDENTIALS_FILE, e)

        return "", ""

    if not isinstance(parsed, dict):
        return "", ""

    user = str(parsed.get("username", "")).strip().lower()
    token = str(parsed.get("oauth", "")).strip()

    if token and not token.startswith("oauth:"):
        token = "oauth:" + token

    return user, token


def available():
    return not why_unavailable()


def why_unavailable():
    if not _channel():
        return 'no channel set - "twitch": {"channel": "yourname"} under plugins'

    block = settings()

    if block.get("post_replies") and not all(_credentials()):
        return (f"post_replies needs a bot account - put {{\"username\": ..., "
                f"\"oauth\": \"oauth:...\"}} in {CREDENTIALS_FILE}, or set "
                f"post_replies to false to just listen")

    if not block.get("post_replies") and not block.get("speak", True):
        return "speak and post_replies are both off - she'd answer into the void"

    return ""


# ---------------------------------------------------------------------------
# The wire
# ---------------------------------------------------------------------------
def _parse(line):
    """(tags, prefix, command, params) for one Twitch IRC line.

    Twitch puts IRCv3 tags in front - "@display-name=Ryan;mod=0 :ryan!...
    PRIVMSG #chan :hi" - and the display name lives there, with the
    capitalisation people actually chose.
    """
    tags = {}

    if line.startswith("@"):
        raw, _, line = line[1:].partition(" ")

        for item in raw.split(";"):
            key, _, value = item.partition("=")
            tags[key] = (value.replace(r"\s", " ").replace(r"\:", ";")
                         .replace(r"\\", "\\"))

    prefix = ""

    if line.startswith(":"):
        prefix, _, line = line[1:].partition(" ")

    head, sep, trailing = line.partition(" :")
    parts = head.split()
    params = parts[1:] + ([trailing] if sep else [])

    return tags, prefix, (parts[0].upper() if parts else ""), params


def _send(line):
    """One line, throttled. Nothing that isn't printable goes out:
    CR or LF in a message is a second command on a line protocol."""
    global _last_send

    with _send_lock:
        if _sock is None:
            return False

        wait = SEND_INTERVAL - (time.time() - _last_send)

        if wait > 0:
            time.sleep(wait)

        try:
            _sock.sendall(line.encode("utf-8", "replace")[:510] + b"\r\n")
        except OSError as e:
            logbook.warn(NAME, "send failed: %s", e)

            return False

        _last_send = time.time()

        return True


def _post(text):
    global _posted

    limit = min(int(settings().get("max_reply_chars", 450)), MAX_CHARS)
    clean = " ".join("".join(c if ord(c) >= 32 else " " for c in str(text)).split())

    # Twitch reads a message starting with "/" or "." as a chat command.
    # Her reply should never be able to /ban somebody.
    clean = clean.lstrip("/.")

    if len(clean) > limit:
        clean = clean[:limit - 1].rsplit(" ", 1)[0] + "…"

    if clean and _send(f"PRIVMSG #{_channel()} :{clean}"):
        _posted += 1


def _connect_once():
    global _sock, _connected, _last_error, _lines, _last_line_at, _login

    channel = _channel()
    user, token = _credentials()
    posting = bool(settings().get("post_replies")) and user and token

    connection = socket.create_connection((HOST, PORT), timeout=30)
    connection = ssl.create_default_context().wrap_socket(connection, server_hostname=HOST)
    connection.settimeout(RECV_TIMEOUT)

    _login = user if posting else f"justinfan{random.randint(10000, 99999)}"
    hello = ["CAP REQ :twitch.tv/tags twitch.tv/commands"]
    hello.append(f"PASS {token}" if posting else "PASS SCHMOOPIIE")
    hello += [f"NICK {_login}", f"JOIN #{channel}"]

    for line in hello:
        connection.sendall((line + "\r\n").encode())

    buffer = b""
    last_traffic = time.time()
    _sock = connection

    try:
        while not _stop.is_set():
            try:
                chunk = connection.recv(4096)
            except socket.timeout:
                if time.time() - last_traffic > DEAD_AFTER:
                    raise OSError("no traffic - the connection is gone")
                continue

            if not chunk:
                raise OSError("closed by Twitch")

            last_traffic = time.time()
            buffer += chunk

            while b"\r\n" in buffer:
                raw, _, buffer = buffer.partition(b"\r\n")
                tags, prefix, command, params = _parse(raw.decode("utf-8", "replace"))
                _lines += 1
                _last_line_at = time.time()

                if command == "PING":
                    connection.sendall(f"PONG :{params[-1] if params else ''}\r\n".encode())
                elif command == "RECONNECT":
                    # Twitch's way of saying it's restarting that server.
                    raise OSError("Twitch asked us to reconnect")
                elif command == "NOTICE" and "authentication failed" in (params[-1] if params else "").lower():
                    raise PermissionError("Twitch refused the oauth token in twitch.json")
                elif command == "ROOMSTATE" or (command == "366"):
                    if not _connected:
                        _connected = True
                        _last_error = ""
                        logbook.info(NAME, "in #%s as %s", channel, _login)
                elif command == "PRIVMSG" and len(params) >= 2:
                    _message(tags, prefix, params[-1])
    finally:
        _connected = False
        _sock = None

        try:
            connection.close()
        except OSError:
            pass


def _message(tags, prefix, text):
    who = tags.get("display-name") or prefix.split("!", 1)[0]

    # /me arrives wrapped in CTCP ACTION. It's still something said.
    if text.startswith("\x01ACTION ") and text.endswith("\x01"):
        text = text[8:-1]

    _room.saw(who, text)


def _listen_loop():
    global _last_error

    delay = 2

    while not _stop.is_set():
        try:
            _connect_once()
            delay = 2
        except PermissionError as e:
            # Retrying a bad token only gets the account looked at.
            _last_error = str(e)
            logbook.warn(NAME, "%s - stopping", e)
            break
        except Exception as e:
            _last_error = f"{type(e).__name__}: {e}"[:140]
            logbook.warn(NAME, "connection: %s", _last_error)

        if _stop.is_set():
            break

        time.sleep(delay + random.uniform(0, 1))
        delay = min(delay * 2, 120)


# ---------------------------------------------------------------------------
# The plugin interface
# ---------------------------------------------------------------------------
def start(model):
    global _room, _thread, _running

    with _lock:
        if _running:
            return False, "Already reading Twitch chat."

        problem = why_unavailable()

        if problem:
            return False, problem

        block = settings()
        channel = _channel()
        post = bool(block.get("post_replies"))
        user, _token = _credentials()

        merged = dict(block)

        # Her own account goes in the ignore list when she posts, or one
        # reply with her name in it answers itself forever.
        if post and user:
            merged["ignore"] = tuple(block.get("ignore", ())) + (user,)

        _room = chatroom.ChatRoom(
            NAME, owner=channel, settings=merged,
            where=f"{channel}'s Twitch stream chat",
            reply=(lambda _who, answer: _post(answer)) if post else None,
        )
        _room.start(model)

        _stop.clear()
        _thread = threading.Thread(target=_listen_loop, daemon=True)
        _thread.start()
        _running = True

    how = {(True, True): "out loud and in chat", (True, False): "in chat only, silently",
           (False, True): "out loud - she never posts"}[(post, bool(block.get("speak", True)))]

    return True, (f"Reading twitch.tv/{channel}. She'll answer anything with "
                  f"\"{config.AGENT_NAME}\" in it, {how}.")


def stop():
    global _running

    with _lock:
        if not _running:
            return False, "Not reading Twitch chat."

        _stop.set()

        if _room is not None:
            _room.stop()

        if _sock is not None:
            _send(f"PART #{_channel()}")

        _running = False

    return True, "Stopped reading Twitch chat."


def running():
    return _running


def status():
    if not _running:
        problem = why_unavailable()

        return f"twitch: off ({problem})" if problem else "twitch: off"

    block = settings()
    where = "connected" if _connected else f"reconnecting ({_last_error or 'starting'})"
    lines = [f"twitch: {where} to #{_channel()} as {_login or '...'}"]

    if _lines:
        ago = timeutil.relative(datetime.fromtimestamp(_last_line_at), datetime.now())
        lines.append(f"  {_lines} lines from Twitch, last {ago}")
    else:
        lines.append("  nothing from Twitch yet")

    lines.append(f"  posts replies as {_login} ({_posted} sent)" if block.get("post_replies")
                 else "  read-only - she answers out loud, never in chat")
    lines.extend(_room.summary())

    if not _lines:
        lines.append("  -> nothing arriving. Check the network, and /log for the error.")
    elif not _room.seen:
        lines.append(f"  -> connected, but no chat yet - is #{_channel()} the right "
                     "channel name, and is anyone talking?")
    elif not _room.answered:
        lines.append(f"  -> chat is arriving, but nobody's said \"{config.AGENT_NAME}\" "
                     "(or they hit a cooldown).")

    return "\n".join(lines)
