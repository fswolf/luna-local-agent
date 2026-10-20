"""Hologram fans: Luna live on a spinning LED fan.

Two kinds work:

- An HDMI fan is just a screen: open /portrait/?fan=1 on it (black
  background, all of her, centred). Nothing here is needed.
- A WiFi fan run by the Holoscope app (P56, PD42, P42, HS56...): she is
  streamed to it live, about 15 frames a second. This file is that link.

How a Holoscope fan talks (reverse-engineered by github.com/trackerr/p56-studio,
MIT; see its PROTOCOL.md - all credit to them): backwards. Luna is the
server. Every 3 s she broadcasts "<her-ip>HS" on UDP 8988; a fan that
hears it connects to her on TCP 6666 and reports its status (which model
it is). To show her live: start a cast (26, the fan answers 29), then send
a frame at least every 130 ms. Each frame is one JPEG in the fan's own
layout (the picture unrolled around the centre, one strip per LED arm),
in a fixed 20480-byte packet. The portrait page renders that JPEG on the
GPU (portrait/viewer/fan.js) and posts it to /portrait/fan/frame; this
relays it. When frames stop, the fan goes back to its own clips.

On by config.json, "portrait": {"fan": {"cast": true}}. The fan has to
be on the same network: join its own WiFi (3D-...-xxxx, password usually
12345678; the fan is 192.168.4.1), or have the Holoscope app put it on
your router. "ip": "<fan ip>" sends the announcement straight to it too.

Never sent: format card (07), factory reset (08), delete (80), and the
Bluetooth commands (WiFi and Bluetooth share one radio on these fans; with
Bluetooth audio connected a P56 drops off WiFi).

    python3 holofan.py sim [type]   a pretend fan on this machine: it
                                    connects to Luna, takes the frames and
                                    writes /tmp/holofan-preview.png (Pillow)
                                    - what the real fan would show
"""
import socket
import struct
import threading
import time

try:
    import config
    import logbook
except Exception:  # run on its own (the simulator)
    config = None
    logbook = None

TCP_PORT = 6666
UDP_PORT = 8988
PACKET = 20480                  # a cast frame, always this size
MAX_JPEG = PACKET - 4           # 5A 28 <jpeg> ... 55 F5

# fan type (what its status reports) -> model, angles, LEDs per arm, arms
# (0 = raw polar picture), auto-brightness gain, how well it's known.
# From p56-studio's transcode.rs; P56 (8) is the one verified on a real fan.
TYPES = {
    1: ("HS65", 960, 192, 4, 1.5, "jpeg"),   2: ("HS56", 960, 168, 4, 1.5, "jpeg"),
    3: ("HS80", 1440, 240, 1, 1.5, "jpeg"),  4: ("P50", 960, 144, 4, 1.5, "jpeg"),
    5: ("HD30", 960, 128, 2, 1.5, "jpeg"),   6: ("P45", 600, 133, 0, 2.0, "legacy"),
    7: ("P42", 490, 122, 0, 1.6, "legacy"),  8: ("P56", 960, 172, 4, 1.5, "jpeg"),
    11: ("P62", 960, 184, 4, 1.5, "jpeg"),   12: ("HL20", 512, 85, 0, 1.6, "legacy"),
    13: ("HL33", 490, 128, 0, 1.6, "legacy"), 14: ("PD45", 960, 176, 2, 1.4, "jpeg"),
    15: ("PD42", 490, 122, 0, 1.6, "legacy"), 17: ("type 17", 960, 192, 2, 1.5, "jpeg"),
}


