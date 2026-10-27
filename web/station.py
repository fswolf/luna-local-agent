"""Relay stations: talk to Luna from another room on an old phone or tablet.

A station is a web page Luna serves to your home network. Open it on a
phone or tablet, tap the button and talk: the recording comes here, she
answers like any spoken turn (the same memory, mood, people and tools),
and her voice plays on the tablet. Nothing to install on it.

    station.enabled   on/off (the settings page; off by default)
    station.port      HTTPS for the stations; port + 1 is the setup page

Browsers only let a page use the microphone over HTTPS, so Luna makes her
own: a small private certificate authority, made once, and a certificate
for this PC's address signed by it (needs the stations extra:
installer --extras stations). Each tablet trusts that authority once,
from the setup page, and is then paired with a one-time code from the
settings page's QR code. Nothing here needs a domain, an account or the
internet.

What keeps it safe:
  - off until you switch it on, and then only answering home-network
    addresses (private, link-local, loopback), never the internet
  - a device needs a pairing code that you made on this PC (single use,
    15 minutes), and keeps a token after that (stored hashed; removable)
  - her permission questions (writing a file, running a command) are
    asked on the station that asked, never answered for you
"""
import datetime
import hashlib
import io
import ipaddress
import json
import os
import secrets
import socket
import ssl
import sys
import tempfile
import threading
import time
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlsplit

import config
from core import logbook

FOLDER = os.path.expanduser("~/.config/ai-voice/station")
DEVICES_FILE = os.path.join(FOLDER, "devices.json")
COOKIE = "luna_station"
COOKIE_LIFE = 10 * 365 * 24 * 3600   # a paired device stays paired: renewed on every visit, until you unpair it
KEEP_KEY = "luna_station"          # the page's own copy of the token (localStorage), for a browser that drops cookies
PAIR_MINUTES = 15
MAX_AUDIO = 6 * 1024 * 1024        # about 3 minutes of 16 kHz mono
MAX_TYPED = 2000                   # characters typed in the station's box
ASK_SECONDS = 120                  # how long a permission question waits on the tablet
TURN_KEEP = 300                    # finished turns are forgotten after this

_state = {"servers": [], "error": "", "ip": "", "codes": {}}
_turns = {}                        # id -> Turn
_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Where she is on the network, and the certificates
# ---------------------------------------------------------------------------
def lan_ip():
    """This PC's address on the home network: the one its default route
    uses (a VPN or Docker network on 10.x or 172.x isn't it). Connecting a
    UDP socket sends nothing; it only asks the system which way it'd go."""
    for target in ("1.1.1.1", "192.168.255.255", "10.254.254.254"):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect((target, 1))
            ip = s.getsockname()[0]
            if ip and not ip.startswith("127."):
                return ip
        except OSError:
            pass
        finally:
            s.close()
    return "127.0.0.1"


def available():
    try:
        import cryptography  # noqa: F401

        return True
    except ImportError:
        return False


def _paths():
    return {k: os.path.join(FOLDER, f) for k, f in
            (("ca_key", "ca.key"), ("ca", "luna-ca.crt"), ("key", "server.key"), ("cert", "server.crt"))}


def _write_private(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)


