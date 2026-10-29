"""portrait/viewer/turns.js: what you say that turns her round. Run through
node; skipped where node isn't installed."""

import json
import os
import shutil
import subprocess
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TURNS = os.path.join(HERE, "portrait", "viewer", "turns.js")

CASES = {
    "Turn around": {"around": True},
    "spin around": {"around": True},
    "Show me your ass": {"to": 180},
    "show me your back": {"to": 180},
    "show me your bum": {"to": 180},
    "can I see your butt?": {"to": 180},
    "turn to the side": {"to": 90},
    "show me your profile": {"to": 90},
    "turn left": {"by": -90},
    "turn right": {"by": 90},
    "turn 180": {"by": 180},
    "turn 90 deg": {"by": 90},
    "turn -45": {"by": -45},
    "face me": {"to": 0},
    "turn back": {"to": 0},
    "turn around to face me": {"to": 0},
    # not requests
    "turn 360": None,
    "I had to turn left at the lights on my way home today": None,
    "this song makes me turn around and smile every single time": None,
    "turn off the lights": None,
    "it's your turn": None,
    "my back hurts": None,
}


@unittest.skipUnless(shutil.which("node"), "node isn't installed")
class Turns(unittest.TestCase):
    def test_what_people_say(self):
        script = ("import(process.argv[1]).then(m => { const out = {}; "
                  "for (const c of JSON.parse(process.argv[2])) out[c] = m.turnAsked(c); "
                  "console.log(JSON.stringify(out)); });")
        got = json.loads(subprocess.run(["node", "-e", script, "file://" + TURNS, json.dumps(list(CASES))],
                                        capture_output=True, text=True, check=True, timeout=30).stdout)
        for text, want in CASES.items():
            self.assertEqual(got[text], want, text)


if __name__ == "__main__":
    unittest.main()