def geometry(fan_type):
    """What the portrait needs to draw for this fan, or None if we can't."""
    t = TYPES.get(fan_type)
    if not t:
        return None
    model, angles, radius, arms, gain, support = t
    w, h = (radius * arms, angles // arms) if arms in (2, 4) else (radius, angles)
    return {"type": fan_type, "model": model, "angles": angles, "radius": radius, "arms": arms,
            "gain": gain, "cap": 100 if fan_type == 14 else 150, "soft": fan_type in (5, 14, 17),
            "order": [0, 3, 2, 1] if arms == 4 else [0, 1, 0, 0], "width": w, "height": h,
            "support": support, "max_jpeg": MAX_JPEG}


def _cmd(op, arg=None):
    return bytes([0x5A, op, op, 0xF5]) if arg is None else bytes([0x5A, op, arg, arg, 0xF5])


HEARTBEAT = bytes([0x5A, 0x0D, 0x0D, 0xF5, 0x00])
INFO = bytes([0x5A, 0x1C, 0x1C, 0xF5, 0x00])


def _log(level, msg, *args):
    if logbook:
        getattr(logbook, level)("fan", msg, *args)
    else:
        print("fan:", msg % args if args else msg)


def _setting(key, default):
    fan = dict(getattr(config, "PORTRAIT_FAN", {}) or {}) if config else {}
    return fan.get(key, default)


# ---------------------------------------------------------------------------
# Luna's side
# ---------------------------------------------------------------------------
QUIET = 2.0          # s without a new frame from the portrait: the cast ends
SILENT = 12.0        # s without a word from an idle fan: it's gone (no FIN when unplugged)


class _State:
    def __init__(self):
        self.lock = threading.Lock()
        self.wlock = threading.Lock()   # one writer at a time on the fan's socket
        self.sock = None                # the connected fan
        self.ip = ""
        self.type = 0
        self.flags = 0
        self.brightness = 0
        self.heard = 0.0                # when the fan last said anything
        self.casting = False
        self.cast_ok = threading.Event()
        self.frame = None               # (jpeg, when, sender)
        self.sender = ""
        self.fps = 0.0
        self.error = ""
        self.started = False
        self.failed = 0.0               # when listening last failed (port taken)


_s = _State()


def enabled():
    return bool(getattr(config, "PORTRAIT_FAN_CAST", False)) if config else True


def status():
    with _s.lock:
        connected = _s.sock is not None
        g = geometry(_s.type) if connected and _s.type else None
        return {"enabled": enabled(), "running": _s.started, "connected": connected, "ip": _s.ip,
                "type": _s.type, "model": g["model"] if g else "", "geometry": g,
                "casting": _s.casting, "fps": round(_s.fps, 1) if _s.casting else 0,
                "playing": bool(_s.flags & 0x08), "on": bool(_s.flags & 0x40),
                "brightness": _s.brightness, "error": _s.error}


def push(jpeg, sender=""):
    """A frame from the portrait, already in the fan's layout.
    Returns (ok, active): ok False if it isn't one we can send, active
    False if another page has the fan (that page can stop rendering)."""
    if not (jpeg[:2] == b"\xff\xd8" and jpeg[-2:] == b"\xff\xd9" and len(jpeg) <= MAX_JPEG):
        return False, False
    now = time.monotonic()
    with _s.lock:
        # two pages casting at once would flicker: the first keeps the fan
        # until it has been quiet for QUIET seconds
        if _s.frame and _s.sender and sender != _s.sender and now - _s.frame[1] < QUIET:
            return True, False
        _s.frame, _s.sender = (jpeg, now, sender), sender
    return True, _s.sock is not None


def start():
    """Listen for a fan and announce Luna. Once; does nothing when
    portrait.fan.cast is off. If the port is taken it tries again at most
    every 30 s (start() is called with every frame)."""
    if _s.started or not enabled() or time.monotonic() - _s.failed < 30:
        return False
    try:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("0.0.0.0", TCP_PORT))
        server.listen(2)
    except OSError as e:
        _s.failed = time.monotonic()
        _s.error = f"can't listen on TCP {TCP_PORT}: {e}"
        _log("warn", _s.error)
        return False
    _s.started = True
    for target, name in ((_accept, "fan-accept"), (_announce, "fan-announce"), (_cast_loop, "fan-cast")):
        threading.Thread(target=_forever, args=(target, server), daemon=True, name=name).start()
    _log("info", "hologram fan: waiting for one on TCP %s", TCP_PORT)
    return True