def certificates(ip=None):
    """Make the authority once, and a server certificate for this address
    (again whenever the address changes or it nears its end). Returns the
    paths."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    ip = ip or lan_ip()
    p = _paths()
    os.makedirs(FOLDER, mode=0o700, exist_ok=True)
    now = datetime.datetime.now(datetime.timezone.utc)
    pem = serialization.Encoding.PEM
    raw = dict(encoding=pem, format=serialization.PrivateFormat.PKCS8,
               encryption_algorithm=serialization.NoEncryption())

    if not (os.path.isfile(p["ca"]) and os.path.isfile(p["ca_key"])):
        key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"Luna on {socket.gethostname()}"[:64]),
                          x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Luna (your own, made on this PC)")])
        ca = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
              .serial_number(x509.random_serial_number())
              .not_valid_before(now - datetime.timedelta(days=1))
              .not_valid_after(now + datetime.timedelta(days=3650))
              .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
              .add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=True, crl_sign=True,
                                           content_commitment=False, key_encipherment=False,
                                           data_encipherment=False, key_agreement=False,
                                           encipher_only=False, decipher_only=False), critical=True)
              .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
              # it can only ever vouch for home-network addresses and .local
              # names: even with its key, nobody could pass off a real site
              .add_extension(x509.NameConstraints(permitted_subtrees=[
                  *(x509.IPAddress(ipaddress.ip_network(n)) for n in
                    ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8", "169.254.0.0/16")),
                  x509.DNSName("local"), x509.DNSName("localhost")], excluded_subtrees=None), critical=True)
              .sign(key, hashes.SHA256()))
        _write_private(p["ca_key"], key.private_bytes(**raw))
        with open(p["ca"], "wb") as f:
            f.write(ca.public_bytes(pem))
        if os.path.isfile(p["cert"]):
            os.remove(p["cert"])                  # signed by an authority that's gone
        logbook.info("station", "made a certificate authority for the stations")

    with open(p["ca"], "rb") as f:
        ca = x509.load_pem_x509_certificate(f.read())
    with open(p["ca_key"], "rb") as f:
        ca_key = serialization.load_pem_private_key(f.read(), None)

    if os.path.isfile(p["cert"]):
        with open(p["cert"], "rb") as f:
            cert = x509.load_pem_x509_certificate(f.read())
        try:
            ips = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value \
                .get_values_for_type(x509.IPAddress)
        except x509.ExtensionNotFound:
            ips = []
        ends = getattr(cert, "not_valid_after_utc", None) or cert.not_valid_after.replace(tzinfo=datetime.timezone.utc)
        if ipaddress.ip_address(ip) in ips and ends - now > datetime.timedelta(days=30):
            return p

    host = socket.gethostname().split(".")[0] or "luna"
    names = [x509.IPAddress(ipaddress.ip_address(ip)), x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
             x509.DNSName(f"{host}.local"), x509.DNSName("localhost")]
    key = ec.generate_private_key(ec.SECP256R1())
    cert = (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, ip)]))
            .issuer_name(ca.subject).public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=397))     # phones refuse longer ones
            .add_extension(x509.SubjectAlternativeName(names), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
            .sign(ca_key, hashes.SHA256()))
    _write_private(p["key"], key.private_bytes(**raw))
    with open(p["cert"], "wb") as f:
        f.write(cert.public_bytes(pem) + ca.public_bytes(pem))      # with its authority, for the chain
    logbook.info("station", "certificate for %s", ip)
    return p


# ---------------------------------------------------------------------------
# Devices: pairing codes and tokens
# ---------------------------------------------------------------------------
def _hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def devices():
    try:
        with open(DEVICES_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_devices(data):
    os.makedirs(FOLDER, mode=0o700, exist_ok=True)
    _write_private(DEVICES_FILE, json.dumps(data, indent=2).encode())


def _clean_name(name):
    name = " ".join(str(name or "").split())[:30]
    return "".join(c for c in name if c.isalnum() or c in " -_'") or "station"


def new_pairing(name):
    """A one-time code for pairing one device, and the setup page's address."""
    code = secrets.token_urlsafe(9)
    with _lock:
        now = time.time()
        _state["codes"] = {c: v for c, v in _state["codes"].items() if v["until"] > now}
        _state["codes"][code] = {"name": _clean_name(name), "until": now + PAIR_MINUTES * 60}
    return code, setup_url(code)


def _use_code(code):
    with _lock:
        entry = _state["codes"].pop(str(code or ""), None)
    if not entry or entry["until"] < time.time():
        return None
    token = secrets.token_urlsafe(32)
    data = devices()
    data[_hash(token)] = {"name": entry["name"], "paired": datetime.date.today().isoformat()}
    _save_devices(data)
    logbook.info("station", "paired a station: %s", entry["name"])
    return token, entry["name"]


def forget(key):
    """Unpair a device (its devices.json key)."""
    data = devices()
    if data.pop(key, None) is None:
        return False
    _save_devices(data)
    return True


def _token(cookie_header):
    """The station token in a Cookie header, or ''."""
    for part in str(cookie_header or "").split(";"):
        k, _, v = part.strip().partition("=")
        if k == COOKIE and v:
            return v
    return ""


def _by_token(token):
    """The paired device with this token (with its key), or None."""
    if not token:
        return None
    key = _hash(token)
    found = devices().get(key)
    return dict(found, key=key) if found else None


def _device(cookie_header):
    """The paired device sending this cookie (with its key), or None."""
    return _by_token(_token(cookie_header))


