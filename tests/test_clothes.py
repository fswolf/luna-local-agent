"""Her clothes on a human model: the page's report (life/clothes.py and
POST /portrait/outfit), her situation line, /outfit, and the plain-words
parser (portrait/viewer/clothes_talk.js, run through node when it's there)."""
import http.client
import json
import os
import shutil
import subprocess
import sys
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tests.offline  # noqa: F401,E402

from life import clothes  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def reset():
    clothes._state.update(wearing="", off=[], pieces=[], at=0.0)


class Report(unittest.TestCase):
    def setUp(self):
        reset()
        self.open = mock.patch("web.livefeed.watching", return_value=True)
        self.open.start()

    def tearDown(self):
        self.open.stop()

    def test_dressed_and_no_pieces_say_nothing(self):
        for wearing in ("dressed", "none"):
            self.assertTrue(clothes.note(wearing))
            self.assertEqual(clothes.describe(), "")
        reset()
        self.assertEqual(clothes.describe(), "")              # nothing reported yet

    def test_underwear_and_partly(self):
        clothes.note("underwear", ["top", "tie", "bottoms"])
        self.assertIn("underwear", clothes.describe())
        clothes.note("partly", ["top", "tie"])
        self.assertEqual(clothes.describe(), "Wearing: your clothes, without your top and tie")

    def test_junk_refused(self):
        self.assertFalse(clothes.note("naked"))
        self.assertTrue(clothes.note("partly", ["top", "<script>", "x" * 40, "tie"]))
        self.assertEqual(clothes.current()["off"], ["top", "tie"])

    def test_closed_portrait_is_stale(self):
        clothes.note("underwear", ["top"])
        with mock.patch("web.livefeed.watching", return_value=False):
            self.assertEqual(clothes.describe(), "")

    def test_situation_line(self):
        from mind import situation

        clothes.note("partly", ["top"])
        self.assertIn("without your top", situation._clothes())


class Command(unittest.TestCase):
    def test_outfit_sends_to_the_portrait(self):
        from commands import portrait

        with mock.patch("web.livefeed.emit") as emit, mock.patch("ui.add_message"):
            self.assertTrue(portrait.handle("/outfit underwear"))
            emit.assert_called_with("outfit", wear="underwear")
            self.assertTrue(portrait.handle("/outfit off top"))
            emit.assert_called_with("outfit", off=["top"])
            emit.reset_mock()
            self.assertTrue(portrait.handle("/outfit sideways"))
            emit.assert_not_called()


