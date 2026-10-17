"""Buttplug: a toy that vibrates and strokes can do both at once, each
stops only its own motor when its time is up, and nothing is left
running when a job is replaced or stopped. A fake send; no Intiface.

    python -m unittest discover tests        (from the repo folder)
"""
import os
import sys
import time
import unittest
from unittest import mock

# The repo on the path, so this also runs on its own: python tests/<this file>
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: E402,F401  (first: no real servers)

from plugins import buttplug as bp  # noqa: E402

BOTH = {"index": 0, "name": "Both", "scalar": [(0, "Vibrate")], "rotate": 0, "linear": 1}
VIBE = {"index": 1, "name": "Vibe", "scalar": [(0, "Vibrate"), (1, "Vibrate")], "rotate": 0, "linear": 0}
MACHINE = {"index": 2, "name": "Machine", "scalar": [(0, "Oscillate")], "rotate": 0, "linear": 0}


def until(check, seconds=3):
    end = time.time() + seconds
    while time.time() < end:
        if check():
            return True
        time.sleep(0.02)
    return False


class Channels(unittest.TestCase):
    def setUp(self):
        self.sent = []
        self.patches = [
            mock.patch.dict(bp._state, {"connected": True, "devices": {0: BOTH, 1: VIBE, 2: MACHINE}}),
            mock.patch.object(bp, "_motion_caps", return_value=(1.0, 0.0)),   # no ramp: timings stay short
            mock.patch.object(bp, "_send", side_effect=lambda kind, body=None, **kw: self.sent.append((kind, body))),
        ]
        for p in self.patches:
            p.start()
        bp.stop_all_devices()
        self.sent.clear()

    def tearDown(self):
        bp.stop_all_devices()
        time.sleep(0.2)
        for p in self.patches:
            p.stop()

    def kinds(self, index):
        return [k for k, b in self.sent if (b or {}).get("DeviceIndex") == index]

    def last_level(self, index):
        levels = [b["Scalars"][0]["Scalar"] for k, b in self.sent
                  if k == "ScalarCmd" and b["DeviceIndex"] == index]
        return levels[-1] if levels else None

    def test_vibrate_and_stroke_together(self):
        bp._play([BOTH], 0.4, lambda t: 0.5)
        bp._stroke([BOTH], 1.5, 1.0)
        self.assertTrue(until(lambda: "LinearCmd" in self.kinds(0)))
        self.assertTrue(until(lambda: self.last_level(0) == 0.0))       # vibration's time is up...
        self.assertNotIn("StopDeviceCmd", self.kinds(0))                 # ...but the stroke goes on
        strokes = self.kinds(0).count("LinearCmd")
        time.sleep(0.4)
        self.assertGreater(self.kinds(0).count("LinearCmd"), strokes)
        self.assertTrue(until(lambda: "StopDeviceCmd" in self.kinds(0)))  # both done: full stop

    def test_stroke_ending_leaves_the_vibration_on(self):
        bp._play([BOTH], 1.5, lambda t: 0.7)
        bp._stroke([BOTH], 0.3, 1.0)
        time.sleep(0.6)
        self.assertNotIn("StopDeviceCmd", self.kinds(0))
        self.assertEqual(self.last_level(0), 0.7)

    def test_a_replaced_job_turns_off_what_the_new_one_doesnt_drive(self):
        bp._play([VIBE], 5, lambda t: 0.6)
        until(lambda: self.last_level(1) == 0.6)
        bp._play([BOTH], 5, lambda t: 0.3)                                 # Vibe isn't in this one
        self.assertTrue(until(lambda: "StopDeviceCmd" in self.kinds(1)))

    def test_a_machine_builds_up_and_vibration_never_drives_it(self):
        bp._play([MACHINE], 0.3, lambda t: 1.0)
        time.sleep(0.2)
        self.assertNotIn("ScalarCmd", self.kinds(2))                      # toy_vibrate's job: not a machine
        with mock.patch.object(bp, "_motion_caps", return_value=(1.0, 1.0)):
            bp._stroke([MACHINE], 1.6, 0.8)
            self.assertTrue(until(lambda: "ScalarCmd" in self.kinds(2)))
            levels = lambda: [b["Scalars"][0]["Scalar"] for k, b in self.sent  # noqa: E731
                              if k == "ScalarCmd" and b["DeviceIndex"] == 2]
            self.assertLess(levels()[0], 0.3)                             # starts slow
            self.assertTrue(until(lambda: max(levels()) == 0.8))         # reaches the speed asked for
            self.assertTrue(until(lambda: "StopDeviceCmd" in self.kinds(2)))

    def test_stop_all_ends_every_job(self):
        bp._play([BOTH, VIBE], 5, lambda t: 0.5)
        bp._stroke([BOTH], 5, 0.5)
        bp.stop_all_devices()
        self.assertEqual(bp._jobs["spin"]["devs"], set())
        self.assertEqual(bp._jobs["stroke"]["devs"], set())
        self.assertIn("StopAllDevices", [k for k, _b in self.sent])


if __name__ == "__main__":
    unittest.main()