def _cookie(token):
    # Lax, not Strict: pairing arrives from the http setup page, a different
    # site, and Strict would hide the cookie on the way in. Posts are guarded
    # by the Origin check instead.
    return ("Set-Cookie", f"{COOKIE}={token}; Max-Age={COOKIE_LIFE}; Path=/; Secure; HttpOnly; SameSite=Lax")


# ---------------------------------------------------------------------------
# A turn from a station
# ---------------------------------------------------------------------------
class Turn:
    def __init__(self, room, device=""):
        self.id = secrets.token_urlsafe(8)
        self.room = room
        self.device = device               # whose turn: only that device sees or answers it
        self.state = "hearing"
        self.heard = None
        self.reply = []
        self.clips = []
        self.ask = None
        self.error = ""
        self.typed = False                 # typed in the station's box, not spoken
        self.stopped = False               # the station's Stop button
        self.stopper = None                # the turn's Stop (core/interrupts), once it runs
        self.done_at = 0.0
        self._answer = None
        self._asked = threading.Event()
        self._sentences = []
        self._more = threading.Condition()
        self._closed = False

    # her sentences as they're written, to be spoken on the tablet
    def sentence(self, text):
        text = str(text or "").strip()
        if not text or self.stopped:
            return
        with self._more:
            self.reply.append(text)
            self._sentences.append(text)
            self._more.notify()

    def close(self):
        with self._more:
            self._closed = True
            self._more.notify()

    def stop(self):
        """The station's Stop: she stops writing and talking, and nothing
        not yet turned into speech is spoken."""
        self.stopped = True
        if self.stopper is not None:
            self.stopper.stop(speaking=True, generating=True)
        with self._more:
            self._sentences.clear()
            self._more.notify()

    def speaker(self):
        """Turn each sentence into a WAV for the tablet, in order."""
        from voice import speech

        while True:
            with self._more:
                while not self._sentences and not self._closed:
                    self._more.wait()
                if not self._sentences:
                    break
                text = self._sentences.pop(0)
            try:
                self.state = "speaking"
                samples, rate = speech._synthesize(text)
                self.clips.append(_wav(samples, rate))
            except Exception as e:
                self.error = f"no voice: {e}"
                logbook.warn("station", "speech for a station failed: %s", e)

    # her permission questions, asked on the tablet
    def approver(self, kind, title, lines, warn=False):
        self._answer = None
        self._asked.clear()
        self.ask = {"kind": str(kind), "title": str(title)[:300],
                    "body": "\n".join(str(x) for x in (lines or []))[:4000], "warn": bool(warn)}
        answered = self._asked.wait(ASK_SECONDS)
        self.ask = None
        return bool(answered and self._answer)

    def answer(self, allow):
        self._answer = bool(allow)
        self._asked.set()

    def view(self):
        return {"state": self.state, "heard": self.heard, "reply": " ".join(self.reply),
                "clips": len(self.clips), "ask": self.ask, "error": self.error,
                "typed": self.typed, "stopped": self.stopped}


def _wav(samples, rate):
    import numpy as np

    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2").tobytes()
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(rate))
        w.writeframes(pcm)
    return out.getvalue()


def _model():
    return getattr(sys.modules.get("__main__"), "MODEL", None)


def _respond(turn, text, speaker):
    """Her answer to what was said (or typed) at a station, spoken back there."""
    from core import assistant, interrupts
    import ui

    turn.state = "thinking"
    logbook.info("turn", "station %s%s%s: %s", turn.room, " (typed)" if turn.typed else "",
                 f" ({speaker})" if speaker else "", text[:200])
    who = f"{speaker}, " if speaker else ""
    ui.add_message("user", f"[{who}{turn.room}] {text}")
    # The turn's own Stop, held here so the station's Stop button can reach it
    # (respond() runs as it: interrupts.ensure).
    with interrupts.using(kind="station") as stop:
        turn.stopper = stop
        if turn.stopped:
            stop.stop(speaking=True, generating=True)
        assistant.respond(text, _model(), source="station", speaker=speaker,
                          sink=turn.sentence, approver=turn.approver)


