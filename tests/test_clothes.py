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

    def test_tags_in_her_underwear(self):
        clothes.note("underwear", ["top", "bottoms"], ["top", "bottoms", "bra", "panties"])
        with mock.patch.object(clothes, "mode", return_value="tags"), mock.patch("mind.mood.tame", return_value=[]), \
             mock.patch.object(clothes, "TAGS_OFFERED", 10), mock.patch.object(clothes, "_in_the_mood", return_value=True):
            got = clothes.offered()
        self.assertIn("dress", got)
        self.assertIn("bra_off", got)
        self.assertIn("panties_off", got)
        self.assertNotIn("undress", got)
        self.assertIn("top_on", got)

    def test_taking_off_only_offered_in_the_mood(self):
        clothes.note("partly", ["top"], ["top", "tie", "bottoms"])
        tags = (mock.patch.object(clothes, "mode", return_value="tags"), mock.patch("mind.mood.tame", return_value=[]),
                mock.patch.object(clothes, "TAGS_OFFERED", 10))
        for p in tags:
            p.start()
        try:
            for band, keen in (("neutral", False), ("warm", False), ("loving", False), ("lewd", True)):
                with mock.patch("life.gestures._band", return_value=(band, "")):
                    got = clothes.offered()
                self.assertIn("dress", got)                    # putting things on is always there
                self.assertIn("top_on", got)
                self.assertEqual("undress" in got, keen, band)
                self.assertEqual("tie_off" in got, keen, band)
            with mock.patch("life.gestures._band", side_effect=RuntimeError):
                self.assertNotIn("undress", clothes.offered())
            with mock.patch("life.gestures._band", return_value=("neutral", "")), \
                 mock.patch("config.MOOD_ENABLED", False):
                self.assertIn("undress", clothes.offered())   # mood off: nothing to go by, offered
        finally:
            for p in tags:
                p.stop()

    def test_bare(self):
        clothes.note("bare", ["top", "tie", "bra", "panties"], ["top", "tie", "bra", "panties"])
        self.assertEqual(clothes.describe(), "Wearing: nothing, your clothes and underwear are off")

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

    def test_outfit_says_what_it_did(self):
        from commands import portrait

        with mock.patch("web.livefeed.emit"), mock.patch("ui.add_message") as say, \
                mock.patch("mind.mood.tame", return_value=[]):
            portrait.handle("/outfit dressed")
            self.assertEqual(say.call_args[0][1], "Getting her dressed.")
            portrait.handle("/outfit on top")
            self.assertEqual(say.call_args[0][1], "Putting her top back on.")
            portrait.handle("/outfit off tie")
            self.assertEqual(say.call_args[0][1], "Taking off her tie.")
            self.assertNotIn("tame", " ".join(c[0][1] for c in say.call_args_list))

    def test_tame_mode_holds_undressing_only(self):
        from commands import portrait

        with mock.patch("web.livefeed.emit") as emit, mock.patch("ui.add_message") as say, \
                mock.patch("mind.mood.tame", return_value=["twitch"]):
            portrait.handle("/outfit off top")
            emit.assert_not_called()
            self.assertIn("tame mode while twitch is live", say.call_args[0][1])
            portrait.handle("/outfit underwear")
            emit.assert_not_called()
            portrait.handle("/outfit dressed")
            emit.assert_called_with("outfit", wear="dressed")
            self.assertEqual(say.call_args[0][1], "Getting her dressed.")

    def test_rave_set(self):
        from commands import portrait

        with mock.patch("web.livefeed.emit") as emit, mock.patch("ui.add_message"), \
                mock.patch.dict(portrait._rave, on=False):
            self.assertTrue(portrait.handle("/rave"))
            emit.assert_any_call("prop", name="pacifier", on=True)
            emit.assert_any_call("prop", name="glowstick_pink", on=True)
            self.assertTrue(portrait.handle("/rave"))
            emit.assert_called_with("prop", name="glowstick_pink", on=False)

    def test_blanket_on_off_and_toggle(self):
        from commands import portrait

        with mock.patch("web.livefeed.emit") as emit, mock.patch("ui.add_message"), \
                mock.patch.dict(portrait._blanket, on=False):
            self.assertTrue(portrait.handle("/blanket on"))
            emit.assert_called_with("prop", name="blanket", on=True)
            self.assertTrue(portrait.handle("/blanket"))
            emit.assert_called_with("prop", name="blanket", on=False)
            self.assertTrue(portrait.handle("/blanket"))
            emit.assert_called_with("prop", name="blanket", on=True)
            self.assertTrue(portrait.handle("/blanket off"))
            emit.assert_called_with("prop", name="blanket", on=False)


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
                        mock.patch.object(gestures, "clips", return_value=[]),
                        mock.patch.object(gestures, "_band", return_value=("lewd", ""))]   # the full menu
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
    "take off your bra": {"off": ["bra"]},
    "take your panties off": {"off": ["panties"]},
    "take off your underwear": {"off": ["bra", "panties"]},
    "lose the thong": {"off": ["panties"]},
    "put your bra back on": {"on": ["bra"]},
    "get naked for me": {"wear": "bare"},
    "be nude for me": {"wear": "bare"},
    "strip down to your underwear": {"wear": "underwear"},
    "the naked truth": None,
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
    "unhooks her bra and lets her bra fall": {"off": ["bra"]},
    "slips out of her panties": {"off": ["panties"]},
    "gets completely naked": {"wear": "bare"},
    "stands there naked": None,
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



