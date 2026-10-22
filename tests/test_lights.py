"""Light strips: portrait/lights.py (finding the strips and zones on a VRM)
and the portrait.lights settings. The maps are written to a temporary
copy of Luna's robot model, never next to the real one.

    python -m unittest discover tests        (from the repo folder)
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "portrait"))

from tests.offline import FAKE  # noqa: E402,F401  (first: no real servers)

import config  # noqa: E402

try:
    import numpy  # noqa: F401
    from PIL import Image

    import lights
except ImportError:                       # the portrait extra isn't installed
    lights = None

ROBOT = os.path.join(ROOT, "portrait", "models", "luna", "robot_default.vrm")
SOURCE = os.path.join(ROOT, "portrait", "source")


class Bones(unittest.TestCase):
    @unittest.skipUnless(lights, "needs numpy and Pillow")
    def test_names(self):
        for bone, zone in (("J_Bip_L_UpperArm", "arm_l"), ("J_Bip_R_LowerArm", "arm_r"),
                           ("J_Bip_L_Index2", "hand_l"), ("J_Bip_R_Hand", "hand_r"),
                           ("J_Bip_L_UpperLeg", "leg_l"), ("J_Bip_R_ToeBase", "foot_r"),
                           ("J_Sec_L_Bust1", "torso"), ("J_Bip_C_Hips", "torso"), ("J_Bip_C_Neck", "neck"),
                           ("J_Opt_L_CatEar1_01", "ears"), ("J_Opt_C_CatTail3_01", "tail"),
                           ("LeftForeArm", "arm_l"), ("RightFoot", "foot_r")):
            self.assertEqual(lights.bone_zone(bone), zone, bone)


@unittest.skipUnless(lights and os.path.isfile(ROBOT), "needs numpy, Pillow and the robot model")
class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.model = os.path.join(cls.tmp, "robot.vrm")
        shutil.copy(ROBOT, cls.model)
        layer = lambda p: os.path.join(SOURCE, p)                                    # noqa: E731
        panels = [(z, layer(p)) for z, p in (("chest", "layers/chest-led-pearl-slot-v4.png"),
                                             ("navel", "layers/belly-led-pearl-rose-v1.png"))
                  if os.path.isfile(layer(p))]
        private = [(z, layer(p)) for z, p in (("chest", "templates/guide_bra.png"),
                                              ("groin", "templates/guide_panties.png"))
                   if os.path.isfile(layer(p))]
        cls.has_layers = bool(panels and private)
        cls.args = (panels, private)
        cls.manifest = lights.build(cls.model, panels, private, quiet=True)
        cls.out = os.path.join(cls.tmp, "lights")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_materials(self):
        names = set(self.manifest["materials"])
        self.assertIn("N00_000_00_Body_00_SKIN", names)
        self.assertTrue(any("CatEar" in n for n in names))
        self.assertTrue(any("CatTail" in n for n in names))
        self.assertFalse(any("Face" in n or "Hair" in n for n in names))       # her face isn't a strip
        with open(os.path.join(self.out, "lights.json")) as f:
            self.assertEqual(json.load(f)["zones"][0], "none")

    def test_body_zones(self):
        body = self.manifest["materials"]["N00_000_00_Body_00_SKIN"]
        for zone in ("arm_l", "arm_r", "leg_l", "leg_r", "hand_l", "torso"):
            self.assertIn(zone, body["lit"])
        glow = numpy.asarray(Image.open(os.path.join(self.out, body["glow"])))
        self.assertEqual(glow.shape, (2048, 2048))
        self.assertGreater((glow == 255).sum(), 5000)
        self.assertTrue(body["color"].startswith("#"))

    def test_private(self):
        if not self.has_layers:
            self.skipTest("the bra / panties templates aren't in portrait/source")
        body = self.manifest["materials"]["N00_000_00_Body_00_SKIN"]
        self.assertIn("chest", body["lit"])
        self.assertIn("navel", body["lit"])
        zones = numpy.asarray(Image.open(os.path.join(self.out, body["zones"])).convert("RGB"))
        chest = numpy.all(zones == lights.ZONES[lights.ZONE_ID["chest"]][1], axis=2)
        self.assertTrue(chest[480:620, 850:1200].any())      # the chest LEDs sit under the bra
        self.assertFalse(chest[:, :480].any())               # never on an arm

    def test_hand_edits_kept(self):
        body = self.manifest["materials"]["N00_000_00_Body_00_SKIN"]
        path = os.path.join(self.out, body["glow"])
        Image.new("L", (2048, 2048), 7).save(path)
        lights.build(self.model, *self.args, quiet=True)
        self.assertEqual(Image.open(path).getpixel((5, 5)), 7)
        lights.build(self.model, *self.args, force=True, quiet=True)
        self.assertNotEqual(Image.open(path).getpixel((5, 5)), 7)


class Settings(unittest.TestCase):
    def test_color(self):
        coerce = config._coerce
        self.assertEqual(coerce("portrait.lights.color", "#FF4FB4"), "#ff4fb4")
        self.assertEqual(coerce("portrait.lights.color", "own"), "own")
        self.assertEqual(coerce("portrait.lights.color", "mood"), "")
        with self.assertRaises(ValueError):
            coerce("portrait.lights.color", "pinkish")
        self.assertEqual(coerce("portrait.lights.brightness", "5"), 2.0)

    def test_page_gets_them(self):
        import livefeed

        with mock.patch.object(config, "PORTRAIT_LIGHTS_ENABLED", True, create=True), \
             mock.patch.object(config, "PORTRAIT_LIGHTS_COLOR", "#22e0ff", create=True):
            got = livefeed.portrait_config()["lights"]
        self.assertEqual((got["enabled"], got["color"], got["style"]), (True, "#22e0ff", "neon"))
        sent = []
        with mock.patch.object(livefeed, "emit", lambda kind, **d: sent.append((kind, d))):
            livefeed.lights_changed()
        self.assertEqual(sent[0][0], "lights")

    def test_listed(self):
        for path in ("portrait.lights.enabled", "portrait.lights.color", "portrait.lights.brightness",
                     "portrait.lights.voice", "portrait.lights.private", "portrait.lights.style"):
            self.assertIn(path, config.SETTINGS)
            self.assertTrue(config.SETTINGS[path][1], path)       # live


if __name__ == "__main__":
    unittest.main()
