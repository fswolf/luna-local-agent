"""YouTube live chat.

    /youtube on | off | status

Reads a live stream's chat through the YouTube Data API and answers
anything with her name in it, out loud. Read-only: posting to YouTube
chat needs a full Google OAuth sign-in and costs 50 quota units a
message, which is a different plugin.

## What it needs

An API key - no sign-in. In Google Cloud Console: create a project,
enable "YouTube Data API v3", create an API key (restrict it to that
API). Put it outside the repo, in ~/.config/ai-voice/youtube.json:

    {"api_key": "AIza..."}

or the YOUTUBE_API_KEY environment variable.

Then say which stream, under "youtube" in config.json:

    "video":   "https://www.youtube.com/watch?v=XXXX"  (or just the id)
    "channel": "@YourHandle"   - finds whatever that channel has live now

"video" wins when both are set. "channel" reads the channel's public
/live page to find the stream, which costs no quota but is a web page,
not an API - if YouTube changes it, set "video" instead.

## Quota

The key gets 10,000 units a day. Finding the stream is 1, and each poll
of the chat is 1. YouTube says how long to wait between polls; this
waits at least poll_seconds (default 5), which is about 14 hours of
chat a day. Run out and it says so and waits for the reset (midnight
Pacific) rather than hammering a key that will only say no.
"""
import json
import os
import re
import threading
import time

from datetime import datetime, timedelta, timezone

import requests

import chatroom
import config
import logbook
import timeutil

NAME = "youtube"
SUMMARY = "answers YouTube live chat out loud (read-only, needs an API key)"

API = "https://www.googleapis.com/youtube/v3"
CREDENTIALS_FILE = os.path.expanduser("~/.config/ai-voice/youtube.json")

DEFAULTS = {
    "video": "",
    "channel": "",
    "poll_seconds": 5,
    "speak": True,
    "ignore": ["Nightbot", "StreamElements", "Streamlabs", "Moobot", "Fossabot"],
}

_room = None
_thread = None
_stop = threading.Event()
_lock = threading.Lock()

_running = False
_chat_id = ""
_video_id = ""
_title = ""
_last_error = ""
_polls = 0
_messages = 0
_last_poll_at = 0.0
_quota_until = 0.0


def settings():
    merged = dict(DEFAULTS)
    merged.update(config.plugin_settings(NAME))

    return merged


def _api_key():
    key = os.environ.get("YOUTUBE_API_KEY", "").strip()

    if key:
        return key

    try:
        with open(CREDENTIALS_FILE) as handle:
            parsed = json.load(handle)
    except FileNotFoundError:
        return ""
    except (ValueError, OSError) as e:
        logbook.warn(NAME, "couldn't read %s: %s", CREDENTIALS_FILE, e)

        return ""

    return str(parsed.get("api_key", "")).strip() if isinstance(parsed, dict) else ""


def available():
    return not why_unavailable()


def why_unavailable():
    if not _api_key():
        return (f'no API key - put {{"api_key": "AIza..."}} in {CREDENTIALS_FILE} '
                "(Google Cloud Console, YouTube Data API v3)")

    block = settings()

    if not str(block.get("video", "")).strip() and not str(block.get("channel", "")).strip():
        return ('no stream set - "youtube": {"video": "<url or id>"} or '
                '{"channel": "@YourHandle"} under plugins')

    if not block.get("speak", True):
        return "speak is off, and this plugin can't post - she'd answer into the void"

    return ""


# ---------------------------------------------------------------------------
# Finding the chat
# ---------------------------------------------------------------------------
_VIDEO_ID = re.compile(r"(?:v=|youtu\.be/|/live/|/shorts/)([A-Za-z0-9_-]{11})")


def _video_from_setting(raw):
    raw = str(raw or "").strip()

    if re.fullmatch(r"[A-Za-z0-9_-]{11}", raw):
        return raw

    match = _VIDEO_ID.search(raw)

    return match.group(1) if match else ""