def _forever(target, server):
    """Run a loop; if it ever breaks, say so and start it again."""
    while True:
        try:
            target(server)
        except Exception as e:  # noqa: BLE001 - a fan thread must not die quietly
            _s.error = f"{target.__name__}: {e}"
            _log("warn", "hologram fan: %s", _s.error)
            time.sleep(2)


def _own_ips(fan_ip):
    """This machine's address on the way to the fan (its own WiFi is
    192.168.4.x) and on the way out (the router)."""
    ips = []
    for target in (fan_ip or "192.168.4.1", "8.8.8.8"):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect((target, 9))
                ip = s.getsockname()[0]
            if ip not in ips and (not ip.startswith("127.") or target.startswith("127.")):
                ips.append(ip)
        except OSError:
            pass
    return ips


def _announce(_server):
    """'<ip>HS' on UDP 8988 every 3 s while no fan is connected."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        while True:
            if _s.sock is None:
                fan_ip = str(_setting("ip", "") or "").strip()
                for ip in _own_ips(fan_ip):
                    msg = (ip + "HS").encode()
                    targets = {"255.255.255.255", ip.rsplit(".", 1)[0] + ".255"}
                    if fan_ip:
                        targets.add(fan_ip)
                    for t in targets:
                        try:
                            sock.sendto(msg, (t, UDP_PORT))
                        except OSError:
                            pass
            time.sleep(3)


def _local(ip):
    """A fan is on the home network: never let the internet connect."""
    import ipaddress
    try:
        a = ipaddress.ip_address(ip)
        return a.is_private or a.is_loopback or a.is_link_local
    except ValueError:
        return False


def _accept(server):
    while True:
        conn, addr = server.accept()
        if not _local(addr[0]):
            _log("warn", "hologram fan: refused a connection from %s (not on this network)", addr[0])
            conn.close()
            continue
        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        conn.settimeout(2.0)
        with _s.lock:
            old, _s.sock, _s.ip = _s.sock, conn, addr[0]
            _s.type, _s.flags, _s.casting, _s.heard, _s.error = 0, 0, False, time.monotonic(), ""
        if old:
            try:
                old.close()
            except OSError:
                pass
        _log("info", "hologram fan connected from %s", addr[0])
        threading.Thread(target=_read, args=(conn,), daemon=True, name="fan-read").start()
        _write(conn, INFO)
        _write(conn, HEARTBEAT)


def _write(conn, data):
    try:
        with _s.wlock:
            conn.sendall(data)
        return True
    except OSError as e:
        # a send cut short leaves the fan mid-packet: start again from scratch
        _drop(conn, f"lost the fan: {e}")
        return False


def _drop(conn, why):
    with _s.lock:
        if _s.sock is not conn:
            return
        _s.sock, _s.casting, _s.type, _s.flags = None, False, 0, 0
        _s.error = why
    try:
        conn.close()
    except OSError:
        pass
    _log("info", "hologram fan: %s", why)


def _packets(buf):
    """Split what the fan sent into packets: (packets, rest)."""
    out = []
    while True:
        i = buf.find(b"\x5a")
        if i < 0:
            return out, b""
        buf = buf[i:]
        if len(buf) < 4:
            return out, buf
        op = buf[1]
        if op in (0x0E, 0x21, 0x22, 0x29):
            n = 4
        elif op == 0x85:
            n = 5
        elif op == 0x86:
            n = 11
        elif op == 0x8D:
            n = 126
        elif op == 0x84:
            n = 4 + struct.unpack(">H", buf[2:4])[0] + 2
        elif op == 0x8F:
            if len(buf) < 6:
                return out, buf
            n = 6 + struct.unpack(">H", buf[4:6])[0] + 2
        else:
            buf = buf[1:]
            continue
        if len(buf) < n:
            return out, buf
        out.append(buf[:n])
        buf = buf[n:]


def _read(conn):
    buf = b""
    while _s.sock is conn:
        try:
            data = conn.recv(4096)
        except socket.timeout:
            continue
        except OSError:
            data = b""
        if not data:
            _drop(conn, "the fan hung up")
            return
        _s.heard = time.monotonic()
        pkts, buf = _packets(buf + data)
        if len(buf) > 4096:                     # garbage, not a packet in progress
            buf = b""
        for p in pkts:
            if p[1] == 0x86:
                with _s.lock:
                    if _s.type != p[8]:
                        g = geometry(p[8])
                        _log("info", "hologram fan is a %s (type %s)%s", g["model"] if g else "fan", p[8],
                             "" if g and g["support"] == "jpeg" else
                             " - an older picture format: live may not show" if g else " - not one we can draw for")
                    _s.flags, _s.brightness, _s.type = p[2], p[4], p[8]
            elif p[1] == 0x29:
                _s.cast_ok.set()
            elif p[1] == 0x85:
                _s.error = f"the fan reported error {p[2]}"


def _cast_loop(_server):
    """Heartbeat while idle; while frames come, cast them on a steady beat
    (the last one again if no new one came - the fan needs one every 130 ms)."""
    last_beat = last_sent = 0.0
    count, count_t, beat = 0, time.monotonic(), time.monotonic()
    while True:
        fps = max(8.0, min(25.0, float(_setting("fps", 15) or 15)))
        beat = max(beat + 1.0 / fps, time.monotonic())   # a steady rate, not sleep + send time
        time.sleep(max(0.0, beat - time.monotonic()))
        now = time.monotonic()
        conn = _s.sock
        if conn is None:
            continue
        with _s.lock:
            frame = _s.frame
        if frame is None or now - frame[1] >= QUIET:
            if _s.casting and now - last_sent > QUIET:
                _s.casting = False
            if not _s.casting and now - last_sent > QUIET:
                if now - max(_s.heard, last_sent) > SILENT:
                    _drop(conn, "the fan went quiet (switched off?)")
                elif now - last_beat > 1.0:
                    last_beat = now
                    _write(conn, HEARTBEAT)
            continue
        if not _s.casting or now - last_sent > 1.0:
            # (re)start the cast: on, playing (a paused fan shows no cast), 26 -> 29
            if _s.flags and not _s.flags & 0x40 and not _write(conn, _cmd(0x01)):
                continue
            if _s.flags and not _s.flags & 0x08 and not _write(conn, _cmd(0x04)):
                continue
            _s.cast_ok.clear()
            if not _write(conn, _cmd(0x26)):
                continue
            _s.error = "" if _s.cast_ok.wait(1.0) else "the fan didn't answer the cast start (no 29) - sending anyway"
            time.sleep(0.07)
            _s.casting = True
            count, count_t = 0, time.monotonic()
        jpeg = frame[0]
        if _write(conn, b"\x5a\x28" + jpeg + b"\x00" * (PACKET - 4 - len(jpeg)) + b"\x55\xf5"):
            last_sent = time.monotonic()
            count += 1
        if now - count_t >= 2.0:
            _s.fps, count, count_t = count / (now - count_t), 0, now


# ---------------------------------------------------------------------------
# A pretend fan, for trying it all without one
# ---------------------------------------------------------------------------
def simulate(fan_type=8, out=None):
    """Hear Luna's announcement, connect, say we're a fan of fan_type,
    take the cast and save what a real fan would show."""
    import os
    import tempfile
    out = out or os.path.join(tempfile.gettempdir(), "holofan-preview.png")
    g = geometry(fan_type)
    if not g:
        raise SystemExit(f"unknown fan type {fan_type}")
    try:
        from PIL import Image
    except ImportError:
        Image = None
        print("no Pillow: counting frames only (pip install pillow for the picture)")
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    udp.bind(("", UDP_PORT))
    print(f"pretend {g['model']} (type {fan_type}) listening on UDP {UDP_PORT}...")
    while True:
        msg, _ = udp.recvfrom(256)
        if msg.endswith(b"HS"):
            host = msg[:-2].decode(errors="replace")
            break
    print("heard Luna at", host)
    s = socket.create_connection((host, TCP_PORT), timeout=10)
    status = bytes([0x5A, 0x86, 0x40 | 0x08 | 0x04, 0, 12, 0, 180, 0, fan_type, 0, 0xF5])
    s.sendall(status)
    latest = {"jpeg": None, "frames": 0}
    t0 = time.monotonic()

    def draw():         # in the background: drawing is slow and must not hold up reading
        while True:
            time.sleep(1.0)
            jpeg, n = latest["jpeg"], latest["frames"]
            if not jpeg:
                continue
            with open(out.replace(".png", ".jpg"), "wb") as f:
                f.write(jpeg)
            if Image:
                _preview(Image, jpeg, g).save(out)
            print(f"{n} frames, {n / (time.monotonic() - t0):.1f}/s, jpeg {len(jpeg)} B -> {out}")

    threading.Thread(target=draw, daemon=True).start()
    buf = b""
    while True:
        data = s.recv(65536)
        if not data:
            print("Luna hung up")
            return
        buf += data
        while buf:
            if buf[:2] == b"\x5a\x28":                     # a cast frame
                if len(buf) < PACKET:
                    break
                pkt, buf = buf[:PACKET], buf[PACKET:]
                latest["jpeg"] = pkt[2:-2].rstrip(b"\x00")
                latest["frames"] += 1
                continue
            if buf[:1] == b"\x5a" and len(buf) >= 4:
                if buf[3] != 0xF5 and len(buf) < 5:
                    break                                   # 5A op n n F5: wait for the rest
                op = buf[1]
                if op == 0x26:
                    s.sendall(bytes([0x5A, 0x29, 0x29, 0xF5]))
                elif op in (0x0D, 0x1C):
                    s.sendall(status)
                buf = buf[4 if buf[3] == 0xF5 else 5:]      # a padding byte after is skipped below
                continue
            if buf[:1] == b"\x5a":
                break
            buf = buf[1:]


def _preview(Image, jpeg, g, size=480):
    """Undo the fan layout: the round picture the spinning fan shows."""
    import io
    import math
    mat = Image.open(io.BytesIO(jpeg)).convert("RGB")
    px, (w, h) = mat.load(), mat.size
    rad, ang, arms = g["radius"], g["angles"], g["arms"]
    out = Image.new("RGB", (size, size))
    op = out.load()
    c = size / 2
    for y in range(size):
        for x in range(size):
            dx, dy = x + 0.5 - c, y + 0.5 - c
            r = math.hypot(dx, dy) / c
            if r >= 1:
                continue
            phi = math.atan2(dy, dx) % (2 * math.pi)
            rho = min(int(r * rad), rad - 1)
            a = int(phi / (2 * math.pi) * ang) % ang
            if arms in (2, 4):
                order = g["order"][:arms]
                q = ang // arms
                k, i = divmod(a, q)
                seg = order.index(k)
                X, Y = seg * rad + (rad - 1 - rho), q - 1 - i
            elif arms == 1:
                X, Y = rad - 1 - rho, ang - 1 - a
            else:
                X, Y = rho, a
            if 0 <= X < w and 0 <= Y < h:
                p = px[X, Y]
                op[x, y] = (p[2], p[1], p[0]) if arms == 1 else p
    return out


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "sim":
        simulate(int(sys.argv[2]) if len(sys.argv) > 2 else 8)
    else:
        print(__doc__)