class Endpoint(unittest.TestCase):
    def setUp(self):
        from web import livefeed

        reset()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), livefeed._Handler)
        self.port = self.server.server_address[1]
        self.patch = mock.patch.object(livefeed, "port", return_value=self.port)
        self.patch.start()
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.patch.stop()

    def post(self, body, kind="application/json", origin=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {"Content-Type": kind, "Host": f"127.0.0.1:{self.port}"}
        if origin:
            headers["Origin"] = origin
        c.request("POST", "/portrait/outfit", body=body, headers=headers)
        status = c.getresponse().status
        c.close()
        return status

    def test_only_json_from_her_own_page(self):
        self.assertEqual(self.post(json.dumps({"wearing": "partly", "off": ["top"]})), 204)
        self.assertEqual(clothes.current()["off"], ["top"])
        self.assertEqual(self.post(json.dumps({"wearing": "partly", "off": ["top"], "pieces": ["top", "tie"]})), 204)
        self.assertEqual(clothes.current()["pieces"], ["top", "tie"])
        self.assertEqual(self.post("wearing=underwear", kind="application/x-www-form-urlencoded"), 400)
        self.assertEqual(self.post(json.dumps({"wearing": "underwear"}), origin="http://evil.example"), 403)
        self.assertEqual(clothes.current()["wearing"], "partly")


class Tags(unittest.TestCase):
    """Structured choices: [top_off], [undress], [dress], tied to portrait.gestures."""

    def setUp(self):
        reset()
        from life import gestures

        gestures.new_turn()
        self.patches = [mock.patch("web.livefeed.watching", return_value=True),
                        mock.patch("mind.mood.tame", return_value=False),
                        mock.patch.object(gestures, "_three_d", return_value=True),
                        mock.patch.object(gestures, "offered", return_value=["wave", "hug"]),
                        mock.patch.object(gestures, "clips", return_value=[])]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def setting(self, gestures="keywords", clothes_mode="gestures"):
        return mock.patch.multiple("config", PORTRAIT_GESTURES=gestures, PORTRAIT_CLOTHES=clothes_mode, create=True)

    def test_mode_follows_gestures(self):
        for g, want in (("tags", "tags"), ("meaning", "keywords"), ("keywords", "keywords"), ("off", "off")):
            with self.setting(g):
                self.assertEqual(clothes.mode(), want, g)
        with self.setting("tags", "keywords"):
            self.assertEqual(clothes.mode(), "keywords")
        with self.setting("off", "tags"):
            self.assertEqual(clothes.mode(), "tags")

    def test_offered_fits_what_she_has_on(self):
        clothes.note("dressed", [], ["top", "tie", "bottoms"])
        with self.setting("tags"):
            self.assertEqual(clothes.offered(), ["undress", "top_off", "tie_off", "bottoms_off"])
            self.assertEqual(clothes.offered(private=False), [])       # stream chat, a guest
            clothes.note("partly", ["top"], ["top", "tie", "bottoms"])
            self.assertEqual(clothes.offered(), ["dress", "undress", "tie_off", "bottoms_off"])
            clothes.note("underwear", ["top", "tie", "bottoms"], ["top", "tie", "bottoms"])
            self.assertEqual(clothes.offered(), ["dress", "top_on", "tie_on", "bottoms_on"])
            with mock.patch("mind.mood.tame", return_value=True):
                self.assertEqual(clothes.offered(), ["dress", "top_on", "tie_on", "bottoms_on"])
        with self.setting("keywords"):
            self.assertEqual(clothes.offered(), [])
        clothes.note("none")
        with self.setting("tags"):
            self.assertEqual(clothes.offered(), [])                    # the robot

    def test_one_prompt_line(self):
        from life import gestures

        clothes.note("dressed", [], ["top", "tie"])
        with self.setting("tags"):
            line = gestures.prompt_line()
            self.assertIn("[wave] [hug] [undress] [top_off] [tie_off]", line)
            self.assertEqual(line.count("\n"), 1)
        with self.setting("keywords", "tags"):
            self.assertIn("[undress]", gestures.prompt_line())
            self.assertNotIn("[wave]", gestures.prompt_line())
        with self.setting("keywords"):
            self.assertEqual(gestures.prompt_line(), "")

    def test_tag_goes_to_the_page_and_is_cut(self):
        from life import gestures

        clothes.note("dressed", [], ["top", "tie"])
        with self.setting("tags"), mock.patch("web.livefeed.emit") as emit:
            gestures.from_tags("Fine, fine. [top_off] Happy now? [wave]")
            emit.assert_any_call("outfit", src="tag", off=["top"])
            emit.assert_any_call("gesture", name="wave", src="tag")
            emit.reset_mock()
            gestures.from_tags("Fine, fine. [top_off] Happy now? [wave] [dress]")   # streamed again: once each
            emit.assert_called_once_with("outfit", src="tag", wear="dressed")
            self.assertEqual(gestures.strip("Okay [undress] there."), "Okay there.")
            self.assertEqual(gestures.strip("Okay [tie_o"), "Okay ")
        gestures.new_turn()
        with self.setting("off", "off"), mock.patch("web.livefeed.emit") as emit:
            gestures.from_tags("[top_off]")
            emit.assert_not_called()


class UndressGestures(unittest.TestCase):
    """Gestures that take a piece off at a moment (tie_off, top_off, bottoms_off)."""

    def test_studio_saves_clothes_checked(self):
        from web import livefeed

        k = [[0, {"rightHand": [0, 0, 0]}]]
        _n, text = livefeed.gesture_file({"name": "s", "keys": k, "clothes": [
            {"at": 1.5, "off": ["top", "<b>"]}, {"at": 2, "on": ["tie"]}, {"at": 3, "off": []}, "junk"]})
        self.assertIn('clothes: [{"at": 1.5, "off": ["top"]}, {"at": 2.0, "on": ["tie"]}]', text.replace("2,", "2.0,"))

    def test_built_ins_take_off_what_they_say(self):
        from life import gestures

        found = gestures.builtin()
        for name, piece in (("tie_off", "tie"), ("top_off", "top"), ("bottoms_off", "bottoms")):
            self.assertIn(name, found)
            self.assertFalse(found[name]["about"], name)          # never offered as a move of its own
            with open(os.path.join(HERE, "portrait", "gestures", name + ".js"), encoding="utf-8") as f:
                # hand-written (off: ['top']) or saved by the studio ("off": ["top"])
                # (the studio saves one entry per piece: {"at": 2.05, "off": ["top"]}, ...)
                self.assertRegex(f.read(), r"clothes: \[.*\"?off\"?: ?\[[^\]]*['\"]%s['\"]" % piece)


@unittest.skipUnless(shutil.which("node"), "node isn't installed")
class FaceChannels(unittest.TestCase):
    """A face track that starts later than 0 (blush from 2.4 s, in the undress
    gestures) gave NaN before its first point, and the face mesh vanished."""

    def test_no_nan_before_the_first_point(self):
        with open(os.path.join(HERE, "portrait", "viewer", "gestures.js"), encoding="utf-8") as f:
            src = f.read()
        ease = src[src.index("const ease ="):].split("\n", 1)[0]
        fn = src[src.index("export function sampleScalar"):]
        fn = fn[:fn.index("\n}\n") + 3].replace("export ", "")
        script = ease + "\n" + fn + """
const tr = [[2.4, 0], [3.0, 0.5], [4.4, 0.4]];
console.log(JSON.stringify([0, 1, 2.4, 2.7, 3.0, 9].map(t => sampleScalar(tr, t))));"""
        out = json.loads(subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True, timeout=30).stdout)
        self.assertEqual(out[:3], [0, 0, 0])
        self.assertTrue(0 < out[3] < 0.5)
        self.assertEqual(out[4:], [0.5, 0.4])


