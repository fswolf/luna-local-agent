"""Luna cards (web/cards.py): a PNG with a zip on the end that carries her look."""
import io
import json
import os
import shutil
import tempfile
import unittest
import zipfile
from unittest import mock

import config
from web import cards

PNG = cards.PNG_SIG + b"\x00\x00\x00\x0dIHDR" + b"\x00" * 30     # enough of a picture for these tests
WAVE = {"name": "wave_hi", "keys": [[0, {"rightHand": [0, 0, 0]}], [1, {"rightHand": [0.2, 0, 0]}]]}


class CardTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.dir, "portrait", "models", "luna"))
        os.makedirs(os.path.join(self.dir, "portrait", "gestures"))
        self.model = os.path.join(self.dir, "portrait", "models", "luna", "her.vrm")
        with open(self.model, "wb") as f:
            f.write(b"glTF" + os.urandom(4096))
        with open(os.path.join(self.dir, "portrait", "models", "luna", "her.outfits.json"), "w") as f:
            json.dump({"pieces": {"Tops": "top", "Bottoms": "bottoms", "bad<key>": "x"}, "extra": 1}, f)
        self.settings = {"portrait.frame": "full", "portrait.hologram.enabled": True, "voice": "af_heart",
                         "tts.speed": 1.1}
        self.saved = {}
        patches = [mock.patch.object(config, "BASE_DIR", self.dir),
                   mock.patch.object(config, "current", side_effect=lambda k: self.settings.get(k)),
                   mock.patch.object(config, "save_any", side_effect=lambda k, v: self.saved.__setitem__(k, v))]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(shutil.rmtree, self.dir)

    def pack(self, name="test", **carry):
        carry = carry or {p: True for p in cards.PARTS}
        return cards.pack(name, PNG, carry, [WAVE, {"name": "Bad Name!", "keys": []}], model="models/luna/her.vrm")

    def test_a_card_is_a_picture_and_a_zip(self):
        out = self.pack("My Card")
        self.assertEqual(out["name"], "my-card")
        path = os.path.join(self.dir, "portrait", "cards", "my-card.png")
        with open(path, "rb") as f:
            self.assertTrue(f.read().startswith(PNG))
        z = zipfile.ZipFile(path)
        self.assertEqual(set(z.namelist()), {"model.vrm", "outfits.json", "gestures/wave_hi.json", "card.json"})
        card = json.loads(z.read("card.json"))
        self.assertEqual(card["format"], "luna-card")
        self.assertEqual(card["look"], {"portrait.frame": "full", "portrait.hologram.enabled": True})
        self.assertEqual(card["voice"], {"voice": "af_heart", "tts.speed": 1.1})
        self.assertEqual(json.loads(z.read("outfits.json")), {"pieces": {"Tops": "top", "Bottoms": "bottoms"}})
        self.assertTrue(any("Bad Name" in s for s in out["skipped"]))

    def test_only_what_is_ticked(self):
        out = self.pack("light", look=True)
        self.assertEqual(out["carries"], ["look"])
        z = zipfile.ZipFile(os.path.join(self.dir, "portrait", "cards", "light.png"))
        self.assertEqual(z.namelist(), ["card.json"])
        self.assertEqual(json.loads(z.read("card.json"))["voice"], {})

    def test_never_settings_outside_the_list(self):
        self.settings["llm.api_key"] = "secret"
        self.pack()
        z = zipfile.ZipFile(os.path.join(self.dir, "portrait", "cards", "test.png"))
        self.assertNotIn(b"secret", z.read("card.json"))

    def test_model_only_from_portrait_models(self):
        with self.assertRaises(ValueError):
            cards._model_path("../config.json")
        with self.assertRaises(ValueError):
            cards._model_path("models/luna/her.outfits.json")
        out = cards.pack("x", PNG, {"model": True}, model="../../etc/passwd.vrm")
        self.assertEqual(out["carries"], [])
        self.assertTrue(out["skipped"])

    def test_names_and_pictures(self):
        for bad in ("", "!!!", "-"):
            with self.assertRaises(ValueError):
                cards.slug(bad)
        self.assertEqual(cards.slug("../../evil"), "evil")
        with self.assertRaises(ValueError):
            cards.pack("x", b"GIF89a", {})

    def test_list_and_add(self):
        self.pack("one")
        with open(os.path.join(self.dir, "portrait", "cards", "one.png"), "rb") as f:
            data = f.read()
        c = cards.add(data, "one")              # taken: gets a new name
        self.assertEqual(c["name"], "one-2")
        self.assertEqual({c["name"] for c in cards.cards()}, {"one", "one-2"})
        with self.assertRaises(ValueError):
            cards.add(PNG)                      # a picture, but not a card
        with self.assertRaises(ValueError):
            cards.add(b"not a png")
        self.assertFalse(os.path.exists(os.path.join(self.dir, "portrait", "cards", ".incoming.png")))
        self.assertEqual(len(cards.cards()), 2)

    def test_a_zip_that_is_not_ours(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("card.json", json.dumps({"format": "something-else"}))
        with self.assertRaises(ValueError):
            cards.add(PNG + buf.getvalue())

    def test_put_on_with_the_same_model(self):
        self.pack()
        out = cards.apply("test")
        self.assertEqual(out["model"], "models/luna/her.vrm")
        self.assertEqual(self.saved["portrait.model"], "models/luna/her.vrm")
        self.assertEqual(self.saved["portrait.frame"], "full")
        self.assertEqual(self.saved["portrait.hologram.enabled"], "true")
        self.assertEqual(self.saved["voice"], "af_heart")
        self.assertTrue(os.path.isfile(os.path.join(self.dir, "portrait", "gestures", "wave_hi.js")))
        self.assertFalse(os.path.isdir(os.path.join(self.dir, "portrait", "models", "cards")))

    def test_put_on_somewhere_else(self):
        """Another person's Luna: no model of that name, so the card's copy goes in models/cards/."""
        self.pack()
        os.remove(self.model)
        out = cards.apply("test")
        self.assertEqual(out["model"], "models/cards/test/her.vrm")
        dest = os.path.join(self.dir, "portrait", "models", "cards", "test")
        self.assertTrue(os.path.isfile(os.path.join(dest, "her.vrm")))
        with open(os.path.join(dest, "her.outfits.json")) as f:
            self.assertEqual(json.load(f), {"pieces": {"Tops": "top", "Bottoms": "bottoms"}})

    def test_a_changed_model_is_not_overwritten(self):
        self.pack()
        with open(self.model, "ab") as f:
            f.write(b"edited since")
        out = cards.apply("test")
        self.assertEqual(out["model"], "models/cards/test/her.vrm")
        with open(self.model, "rb") as f:
            self.assertTrue(f.read().endswith(b"edited since"))

    def test_your_own_gesture_and_clothes_map_are_kept(self):
        self.pack()
        mine = os.path.join(self.dir, "portrait", "gestures", "wave_hi.js")
        with open(mine, "w") as f:
            f.write("// mine")
        with open(os.path.join(self.dir, "portrait", "models", "luna", "her.outfits.json"), "w") as f:
            json.dump({"pieces": {"Tops": "shirt"}}, f)
        out = cards.apply("test")
        with open(mine) as f:
            self.assertEqual(f.read(), "// mine")
        self.assertTrue(any("wave_hi" in s and "kept yours" in s for s in out["skipped"]))
        self.assertTrue(any(s.startswith("clothes") for s in out["skipped"]))

    def test_light_card_without_the_model(self):
        self.pack("light", look=True, gestures=True)
        os.remove(self.model)
        out = cards.apply("light")
        self.assertIsNone(out["model"])
        self.assertNotIn("portrait.model", self.saved)
        self.assertEqual(self.saved["portrait.frame"], "full")

    def test_the_picture_alone(self):
        import struct
        import zlib

        def chunk(kind, data):
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        png = (cards.PNG_SIG + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0))
               + chunk(b"IDAT", zlib.compress(b"\0" + b"\x80\x40\xc0" * 2 + b"\0" + b"\x80\x40\xc0" * 2))
               + chunk(b"IEND", b""))
        cards.pack("pic", png, {p: True for p in cards.PARTS}, model="models/luna/her.vrm")
        self.assertEqual(cards.picture("pic"), png)
        with self.assertRaises((ValueError, OSError)):
            cards.picture("../../etc/passwd")

    def test_delete(self):
        self.pack("gone")
        cards.apply("gone")
        os.remove(self.model)
        cards.apply("gone")                         # brings its own model in
        cards.remove("gone")
        self.assertEqual(cards.cards(), [])
        self.assertTrue(os.path.isfile(os.path.join(self.dir, "portrait", "models", "cards", "gone", "her.vrm")))
        with self.assertRaises(ValueError):
            cards.remove("gone")

    def test_own_gestures(self):
        gdir = os.path.join(self.dir, "portrait", "gestures")
        for n in ("wave", "mine", "_try"):
            with open(os.path.join(gdir, n + ".js"), "w") as f:
                f.write("export default {}")
        self.assertIsNone(cards.own_gestures())            # not a git copy: can't say
        import subprocess
        if shutil.which("git"):
            subprocess.run(["git", "init", "-q", self.dir], check=True)
            subprocess.run(["git", "-C", self.dir, "add", "portrait/gestures/wave.js"], check=True)
            self.assertEqual(cards.own_gestures(), ["mine"])

    def test_no_such_card(self):
        with self.assertRaises(ValueError):
            cards.apply("nothing")


if __name__ == "__main__":
    unittest.main()