def _run(turn, audio=None, text=None):
    """One station turn: a recording (transcribed, voice checked) or typed text."""
    from core import assistant
    from senses import people
    from voice import speech

    path = None
    voice = threading.Thread(target=turn.speaker, daemon=True, name="station-voice")
    voice.start()
    try:
        if text is not None:
            # Typed on a paired device: no voice to check, so it counts as the
            # owner's, the same as typing at the desk.
            turn.typed = True
            turn.heard = text
            _respond(turn, text, people.decide(None, voice_checked=False, at_desk=False))
            return
        fd, path = tempfile.mkstemp(suffix=".wav", prefix="luna-station-")
        with os.fdopen(fd, "wb") as f:
            f.write(audio)
        heard = {}
        assistant._whose_voice(path, heard)
        if heard.get("enroll"):
            turn.error = "a voice enrolment is running on the PC - read its lines there"
            return
        said = speech.transcribe(path)
        turn.heard = said
        if not said or turn.stopped:
            return
        speaker = people.decide(heard.get("name"), voice_checked=heard.get("score") is not None,
                                at_desk=False)      # another room: the desk camera can't tell
        _respond(turn, said, speaker)
    except Exception as e:
        turn.error = str(e)[:300]
        logbook.exception("station", "station turn failed")
    finally:
        turn.close()
        voice.join(timeout=180)
        turn.state = "done"
        turn.done_at = time.time()
        if path:
            try:
                os.remove(path)
            except OSError:
                pass


def _tidy():
    now = time.time()
    with _lock:
        for k in [k for k, t in _turns.items() if t.done_at and now - t.done_at > TURN_KEEP]:
            del _turns[k]


# ---------------------------------------------------------------------------
# The two servers
# ---------------------------------------------------------------------------
class _Server(ThreadingHTTPServer):
    """Errors (a browser hanging up, plain http on the https port) go to the
    log, never over the terminal."""
    daemon_threads = True

    def handle_error(self, request, client_address):
        logbook.info("station", "connection from %s dropped: %s", client_address[0], sys.exc_info()[1])


class _TLSServer(_Server):
    """HTTPS, with the handshake done in each connection's own thread: done
    on accept, one device that connects and says nothing would stall every
    other one."""

    def __init__(self, address, handler, context):
        self.context = context
        super().__init__(address, handler)

    def finish_request(self, request, client_address):
        request.settimeout(15)
        tls = self.context.wrap_socket(request, server_side=True)
        try:
            super().finish_request(tls, client_address)
        finally:
            try:
                tls.close()
            except OSError:
                pass


def _home_network(address):
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    if getattr(ip, "ipv4_mapped", None):
        ip = ip.ipv4_mapped
    return ip.is_private or ip.is_loopback or ip.is_link_local


class _Base(BaseHTTPRequestHandler):
    server_version = "Luna"
    sys_version = ""
    timeout = 30                   # a connection that goes quiet is dropped

    def log_message(self, *args):
        pass

    def _send(self, code, body, kind="text/html; charset=utf-8", headers=()):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'unsafe-inline'; "
                         "img-src 'self' data:; media-src 'self' blob:; frame-ancestors 'none'")
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj), "application/json")

    def _allowed(self):
        if _home_network(self.client_address[0]):
            return True
        self._send(403, "home network only")
        return False


class _Setup(_Base):
    """Plain HTTP, before the tablet trusts anything: how to, and the
    authority's certificate (public by nature: it proves nothing alone)."""

    def do_GET(self):
        if not self._allowed():
            return
        url = urlsplit(self.path)
        if url.path == "/luna-ca.crt":
            with open(_paths()["ca"], "rb") as f:
                return self._send(200, f.read(), "application/x-x509-ca-cert",
                                  [("Content-Disposition", 'attachment; filename="luna-ca.crt"')])
        if url.path == "/":
            code = (parse_qs(url.query).get("code") or [""])[0]
            return self._send(200, _setup_page(code))
        if url.path.startswith("/sat/") and url.path.endswith(".wav"):
            # an ESPHome satellite fetching her reply (web/satellites.py): plain http, as
            # those devices play from a link; the id is random and lasts minutes
            from web import satellites

            wav = satellites.clip(url.path[5:-4])
            return self._send(200, wav, "audio/wav") if wav else self._send(404, "gone")
        self._send(404, "not found")


