"""Relay stations (web/station.py): the certificates, pairing, and a whole turn
from a phone, over real HTTPS on this machine. Her thinking and voice are
faked; the certificates and devices live in a temporary folder.

    python -m unittest discover tests        (from the repo folder)
"""
import io
import json
import os
import shutil
import socket
import ssl
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
import wave
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: E402,F401  (first: no real servers)

import config  # noqa: E402
from web import station  # noqa: E402


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wav(seconds=1.5):
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x10" * int(16000 * seconds))
    return out.getvalue()


@unittest.skipUnless(station.available(), "needs the stations extra (cryptography)")
class Stations(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        port = _free_port()
        while True:                       # port + 1 must be free too
            try:
                with socket.socket() as s:
                    s.bind(("0.0.0.0", port + 1))
                break
            except OSError:
                port = _free_port()
        self.port = port
        self.patches = [mock.patch.object(station, "FOLDER", self.tmp),
                        mock.patch.object(station, "DEVICES_FILE", os.path.join(self.tmp, "devices.json")),
                        mock.patch.object(station, "lan_ip", lambda: "127.0.0.1"),
                        mock.patch.object(config, "STATION_ENABLED", True, create=True),
                        mock.patch.object(config, "STATION_PORT", port, create=True)]
        for p in self.patches:
            p.start()
        station._state.update(servers=[], error="", ip="", codes={})
        ok, said = station.start()
        self.assertTrue(ok, said)
        self.ctx = ssl.create_default_context(cafile=os.path.join(self.tmp, "luna-ca.crt"))
        self.base = f"https://127.0.0.1:{port}"

    def tearDown(self):
        station.stop()
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _open(self, path, data=None, cookie=None, kind=None, method=None):
        req = urllib.request.Request(self.base + path, data=data, method=method)
        if cookie:
            req.add_header("Cookie", cookie)
        if kind:
            req.add_header("Content-Type", kind)

        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **k):
                return None

        opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=self.ctx), NoRedirect)
        try:
            r = opener.open(req, timeout=10)
            return r.status, r.headers, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()

    def _pair(self, name="kitchen"):
        code, url = station.new_pairing(name)
        self.assertIn(f"?code={code}", url)
        status, headers, _ = self._open(f"/pair?code={code}")
        self.assertEqual(status, 303)
        cookie = headers["Set-Cookie"].split(";")[0]
        self.assertIn("HttpOnly", headers["Set-Cookie"])
        return code, cookie

    def test_certificate_is_trusted_by_its_authority(self):
        # the verifying context above would have refused the handshake otherwise
        status, _h, body = self._open("/")
        self.assertEqual(status, 401)
        self.assertIn(b"isn't paired", body)

    def test_setup_page_and_authority_download(self):
        plain = urllib.request.build_opener()          # (urlopen itself is blocked offline)
        r = plain.open(f"http://127.0.0.1:{self.port + 1}/?code=abc", timeout=10)
        page = r.read().decode()
        self.assertIn("Download the certificate", page)
        self.assertIn(f"https://127.0.0.1:{self.port}/pair?code=abc", page)
        r = plain.open(f"http://127.0.0.1:{self.port + 1}/luna-ca.crt", timeout=10)
        self.assertIn(b"BEGIN CERTIFICATE", r.read())

    def test_pairing_is_single_use(self):
        code, cookie = self._pair()
        status, _h, page = self._open("/", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertIn(b"kitchen", page)
        self.assertEqual(self._open(f"/pair?code={code}")[0], 403)          # used up
        self.assertEqual(self._open("/pair?code=guess")[0], 403)
        self.assertEqual(self._open("/", cookie="luna_station=nope")[0], 401)
        devices = station.devices()
        self.assertEqual([d["name"] for d in devices.values()], ["kitchen"])
        self.assertNotIn(cookie.split("=", 1)[1], json.dumps(devices))     # stored hashed

    def test_a_paired_device_stays_paired(self):
        code, cookie = self._pair()
        token = cookie.split("=", 1)[1]
        status, headers, page = self._open("/", cookie=cookie)
        self.assertIn(f"Max-Age={station.COOKIE_LIFE}", headers["Set-Cookie"])     # renewed each visit
        self.assertIn(token.encode(), page)                                       # the page keeps a copy
        # the old pairing link again, on the paired device: straight in
        status, headers, _ = self._open(f"/pair?code={code}", cookie=cookie)
        self.assertEqual((status, headers["Location"]), (303, "/"))

    def test_a_lost_cookie_comes_back_from_the_page(self):
        _code, cookie = self._pair()
        token = cookie.split("=", 1)[1]
        status, _h, page = self._open("/")                                         # cookie gone
        self.assertEqual(status, 401)
        self.assertIn(b"/resume", page)
        status, headers, _ = self._open("/resume", data=json.dumps({"token": token}).encode(),
                                        kind="application/json")
        self.assertEqual(status, 200)
        self.assertIn(token, headers["Set-Cookie"])
        self.assertEqual(self._open("/resume", data=b'{"token": "guess"}', kind="application/json")[0], 401)
        key = next(iter(station.devices()))
        station.forget(key)                                                        # unpaired on the PC
        self.assertEqual(self._open("/resume", data=json.dumps({"token": token}).encode(),
                                    kind="application/json")[0], 401)

    def test_resume_checks_the_origin(self):
        _code, cookie = self._pair()
        req = urllib.request.Request(self.base + "/resume", data=json.dumps({"token": cookie.split("=", 1)[1]}).encode())
        req.add_header("Origin", "https://evil.example")
        opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=self.ctx))
        with self.assertRaises(urllib.error.HTTPError) as e:
            opener.open(req, timeout=10)
        self.assertEqual(e.exception.code, 403)

    def test_old_code_refused(self):
        code, _url = station.new_pairing("hall")
        station._state["codes"][code]["until"] = time.time() - 1
        self.assertEqual(self._open(f"/pair?code={code}")[0], 403)

    def test_a_whole_turn(self):
        _code, cookie = self._pair()
        import numpy as np

        def respond(text, model, source, speaker, sink, approver, recording=None, attachment=None):
            self.assertEqual((text, source), ("what's the weather", "station"))
            sink("It's sunny.")
            self.assertTrue(approver("write", "write notes.txt", ["hello"], False))
            sink("Want a jacket anyway?")

        with mock.patch("voice.speech.transcribe", return_value="what's the weather"), \
             mock.patch("voice.speech._synthesize", return_value=(np.zeros(2400, dtype=np.float32), 24000)), \
             mock.patch("core.assistant._whose_voice", lambda path, heard: None), \
             mock.patch("core.assistant.respond", respond), mock.patch("ui.add_message"):
            req = self._open("/talk", data=_wav(), cookie=cookie, kind="audio/wav")
            self.assertEqual(req[0], 200)
            turn = json.loads(req[2])["turn"]
            for _ in range(100):
                view = json.loads(self._open(f"/turn/{turn}", cookie=cookie)[2])
                if view["ask"]:
                    self.assertEqual(view["ask"]["title"], "write notes.txt")
                    self.assertEqual(self._open(f"/answer/{turn}", data=b'{"allow": true}', cookie=cookie,
                                                kind="application/json")[0], 200)
                if view["state"] == "done":
                    break
                time.sleep(0.05)
            self.assertEqual(view["heard"], "what's the weather")
            self.assertEqual(view["reply"], "It's sunny. Want a jacket anyway?")
            self.assertEqual(view["clips"], 2)
            status, headers, clip = self._open(f"/turn/{turn}".replace("turn", "clip") + "/1", cookie=cookie)
            self.assertEqual(status, 200)
            self.assertTrue(clip.startswith(b"RIFF"))

    def test_talk_checks(self):
        _code, cookie = self._pair()
        self.assertEqual(self._open("/talk", data=_wav(), kind="audio/wav")[0], 401)            # not paired
        self.assertEqual(self._open("/talk", data=b"not a wav", cookie=cookie, kind="audio/wav")[0], 400)
        req = urllib.request.Request(self.base + "/talk", data=_wav(), method="POST")
        req.add_header("Cookie", cookie)
        req.add_header("Content-Type", "audio/wav")
        req.add_header("Origin", "https://evil.example")
        try:
            urllib.request.build_opener(urllib.request.HTTPSHandler(context=self.ctx)).open(req, timeout=10)
            self.fail("another origin got in")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 403)

    def test_a_silent_connection_doesnt_stall_the_rest(self):
        idle = socket.create_connection(("127.0.0.1", self.port))      # connects, never says hello
        try:
            started = time.time()
            self.assertEqual(self._open("/")[0], 401)
            self.assertLess(time.time() - started, 5)
        finally:
            idle.close()

    def test_turns_belong_to_their_device(self):
        _c, kitchen = self._pair("kitchen")
        _c, hall = self._pair("hall")
        release = __import__("threading").Event()

        def respond(text, model, source, speaker, sink, approver, recording=None, attachment=None):
            release.wait(5)

        with mock.patch("voice.speech.transcribe", return_value="hi"), \
             mock.patch("core.assistant._whose_voice", lambda path, heard: None), \
             mock.patch("core.assistant.respond", respond), mock.patch("ui.add_message"):
            turn = json.loads(self._open("/talk", data=_wav(), cookie=kitchen, kind="audio/wav")[2])["turn"]
            self.assertEqual(self._open(f"/turn/{turn}", cookie=hall)[0], 404)          # not the hall's
            self.assertEqual(self._open(f"/turn/{turn}", cookie=kitchen)[0], 200)
            self.assertEqual(self._open("/talk", data=_wav(), cookie=kitchen, kind="audio/wav")[0], 409)
            release.set()

    def _wait_done(self, turn, cookie):
        for _ in range(100):
            view = json.loads(self._open(f"/turn/{turn}", cookie=cookie)[2])
            if view["state"] == "done":
                return view
            time.sleep(0.05)
        self.fail("the turn never finished")

    def test_a_typed_turn(self):
        _code, cookie = self._pair()
        import numpy as np

        seen = {}

        def respond(text, model, source, speaker, sink, approver, recording=None, attachment=None):
            seen.update(text=text, source=source, speaker=speaker)
            sink("Sunny all day.")

        with mock.patch("voice.speech.transcribe", side_effect=AssertionError("nothing to transcribe")), \
             mock.patch("voice.speech._synthesize", return_value=(np.zeros(2400, dtype=np.float32), 24000)), \
             mock.patch("core.assistant.respond", respond), mock.patch("ui.add_message"):
            r = self._open("/say", data=json.dumps({"text": " what's the weather? "}).encode(),
                           cookie=cookie, kind="application/json")
            self.assertEqual(r[0], 200)
            view = self._wait_done(json.loads(r[2])["turn"], cookie)
        self.assertEqual(seen, {"text": "what's the weather?", "source": "station", "speaker": None})
        self.assertEqual((view["heard"], view["typed"], view["reply"], view["clips"]),
                         ("what's the weather?", True, "Sunny all day.", 1))

    def _form(self, text, name, kind, data):
        from urllib3 import encode_multipart_formdata
        fields = [("text", text)] + ([("file", (name, data, kind))] if data is not None else [])
        return encode_multipart_formdata(fields)

    def test_a_picture_with_the_words(self):
        _code, cookie = self._pair()
        import io
        import numpy as np
        from PIL import Image

        im = Image.new("RGB", (2400, 1200), (40, 90, 200))
        exif = Image.Exif()
        exif[0x010F] = "PhoneCam"
        raw = io.BytesIO()
        im.save(raw, "JPEG", exif=exif)
        seen = {}

        def respond(text, model, source, speaker, sink, approver, recording=None, attachment=None):
            seen.update(text=text, attachment=attachment)
            sink("A blue rectangle.")

        body, kind = self._form("what's this?", "IMG_1.jpg", "image/jpeg", raw.getvalue())
        with mock.patch("core.attachments.sees_images", return_value=True), \
             mock.patch("voice.speech._synthesize", return_value=(np.zeros(2400, dtype=np.float32), 24000)), \
             mock.patch("core.assistant.respond", respond), mock.patch("ui.add_message"):
            r = self._open("/say", data=body, cookie=cookie, kind=kind)
            self.assertEqual(r[0], 200, r[2])
            view = self._wait_done(json.loads(r[2])["turn"], cookie)
        att = seen["attachment"]
        self.assertEqual((seen["text"], att.kind, att.name, view["reply"]), ("what's this?", "image", "IMG_1.jpg", "A blue rectangle."))
        import base64
        sent = Image.open(io.BytesIO(base64.b64decode(att.data_url.split(",", 1)[1])))
        self.assertLessEqual(max(sent.size), 1568)
        self.assertEqual(dict(sent.getexif()), {})                                   # the phone's EXIF is gone

    def test_attachment_checks(self):
        _code, cookie = self._pair()
        def send(*a):
            body, kind = self._form(*a)
            return self._open("/say", data=body, cookie=cookie, kind=kind)
        with mock.patch("core.attachments.sees_images", return_value=False):
            status, _, body = send("look", "a.jpg", "image/jpeg", b"\xff\xd8\xff" + b"0" * 100)
        self.assertEqual((status, json.loads(body)["code"]), (422, "no_vision"))
        status, _, body = send("run this", "a.exe", "application/octet-stream", b"MZ\x00\x00")
        self.assertEqual((status, json.loads(body)["code"]), (415, "unsupported"))
        from urllib3 import encode_multipart_formdata
        two, kind = encode_multipart_formdata([("text", "hi"), ("file", ("a.txt", b"a", "text/plain")),
                                               ("file", ("b.txt", b"b", "text/plain"))])
        status, _, body = self._open("/say", data=two, cookie=cookie, kind=kind)
        self.assertEqual((status, json.loads(body)["code"]), (413, "too_many"))
        status, _, body = self._open("/say", data=b"--nope", cookie=cookie, kind="multipart/form-data; boundary=x")
        self.assertEqual(status, 400)
        from web import station as st
        text, files = st._form(*reversed(encode_multipart_formdata(
            [("text", "hi"), ("file", ("", b"", "application/octet-stream"))])))   # a browser form, nothing picked
        self.assertEqual((text, files), ("hi", []))

    def test_info(self):
        _code, cookie = self._pair()
        self.assertEqual(self._open("/info")[0], 401)
        with mock.patch("core.attachments.sees_images", return_value=None):
            status, _, body = self._open("/info", cookie=cookie)
        info = json.loads(body)
        self.assertEqual((status, info["api"], info["attachments"]["max_files"]), (200, 2, 1))
        self.assertIn("attachments", info["features"])
        self.assertIn("image/jpeg", info["attachments"]["images"]["types"])

    def test_typed_checks(self):
        _code, cookie = self._pair()
        say = lambda body, c=cookie: self._open("/say", data=body, cookie=c, kind="application/json")[0]
        self.assertEqual(say(b'{"text": "hi"}', None), 401)                       # not paired
        self.assertEqual(say(b'{"text": "   "}'), 400)                            # nothing to say
        self.assertEqual(say(b'not json'), 400)
        self.assertEqual(say(json.dumps({"text": "x" * (station.MAX_TYPED + 1)}).encode()), 413)

    def test_stop(self):
        _code, cookie = self._pair()
        import numpy as np
        import threading
        from core import interrupts

        stopped = threading.Event()

        def respond(text, model, source, speaker, sink, approver, recording=None, attachment=None):
            stop = interrupts.current()        # the station turn's own Stop
            sink("First.")
            for _ in range(200):               # "generating" until told to stop
                if stop.generating.is_set():
                    stopped.set()
                    break
                time.sleep(0.02)
            sink("Never spoken.")

        with mock.patch("voice.speech._synthesize", return_value=(np.zeros(2400, dtype=np.float32), 24000)), \
             mock.patch("core.assistant.respond", respond), mock.patch("ui.add_message"):
            turn = json.loads(self._open("/say", data=b'{"text": "tell me a long story"}',
                                         cookie=cookie, kind="application/json")[2])["turn"]
            time.sleep(0.2)
            _c, other = self._pair("hall")
            self.assertEqual(self._open(f"/stop/{turn}", data=b"", cookie=other)[0], 404)   # not the hall's
            self.assertEqual(self._open(f"/stop/{turn}", data=b"", cookie=cookie)[0], 200)
            view = self._wait_done(turn, cookie)
        self.assertTrue(stopped.is_set())
        self.assertTrue(view["stopped"])
        self.assertEqual(view["reply"], "First.")

    def test_her_portrait_for_paired_devices_only(self):
        self.assertEqual(self._open("/portrait/")[0], 401)
        self.assertEqual(self._open("/portrait/config.json")[0], 401)
        _code, cookie = self._pair()
        status, headers, page = self._open("/portrait/", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertIn(b"boot.js", page)
        self.assertIn("'wasm-unsafe-eval'", headers["Content-Security-Policy"])
        status, _h, body = self._open("/portrait/config.json", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertIsInstance(json.loads(body), dict)
        self.assertEqual(self._open("/portrait/../config/server.py", cookie=cookie)[0], 404)
        self.assertEqual(self._open("/portrait", cookie=cookie)[1]["Location"], "/portrait/")
        # read-only: no pose studio saves; taps and clothes reports are dropped quietly
        self.assertEqual(self._open("/portrait/gestures/save", b"{}", cookie, "application/json")[0], 404)
        with mock.patch("life.touches.note") as note, mock.patch("life.clothes.note") as worn:
            self.assertEqual(self._open("/portrait/touch", b'{"zone": "head"}', cookie, "application/json")[0], 204)
            self.assertEqual(self._open("/portrait/outfit", b'{"wearing": "none"}', cookie, "application/json")[0], 204)
        note.assert_not_called()
        worn.assert_not_called()
        # a tablet never casts to the PC's hologram fan
        with mock.patch.object(config, "PORTRAIT_FAN_CAST", True, create=True):
            body = self._open("/portrait/config.json", cookie=cookie)[2]
        self.assertFalse(json.loads(body)["fan"]["cast"])

    def test_portrait_stream_leaves_out_your_words_and_her_thinking(self):
        import http.client

        from web import livefeed

        snap = mock.patch.dict(livefeed._snapshot, clear=True)
        snap.start()
        self.addCleanup(snap.stop)
        _code, cookie = self._pair()
        c = http.client.HTTPSConnection("127.0.0.1", self.port, context=self.ctx, timeout=10)
        c.request("GET", "/portrait/events", headers={"Cookie": cookie})
        r = c.getresponse()
        self.assertEqual(r.status, 200)
        deadline = time.time() + 5
        while not livefeed._filtered and time.time() < deadline:
            time.sleep(0.05)
        livefeed.emit("turn", text="my secret", source="voice", guest=False)
        livefeed.emit("tok", p="t", s="thinking hard", c=None)
        livefeed.emit("tok", p="a", s="<think>inline thoughts</think>", c=None)
        livefeed.emit("tok", p="a", s="*hugs*", c=None)
        livefeed.emit("context", used=100)
        livefeed.emit("mood", warmth=0.5, energy=0.1)
        got = []
        while time.time() < deadline:
            line = r.fp.readline().decode()
            if line.startswith("data: "):
                got.append(json.loads(line[6:]))
                if got[-1]["t"] == "mood" and any(e["t"] == "tok" for e in got):
                    break
        r.close()           # the app leaving her portrait
        c.close()
        text = json.dumps(got)
        self.assertNotIn("my secret", text)
        self.assertNotIn("thinking hard", text)
        self.assertNotIn("inline thoughts", text)
        self.assertIn("*hugs*", text)
        self.assertNotIn('"context"', text)
        self.assertIn({"t": "turn", "source": "voice", "guest": False},
                      [{k: e.get(k) for k in ("t", "source", "guest")} for e in got if e["t"] == "turn"])
        deadline = time.time() + 5             # noticed within a second or so
        while livefeed._filtered and time.time() < deadline:
            time.sleep(0.2)
        self.assertFalse(livefeed._filtered)

    def test_playing_a_clip_moves_her_mouth(self):
        _code, cookie = self._pair()
        turn = station.Turn("kitchen", next(iter(station.devices())))
        turn.clips.append(_wav(0.5))
        station._turns[turn.id] = turn
        with mock.patch("web.livefeed.watching", return_value=False), mock.patch("voice.tts._lip_sync") as lips:
            self.assertEqual(self._open(f"/playing/{turn.id}/0", b"", cookie)[0], 200)
            time.sleep(0.3)
        lips.assert_not_called()           # nobody watching: the clip isn't even decoded
        with mock.patch("web.livefeed.watching", return_value=True), mock.patch("voice.tts._lip_sync") as lips:
            status, _h, _b = self._open(f"/playing/{turn.id}/0", b"", cookie)
            self.assertEqual(status, 200)
            deadline = time.time() + 5
            while not lips.called and time.time() < deadline:
                time.sleep(0.05)
        self.assertTrue(lips.called)
        samples, rate = lips.call_args[0]
        self.assertEqual(rate, 16000)
        self.assertEqual(len(samples), 8000)
        self.assertEqual(self._open(f"/playing/{turn.id}/5", b"", cookie)[0], 404)

    def test_unpair(self):
        _code, cookie = self._pair()
        key = next(iter(station.devices()))
        self.assertTrue(station.forget(key))
        self.assertEqual(self._open("/", cookie=cookie)[0], 401)

    def test_authority_only_vouches_for_home_addresses(self):
        from cryptography import x509

        with open(os.path.join(self.tmp, "luna-ca.crt"), "rb") as f:
            ca = x509.load_pem_x509_certificate(f.read())
        limits = ca.extensions.get_extension_for_class(x509.NameConstraints)
        self.assertTrue(limits.critical)
        self.assertIn(x509.DNSName("local"), limits.value.permitted_subtrees)

    def test_panel_and_qr(self):
        panel = station.panel()
        self.assertTrue(panel["running"])
        self.assertEqual(panel["port"], self.port)
        self.assertIn("<svg", station.qr_svg("http://example/") or "<svg")
        svg = station.qr_svg("http://example/")
        if svg:                    # scales to its box, never cropped by it
            self.assertIn("viewBox", svg)
            self.assertNotIn('width="', svg.split(">", 1)[0])


class SpokenWithoutEmoji(unittest.TestCase):
    """The station's voice skips emoji and markdown, as the desk does; the reply shown keeps them."""

    def test_voice_loses_the_emoji_the_text_keeps_them(self):
        import numpy as np

        turn = station.Turn(room=None)
        turn.sentence("Mrrp~ hi there 💕✨")
        turn.sentence("🐾 🌸")                       # nothing left to say: no clip
        turn.sentence("*tilts head* ok")
        turn.close()
        with mock.patch("voice.speech._synthesize",
                        return_value=(np.zeros(240, dtype=np.float32), 24000)) as synth:
            turn.speaker()
        self.assertEqual([c.args[0] for c in synth.call_args_list], ["Mrrp hi there", "tilts head ok"])
        self.assertEqual(len(turn.clips), 2)
        self.assertEqual(turn.view()["reply"], "Mrrp~ hi there 💕✨ 🐾 🌸 *tilts head* ok")


class HomeNetworkOnly(unittest.TestCase):
    def test_addresses(self):
        for ip in ("192.168.0.20", "10.1.2.3", "172.16.5.4", "127.0.0.1", "fe80::1", "::ffff:192.168.1.2"):
            self.assertTrue(station._home_network(ip), ip)
        for ip in ("8.8.8.8", "2606:4700::1111", "nonsense"):
            self.assertFalse(station._home_network(ip), ip)


if __name__ == "__main__":
    unittest.main()