CASES_YOU = {
    "take off your top": {"off": ["top"]},
    "take your shirt off": {"off": ["top"]},
    "lose the tie": {"off": ["tie"]},
    "strip": {"wear": "underwear"},
    "get dressed": {"wear": "dressed"},
    "put your shirt back on": {"on": ["top"]},
    "don't take your top off": None,
    "I took my shirt off at the beach": None,
    "turn off the lights": None,
    "take off your shoes and socks": {"off": ["shoes", "socks"]},
    "put some clothes on": {"wear": "dressed"},
    "the comic strip": None,
    "strip for me": {"wear": "underwear"},
}
CASES_HER = {
    "slips her top off": {"off": ["top"]},
    "takes off her tie": {"off": ["tie"]},
    "pulls her shirt back on": {"on": ["top"]},
    "strips down to her underwear": {"wear": "underwear"},
    "starts to take off her top": None,
    "tugs her skirt down": None,
    "takes off her glasses": None,
    "kicks off her shoes": {"off": ["shoes"]},
    "slips out of her skirt": {"off": ["bottoms"]},
    "pulls her top over her head": {"off": ["top"]},
}


@unittest.skipUnless(shutil.which("node"), "node isn't installed")
class Words(unittest.TestCase):
    def run_js(self, fn, cases):
        path = os.path.join(HERE, "portrait", "viewer", "clothes_talk.js")
        script = (f"import(process.argv[1]).then(m => {{ const out = {{}}; "
                  f"for (const c of JSON.parse(process.argv[2])) out[c] = m.{fn}(c); console.log(JSON.stringify(out)); }});")
        return json.loads(subprocess.run(["node", "-e", script, "file://" + path, json.dumps(list(cases))],
                                         capture_output=True, text=True, check=True, timeout=30).stdout)

    def test_you(self):
        got = self.run_js("clothesAsked", CASES_YOU)
        for text, want in CASES_YOU.items():
            self.assertEqual(got[text], want, text)

    def test_her(self):
        got = self.run_js("clothesActed", CASES_HER)
        for text, want in CASES_HER.items():
            self.assertEqual(got[text], want, text)


if __name__ == "__main__":
    unittest.main()