class _Station(_Base):
    def _who(self):
        return _device(self.headers.get("Cookie"))

    @staticmethod
    def _turn(tid, device):
        turn = _turns.get(tid)
        return turn if turn and turn.device == device["key"] else None

    def do_GET(self):
        if not self._allowed():
            return
        url = urlsplit(self.path)
        device = self._who()
        if url.path == "/pair":
            got = _use_code((parse_qs(url.query).get("code") or [""])[0])
            if not got:
                if device:
                    # an old pairing link opened again (from history, the QR
                    # scanner) on a device that's already paired: just go in
                    return self._send(303, "", headers=[("Location", "/"), _cookie(_token(self.headers.get("Cookie")))])
                return self._send(403, _message_page(
                    "That pairing code is used up or too old.",
                    "Make a new one on the PC: settings page, Relay stations.", _RESUME))
            token, name = got
            return self._send(303, "", headers=[("Location", "/"), _cookie(token)])
        if url.path == "/":
            if not device:
                return self._send(401, _message_page(
                    "This device isn't paired yet.",
                    "On the PC: settings page, Relay stations, Add a phone or tablet.", _RESUME))
            # renewed on every visit, so a station in use never expires, and the
            # page keeps a copy for a browser that throws cookies away on close
            token = _token(self.headers.get("Cookie"))
            return self._send(200, _station_page(device["name"], token), headers=[_cookie(token)])
        if not device:
            return self._json(401, {"error": "not paired"})
        if url.path.startswith("/turn/"):
            turn = self._turn(url.path[6:], device)
            return self._json(200, turn.view()) if turn else self._json(404, {"error": "no such turn"})
        if url.path.startswith("/clip/"):
            tid, _, n = url.path[6:].partition("/")
            turn = self._turn(tid, device)
            if not turn or not n.isdigit() or int(n) >= len(turn.clips):
                return self._json(404, {"error": "no such clip"})
            return self._send(200, turn.clips[int(n)], "audio/wav")
        self._json(404, {"error": "not found"})

    def do_POST(self):
        if not self._allowed():
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if length < 0 or length > MAX_AUDIO:
            self.close_connection = True
            return self._json(413, {"error": "too long"})
        # read before answering: hanging up on a body still arriving resets
        # the connection, and the device sees an error instead of the reply
        body = self.rfile.read(length)
        # same-origin only: another page on the tablet can't post here
        origin = self.headers.get("Origin")
        if origin and urlsplit(origin).netloc != self.headers.get("Host"):
            return self._json(403, {"error": "wrong origin"})
        url = urlsplit(self.path)
        if url.path == "/resume":
            # the cookie is gone but the page kept the token: if it's still a
            # paired device's, hand the cookie back
            try:
                token = str(json.loads(body or b"{}").get("token") or "")[:200]
            except (ValueError, AttributeError):
                token = ""
            found = _by_token(token)
            if not found:
                return self._json(401, {"error": "not paired"})
            logbook.info("station", "%s came back without its cookie: restored", found["name"])
            return self._send(200, json.dumps({"ok": True}), "application/json", headers=[_cookie(token)])
        device = self._who()
        if not device:
            return self._json(401, {"error": "not paired"})

        if url.path in ("/talk", "/say"):
            if url.path == "/talk":
                if not body.startswith(b"RIFF") or (self.headers.get("Content-Type") or "") != "audio/wav":
                    return self._json(400, {"error": "send a WAV recording"})
                args = (body, None)
            else:
                try:
                    text = str(json.loads(body or b"{}").get("text") or "").strip()
                except (ValueError, AttributeError):
                    text = ""
                if not text:
                    return self._json(400, {"error": "nothing to say"})
                if len(text) > MAX_TYPED:
                    return self._json(413, {"error": f"keep it under {MAX_TYPED} characters"})
                args = (None, text)
            if not getattr(config, "STATION_ENABLED", False):
                return self._json(503, {"error": "relay stations are switched off"})
            _tidy()
            with _lock:
                if any(t.device == device["key"] and not t.done_at for t in _turns.values()):
                    return self._json(409, {"error": "she's still answering the last one"})
                turn = Turn(device["name"], device["key"])
                _turns[turn.id] = turn
            threading.Thread(target=_run, args=(turn,) + args, daemon=True, name="station-turn").start()
            return self._json(200, {"turn": turn.id})
        if url.path.startswith("/stop/"):
            turn = self._turn(url.path[6:], device)
            if not turn:
                return self._json(404, {"error": "no such turn"})
            turn.stop()
            return self._json(200, {"ok": True})
        if url.path.startswith("/answer/"):
            turn = self._turn(url.path[8:], device)
            try:
                allow = bool(json.loads(body or b"{}").get("allow"))
            except (ValueError, AttributeError):
                return self._json(400, {"error": "bad answer"})
            if not turn or not turn.ask:
                return self._json(404, {"error": "nothing asked"})
            turn.answer(allow)
            return self._json(200, {"ok": True})
        self._json(404, {"error": "not found"})