@unittest.skipUnless(shutil.which("node"), "node isn't installed")
class Pieces(unittest.TestCase):
    """portrait/viewer/outfits.js on a stand-in model: underwear (bra, panties)
    stays on for 'underwear' and comes off for 'bare'; a model without it is
    as before. Labels from <model>.outfits.json."""

    def run_js(self, materials, names, steps):
        path = os.path.join(HERE, "portrait", "viewer", "outfits.js")
        script = r"""
const [path, mats, names, steps] = [process.argv[1], ...process.argv.slice(2).map(JSON.parse)];
class V { constructor(){this.x=0;this.y=0;this.z=0;} fromBufferAttribute(a,i){this.x=a.x[i];this.y=a.y[i];return this;} applyMatrix4(){return this;} }
const THREE = { Vector3: V };
const meshes = mats.map((m, i) => ({ isMesh: true, visible: true, material: { name: m },
  geometry: { index: { count: 300 }, attributes: { position: { count: 2, x: [-0.2, 0.2], y: [1.0 - i * 0.01, 1.0 - i * 0.01] } } },
  updateWorldMatrix(){}, matrixWorld: null }));
const vrm = { scene: { traverse: f => meshes.forEach(f) }, humanoid: { getNormalizedBoneNode: () => null } };
global.fetch = async () => ({ ok: true, json: async () => ({ pieces: names }) });
import(path).then(async m => {
  const o = await m.createOutfits({ THREE, vrm, url: 'x.vrm' });
  const out = [];
  for (const [fn, ...args] of steps) { o[fn](...args); out.push(o.state()); }
  console.log(JSON.stringify(out));
});"""
        res = subprocess.run(["node", "-e", script, "file://" + path, json.dumps(materials), json.dumps(names),
                              json.dumps(steps)], capture_output=True, text=True, check=True, timeout=30)
        return json.loads(res.stdout)

    def test_underwear_pieces(self):
        mats = ["N00_010_01_Onepiece_00_CLOTH_01 (Instance)", "N00_010_01_Onepiece_00_CLOTH_02 (Instance)",
                "N00_090_00_Underwear_Bra_CLOTH", "N00_090_00_Underwear_Panties_CLOTH"]
        names = {"CLOTH_01": "top", "CLOTH_02": "bottoms", "Underwear_Bra": "bra", "Underwear_Panties": "panties"}
        got = self.run_js(mats, names, [["wear", "underwear"], ["set", "bra", False], ["wear", "bare"],
                                        ["set", "bra", True], ["wear", "dressed"]])
        self.assertEqual(got, ["underwear", "partly", "bare", "partly", "dressed"])

    def test_cat_ears_are_hers_underwear_is_clothing(self):
        mats = ["Accessory_CatEar_01_CLOTH (Instance)", "N00_090_00_Underwear_Bra_CLOTH"]
        got = self.run_js(mats, {"Underwear_Bra": "bra"}, [["wear", "bare"]])
        self.assertEqual(got, ["bare"])          # one piece, the bra: the ears never came off

    def test_without_underwear_as_before(self):
        mats = ["N00_010_01_Onepiece_00_CLOTH_01 (Instance)"]
        got = self.run_js(mats, {"CLOTH_01": "top"}, [["wear", "underwear"], ["wear", "bare"]])
        self.assertEqual(got, ["underwear", "underwear"])


if __name__ == "__main__":
    unittest.main()
