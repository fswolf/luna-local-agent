"""Control channel: how a hotkey outside Luna's window pokes her.

Wayland compositors don't hand global key grabs to applications, so on
Hyprland the compositor owns the hotkey and pokes us through this socket
instead:

    bind = SUPER, HOME, exec, python3 ~/ai-voice/ai-voice-ctl.py ptt

On Windows (no unix sockets in its Python) the same commands come in on
a localhost TCP port instead. The port is random and every command has
to carry a random key, both written to a file in your own profile
(%LOCALAPPDATA%\\ai-voice\\control.json) - so a web page that guesses
the port still can't say "quit". An AutoHotkey bind:

    #Home::Run "pythonw ai-voice-ctl.py ptt", "C:\\path\\to\\ai-voice"

Commands: ptt (toggle listening / interrupt), stop, quit.
"""
import hmac
import json
import os
import secrets
import socket
import threading

from config import CONTROL_SOCKET

UNIX = hasattr(socket, "AF_UNIX") and os.name != "nt"


def port_file():
    """Where the TCP port and key live. ai-voice-ctl.py works this out
    the same way - keep the two in step."""
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".cache")
    return os.path.join(base, "ai-voice", "control.json")


_key = {"value": None}


def _serve(server, model, handlers):
    while True:
        try:
            connection, _ = server.accept()
        except OSError:
            return

        handler = None

        try:
            connection.settimeout(3)
            line = connection.recv(128).decode("utf-8", "ignore").strip()

            if _key["value"] is not None:   # TCP: "<key> <command>"
                key, _, line = line.partition(" ")

                if not hmac.compare_digest(key, _key["value"]):
                    line = ""

            handler = handlers.get(line.strip().lower())
            connection.sendall(b"ok\n" if handler else b"unknown\n")
        except Exception:
            handler = None
        finally:
            connection.close()

        # Run the action *after* replying so the client script exits
        # immediately instead of blocking for the whole turn.
        if handler:
            try:
                handler(model)
            except Exception:
                pass


def _start_unix():
    # A stale socket file has to go before bind() will work - but only if
    # nothing is actually listening on it, or a second instance would
    # quietly steal the hotkey from the one already running.
    probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    probe.settimeout(1)

    try:
        probe.connect(CONTROL_SOCKET)
        return None, None  # somebody's home
    except OSError:
        pass
    finally:
        probe.close()

    try:
        try:
            os.unlink(CONTROL_SOCKET)
        except FileNotFoundError:
            pass

        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(CONTROL_SOCKET)
        os.chmod(CONTROL_SOCKET, 0o600)
        server.listen(8)
    except OSError:
        return None, None

    return server, CONTROL_SOCKET


def _start_tcp():
    path = port_file()

    # Another copy already running answers on the port in the file.
    try:
        with open(path, encoding="utf-8") as f:
            port = int(json.load(f)["port"])

        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return None, None
    except (OSError, ValueError, KeyError, TypeError):
        pass

    try:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind(("127.0.0.1", 0))
        server.listen(8)
        port = server.getsockname()[1]
        _key["value"] = secrets.token_hex(16)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"

        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"port": port, "key": _key["value"]}, f)

        os.replace(tmp, path)
    except OSError:
        return None, None

    return server, f"127.0.0.1:{port} (key in {path})"


def start(model, handlers):
    """Open the channel and serve it in the background.

    Returns a description of where it listens, or None if it couldn't
    (another copy running, stale file owned by another user, ...).
    """
    server, where = _start_unix() if UNIX else _start_tcp()

    if server is None:
        return None

    threading.Thread(
        target=_serve, args=(server, model, handlers), daemon=True
    ).start()

    return where


def cleanup():
    try:
        os.unlink(CONTROL_SOCKET if UNIX else port_file())
    except OSError:
        pass