def setup_url(code=""):
    port = int(getattr(config, "STATION_PORT", 8793)) + 1
    return f"http://{_state['ip'] or lan_ip()}:{port}/" + (f"?code={quote(code)}" if code else "")


def station_url(code=""):
    port = int(getattr(config, "STATION_PORT", 8793))
    return f"https://{_state['ip'] or lan_ip()}:{port}/" + (f"pair?code={quote(code)}" if code else "")


def running():
    return bool(_state["servers"])


def start():
    """Start the stations if they're switched on. Returns (ok, message)."""
    if running():
        return True, "already running"
    if not getattr(config, "STATION_ENABLED", False):
        return False, "switched off"
    if not available():
        _state["error"] = "needs the stations extra: python3 installer/install.py --extras stations"
        return False, _state["error"]
    try:
        ip = lan_ip()
        _state["ip"] = ip
        p = certificates(ip)
        port = int(getattr(config, "STATION_PORT", 8793))
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(p["cert"], p["key"])
        secure = _TLSServer(("0.0.0.0", port), _Station, ctx)
        setup = _Server(("0.0.0.0", port + 1), _Setup)
    except Exception as e:
        _state["error"] = f"couldn't start: {e}"
        logbook.warn("station", "%s", _state["error"])
        return False, _state["error"]
    for server, name in ((secure, "station-https"), (setup, "station-setup")):
        threading.Thread(target=server.serve_forever, daemon=True, name=name).start()
    _state["servers"] = [secure, setup]
    _state["error"] = ""
    logbook.info("station", "relay stations on https://%s:%d (setup page on %d)", ip, port, port + 1)
    said = f"listening on {ip}, port {port} (setup page {port + 1})"
    try:
        from web import satellites  # experimental: ESPHome devices listed in config.json

        if satellites.configured():
            ok, sat = satellites.start()
            said += f"; satellites: {sat}"
    except Exception as e:
        logbook.warn("station", "satellites didn't start: %s", e)
    return True, said


def stop():
    try:
        from web import satellites

        satellites.stop()
    except Exception:
        pass
    servers, _state["servers"] = _state["servers"], []
    for server in servers:
        try:
            server.shutdown()
            server.server_close()
        except Exception:
            pass
    return bool(servers)


def panel():
    """What the settings page shows about the stations."""
    port = int(getattr(config, "STATION_PORT", 8793))
    firewall = ""
    if sys.platform.startswith("linux") and os.path.exists("/usr/bin/firewall-cmd"):
        firewall = (f"sudo firewall-cmd --permanent --add-port={port}-{port + 1}/tcp "
                    f"&& sudo firewall-cmd --reload")
    return {"on": bool(getattr(config, "STATION_ENABLED", False)), "running": running(),
            "error": _state["error"], "available": available(), "ip": _state["ip"] or lan_ip(),
            "port": port, "firewall": firewall,
            "devices": [{"key": k, "name": v.get("name", ""), "paired": v.get("paired", "")}
                        for k, v in devices().items()],
            "satellites": _satellites()}


def _satellites():
    """The experimental ESPHome satellites and how they're doing."""
    try:
        from web import satellites

        running = {d["name"]: d for d in satellites.status()}
        return [running.get(str(s.get("name") or s["host"])[:30],
                            {"name": str(s.get("name") or s["host"]), "host": s["host"], "status": "not started"})
                for s in satellites.configured()]
    except Exception:
        return []


