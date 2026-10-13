#!/usr/bin/env python3
"""Poke a running assistant through its control channel.

Stdlib only - no venv needed, which matters because Hyprland's `exec`
runs outside the assistant's virtualenv.

    python3 ai-voice-ctl.py ptt    # toggle listening / interrupt
    python3 ai-voice-ctl.py stop   # interrupt only
    python3 ai-voice-ctl.py quit

Linux and macOS: a unix socket. Windows: a localhost port and a key,
read from %LOCALAPPDATA%\\ai-voice\\control.json (see control.py).
"""
import json
import os
import socket
import sys

SOCKET_PATH = os.environ.get(
    "AI_VOICE_SOCKET",
    os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "ai-voice.sock"),
)


def port_file():
    """Same place control.port_file() writes to."""
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".cache")
    return os.path.join(base, "ai-voice", "control.json")


def connect():
    """(socket, prefix) or (None, why)."""
    if hasattr(socket, "AF_UNIX") and os.name != "nt":
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(3)

        try:
            client.connect(SOCKET_PATH)
        except OSError as e:
            client.close()
            return None, f"{SOCKET_PATH}: {e}"

        return client, b""

    try:
        with open(port_file(), encoding="utf-8") as f:
            info = json.load(f)

        client = socket.create_connection(("127.0.0.1", int(info["port"])), timeout=3)
    except (OSError, ValueError, KeyError, TypeError) as e:
        return None, f"{port_file()}: {e}"

    return client, str(info["key"]).encode() + b" "


def main():
    command = (sys.argv[1] if len(sys.argv) > 1 else "ptt").strip().lower()
    client, prefix = connect()

    if client is None:
        print(f"ai-voice not running? ({prefix})", file=sys.stderr)
        return 1

    try:
        client.sendall(prefix + command.encode() + b"\n")
        reply = client.recv(16).decode().strip()
    except OSError as e:
        print(f"send failed: {e}", file=sys.stderr)
        return 1
    finally:
        client.close()

    if reply != "ok":
        print(f"unknown command: {command}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