def _video_from_channel(handle):
    """The video a channel has live right now, from its public /live
    page. No quota. The page's canonical link points at the stream when
    there is one, and at the channel when there isn't."""
    handle = str(handle or "").strip()
    handle = re.sub(r"^https?://(www\.)?youtube\.com/", "", handle).strip("/")

    if not handle.startswith(("@", "channel/", "c/", "user/")):
        handle = "@" + handle

    page = requests.get(
        f"https://www.youtube.com/{handle}/live", timeout=10,
        headers={"Accept-Language": "en", "User-Agent": "Mozilla/5.0"},
        # Without this the EU consent wall answers instead of the page.
        cookies={"CONSENT": "YES+1"},
    )
    page.raise_for_status()
    match = re.search(r'<link rel="canonical" href="[^"]*watch\?v=([A-Za-z0-9_-]{11})', page.text)

    return match.group(1) if match else ""


def _get(path, **params):
    """One Data API call. The key goes in a header, not the URL, so it
    never lands in a log line or an error message."""
    response = requests.get(f"{API}/{path}", params=params, timeout=15,
                            headers={"X-Goog-Api-Key": _api_key()})

    if response.status_code != 200:
        try:
            error = response.json()["error"]
            reason = (error.get("errors") or [{}])[0].get("reason", "")
            message = error.get("message", "")
        except (ValueError, KeyError, TypeError):
            reason, message = "", response.text[:200]

        raise _ApiError(response.status_code, reason, message)

    return response.json()


class _ApiError(Exception):
    def __init__(self, status, reason, message):
        super().__init__(f"HTTP {status} {reason}: {message}"[:200])
        self.status, self.reason = status, reason


def _find_chat():
    """(video id, live chat id, title), or raise with something a
    person can act on."""
    block = settings()
    video = _video_from_setting(block.get("video"))

    if not video and block.get("channel"):
        video = _video_from_channel(block["channel"])

        if not video:
            raise LookupError(f"{block['channel']} doesn't look live right now")

    if not video:
        raise LookupError("couldn't read a video id from the \"video\" setting")

    data = _get("videos", part="snippet,liveStreamingDetails", id=video)
    items = data.get("items") or []

    if not items:
        raise LookupError(f"no video {video} - private, deleted, or a typo")

    details = items[0].get("liveStreamingDetails") or {}
    chat = details.get("activeLiveChatId", "")

    if not chat:
        raise LookupError("that video isn't live (or its chat is off)")

    return video, chat, items[0].get("snippet", {}).get("title", "")


# ---------------------------------------------------------------------------
# Polling
# ---------------------------------------------------------------------------
def _quota_reset():
    """A few minutes past the next midnight Pacific, when the daily
    quota comes back, as a timestamp."""
    try:
        from zoneinfo import ZoneInfo

        pacific = ZoneInfo("America/Los_Angeles")
    except Exception:
        pacific = timezone(timedelta(hours=-8))  # no tz database: close enough

    now = datetime.now(pacific)
    midnight = (now + timedelta(days=1)).replace(hour=0, minute=5, second=0, microsecond=0)

    return midnight.timestamp()