def qr_svg(text):
    """The address as a QR code (SVG), or None without the segno package."""
    try:
        import segno
    except ImportError:
        return None
    out = io.BytesIO()
    segno.make(text, error="m").save(out, kind="svg", scale=6, border=2, dark="#120d1c", light="#ffffff",
                                    xmldecl=False, svgns=True)
    return out.getvalue().decode()


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------
_STYLE = """
:root{--bg:#120d1c;--panel:#1a1328;--line:#3a2d55;--text:#ece6f7;--dim:#a49bc0;--accent:#ff87d7;--ok:#7be0a8;--warn:#ffcf6b}
*{box-sizing:border-box}html,body{margin:0;min-height:100%;background:var(--bg);color:var(--text);
font:17px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:560px;margin:0 auto;padding:24px 18px 40px}
h1{font-size:24px;margin:8px 0 4px}h2{font-size:18px;margin:22px 0 6px}
p,li{color:var(--dim)}b{color:var(--text)}a{color:var(--accent)}
.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px 18px;margin:14px 0}
.btn{display:inline-block;background:var(--accent);color:#120d1c;font-weight:700;text-decoration:none;
border:0;border-radius:12px;padding:14px 20px;font-size:17px}
ol{padding-left:22px}code{background:#0e0a16;border:1px solid var(--line);border-radius:6px;padding:1px 6px}
"""


def _esc(text):
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _message_page(title, line, extra=""):
    return (f"<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport "
            f"content='width=device-width,initial-scale=1'><title>Luna</title><style>{_STYLE}</style></head>"
            f"<body><main><h1>{_esc(title)}</h1><p>{_esc(line)}</p>{extra}</main></body></html>")


# On a "not paired" page: if this browser kept a token from an earlier visit
# (the cookie was thrown away when the browser closed), trade it back for the
# cookie and go in. A token that was unpaired on the PC is dropped.
_RESUME = """<p id=resume></p><script>
(async () => {
  let t = null;
  try { t = localStorage.getItem('""" + KEEP_KEY + """'); } catch (e) {}
  if (!t) return;
  document.getElementById('resume').textContent = 'This device was paired before: reconnecting...';
  try {
    const r = await fetch('/resume', {method: 'POST', headers: {'Content-Type': 'application/json'},
                                      body: JSON.stringify({token: t})});
    if (r.ok) { location.replace('/'); return; }
    if (r.status === 401) { try { localStorage.removeItem('""" + KEEP_KEY + """'); } catch (e) {} }
  } catch (e) {}
  document.getElementById('resume').textContent = 'It was unpaired on the PC: pair it again.';
})();
</script>"""


def _setup_page(code):
    nxt = station_url(code) if code else ""
    step2 = (f'<a class=btn href="{_esc(nxt)}">Open Luna</a>' if code else
             "<p>Then scan the pairing QR code from the PC (settings page, Relay stations).</p>")
    return f"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>Set up Luna</title><style>{_STYLE}</style></head>
<body><main>
<h1>Talk to Luna from here</h1>
<p>Two steps, once. After that this device opens straight to her.</p>
<div class=card><h2>1. Trust Luna's certificate</h2>
<p>Phones only allow the microphone on secure pages. Luna made her own certificate on your PC
(its key never leaves it), and this device needs to trust it once. It can only vouch for
addresses on a home network, never for a real website.</p>
<p><a class=btn href="/luna-ca.crt">Download the certificate</a></p>
<p><b>Android:</b> Settings, <b>Security</b> (or Security and privacy), <b>More security settings</b>,
<b>Encryption and credentials</b>, <b>Install a certificate</b>, <b>CA certificate</b>, then
<b>Install anyway</b> and pick <code>luna-ca.crt</code> from Downloads. Use Chrome for Luna.</p>
<p><b>iPhone / iPad:</b> open the download in Safari and tap <b>Allow</b>. Then Settings,
<b>Profile Downloaded</b>, <b>Install</b>. Last: Settings, General, About,
<b>Certificate Trust Settings</b>, switch on <b>Luna</b>.</p>
</div>
<div class=card><h2>2. Pair</h2>{step2}
<p>The code works once, for {PAIR_MINUTES} minutes.</p></div>
</main></body></html>"""


def _station_page(room, token=""):
    keep = json.dumps(token or "").replace("<", "\\u003c")
    return (_PAGE.replace("__STYLE__", _STYLE).replace("__ROOM__", _esc(room))
            .replace("__KEEP__", keep).replace("__KEEP_KEY__", KEEP_KEY))


def _web_page(name):
    """A page's HTML from web/ (kept out of the code so each side reads as what it is)."""
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), name), encoding="utf-8") as f:
        return f.read()


_PAGE = _web_page("station.html")   # the page itself: web/station.html