def _poll_loop():
    global _chat_id, _video_id, _title, _last_error, _polls, _messages
    global _last_poll_at, _quota_until

    page = None
    first = True
    backoff = 5

    while not _stop.is_set():
        if _quota_until and time.time() < _quota_until:
            _stop.wait(60)
            continue

        try:
            if not _chat_id:
                _video_id, _chat_id, _title = _find_chat()
                page, first = None, True
                logbook.info(NAME, "reading chat of %s (%s)", _video_id, _title[:60])

            params = {"liveChatId": _chat_id, "part": "snippet,authorDetails",
                      "maxResults": 200}

            if page:
                params["pageToken"] = page

            data = _get("liveChat/messages", **params)
            _polls += 1
            _last_poll_at = time.time()
            _last_error = ""
            backoff = 5
            page = data.get("nextPageToken") or page

            # The first page is the backlog from before she arrived.
            # Answering it would be replying to a conversation that's
            # over; it's only read for context.
            for item in data.get("items") or []:
                snippet = item.get("snippet") or {}

                if snippet.get("type") not in ("textMessageEvent", "superChatEvent"):
                    continue

                who = (item.get("authorDetails") or {}).get("displayName", "")
                text = snippet.get("displayMessage", "")
                _messages += 1

                if first:
                    _room.remember(who, text)
                else:
                    _room.saw(who, text)

            first = False

            if data.get("offlineAt"):
                _last_error = "the stream has ended"
                _chat_id = ""
                _stop.wait(60)
                continue

            wait = max(float(settings().get("poll_seconds", 5)),
                       int(data.get("pollingIntervalMillis") or 0) / 1000)
            _stop.wait(wait)

        except _ApiError as e:
            _last_error = str(e)

            if e.reason in ("quotaExceeded", "dailyLimitExceeded"):
                _quota_until = _quota_reset()
                logbook.warn(NAME, "daily quota used up - waiting for the reset")
                _last_error = "daily quota used up - waits for midnight Pacific"
            elif e.reason in ("liveChatEnded", "liveChatNotFound", "liveChatDisabled"):
                _chat_id = ""
                _stop.wait(30)
            elif e.status in (400, 403) and e.reason in ("keyInvalid", "accessNotConfigured", "forbidden"):
                logbook.warn(NAME, "%s - stopping", e)
                break  # retrying a bad key only burns quota
            else:
                logbook.warn(NAME, "%s", e)
                _stop.wait(backoff)
                backoff = min(backoff * 2, 120)

        except LookupError as e:
            # Not live yet is normal before a stream starts - check
            # again in a minute, which costs 1 unit with "video" set and
            # nothing with "channel".
            _last_error = str(e)
            _stop.wait(60)

        except Exception as e:
            _last_error = f"{type(e).__name__}: {e}"[:140]
            logbook.warn(NAME, "%s", _last_error)
            _stop.wait(backoff)
            backoff = min(backoff * 2, 120)


# ---------------------------------------------------------------------------
# The plugin interface
# ---------------------------------------------------------------------------
def start(model):
    global _room, _thread, _running, _chat_id, _quota_until, _polls, _messages

    with _lock:
        if _running:
            return False, "Already reading YouTube chat."

        problem = why_unavailable()

        if problem:
            return False, problem

        block = settings()
        _chat_id, _quota_until, _polls, _messages = "", 0.0, 0, 0
        stream = block.get("video") or block.get("channel")

        _room = chatroom.ChatRoom(
            NAME, owner=config.AGENT_NAME, settings=block,
            where="a YouTube live stream's chat",
        )
        _room.start(model)

        _stop.clear()
        _thread = threading.Thread(target=_poll_loop, daemon=True)
        _thread.start()
        _running = True

    return True, (f"Reading YouTube chat for {stream}. She'll answer anything "
                  f"with \"{config.AGENT_NAME}\" in it, out loud.")


def stop():
    global _running

    with _lock:
        if not _running:
            return False, "Not reading YouTube chat."

        _stop.set()

        if _room is not None:
            _room.stop()

        _running = False

    return True, "Stopped reading YouTube chat."


def running():
    return _running


def status():
    if not _running:
        problem = why_unavailable()

        return f"youtube: off ({problem})" if problem else "youtube: off"

    if _chat_id:
        where = f"reading {_video_id}" + (f" - {_title[:50]}" if _title else "")
    else:
        where = f"waiting ({_last_error or 'finding the stream'})"

    lines = [f"youtube: {where}"]

    if _polls:
        ago = timeutil.relative(datetime.fromtimestamp(_last_poll_at), datetime.now())
        lines.append(f"  {_polls} polls ({_polls} quota units this run), "
                     f"{_messages} chat messages, last poll {ago}")

    if _last_error and _chat_id:
        lines.append(f"  !! {_last_error}")

    lines.append("  read-only - she answers out loud, never in chat")
    lines.extend(_room.summary())

    if _chat_id and not _room.seen:
        lines.append("  -> reading the chat, but nobody's said anything yet.")
    elif _room.seen and not _room.answered:
        lines.append(f"  -> chat is arriving, but nobody's said \"{config.AGENT_NAME}\" "
                     "(or they hit a cooldown).")

    return "\n".join(lines)
