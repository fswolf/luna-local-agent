"""Telling people apart by voice (voices.py), deciding who's talking
(people.decide), and a guest's own memories (people.py + longterm.py).
No speaker model here: voice prints are faked, files go to a temp folder.

    python -m unittest discover tests        (from the repo folder)
"""
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: E402,F401  (first: no real servers)

import numpy as np  # noqa: E402

import config  # noqa: E402
import longterm  # noqa: E402
import people  # noqa: E402
import presence  # noqa: E402
import turnctx  # noqa: E402
import voices  # noqa: E402

SHANNON, RYAN = [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]


class _Folder(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.patches = [mock.patch.object(people, "FOLDER", self.tmp),
                        mock.patch.object(config, "USER_NAME", "Ryan"),
                        mock.patch.object(config, "USER", "Ryan"),
                        mock.patch.object(config, "PEOPLE_VOICE", True, create=True),
                        mock.patch.object(config, "PEOPLE_VOICE_MATCH", 0.3, create=True),
                        mock.patch.object(voices, "available", return_value=True),
                        mock.patch.object(voices, "_tell", lambda line: None)]
        for p in self.patches:
            p.start()
        voices._state["enroll"] = None

    def tearDown(self):
        voices._state["enroll"] = None
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)


class Voices(_Folder):
    def test_nothing_to_compare_with_is_no_answer(self):
        self.assertEqual(voices.identify(np.zeros(32000)), (None, None))

    def test_enrolment_takes_the_next_turns(self):
        with mock.patch.object(voices, "threading"):
            ok, _said = voices.enroll("Shannon", turns=2)
        self.assertTrue(ok)
        with mock.patch.object(voices, "print_of", return_value=SHANNON):
            self.assertEqual(voices.identify("x.wav")[0], "Shannon")
            self.assertEqual(voices.identify("x.wav")[0], "Shannon")
        self.assertIsNone(voices._state["enroll"])
        self.assertEqual(len(people.load("Shannon")["voice"]), 2)

    def test_enrolment_gives_lines_to_read(self):
        told = []
        with mock.patch.object(voices, "threading"), mock.patch.object(voices, "_tell", told.append):
            ok, said = voices.enroll("Shannon")
            lines = voices._state["enroll"]["lines"]
            self.assertEqual(len(set(lines)), voices.ENROLL_TURNS)          # 5 different ones
            self.assertTrue(set(lines) <= set(voices.LINES))
            self.assertIn(lines[0], said)
            self.assertTrue(voices.enrolling())
            with mock.patch.object(voices, "print_of", return_value=None):
                voices.identify("x.wav")                                     # too short: same line again
            self.assertIn(lines[0], told[-1])
            with mock.patch.object(voices, "print_of", return_value=SHANNON):
                voices.identify("x.wav")
            self.assertIn(lines[1], told[-1])
            # no speaker model: the enrolment stops instead of going deaf
            voices._state["error"] = "the speaker model didn't load"
            try:
                with mock.patch.object(voices, "print_of", return_value=None):
                    voices.identify("x.wav")
            finally:
                voices._state["error"] = ""
            self.assertFalse(voices.enrolling())
            self.assertIn("stopped", told[-1])
        for line in voices.LINES:
            self.assertTrue(8 <= len(line.split()) <= 15, line)

    def test_matches_the_closest_voice(self):
        people.add_prints("Shannon", "voice", [SHANNON])
        people.add_prints("Ryan", "voice", [RYAN])
        with mock.patch.object(voices, "print_of", return_value=[0.9, 0.2, 0.1]):
            self.assertEqual(voices.identify("x.wav")[0], "Shannon")
        with mock.patch.object(voices, "print_of", return_value=[0.0, 0.0, 1.0]):
            name, score = voices.identify("x.wav")
            self.assertIsNone(name)
            self.assertIsNotNone(score)            # compared, matched nobody

    def test_switched_off(self):
        people.add_prints("Shannon", "voice", [SHANNON])
        with mock.patch.object(config, "PEOPLE_VOICE", False, create=True), \
                mock.patch.object(voices, "print_of", return_value=SHANNON):
            self.assertEqual(voices.identify("x.wav"), (None, None))

    def test_audio_is_made_16k_float(self):
        pcm = (np.sin(np.linspace(0, 100, 48000)) * 20000).astype(np.int16)
        with mock.patch.object(voices, "RATE", 16000):
            out = voices._samples(pcm)
        self.assertEqual(out.dtype, np.float32)
        self.assertLessEqual(float(np.abs(out).max()), 1.0)
        self.assertIsNone(voices._samples(np.zeros(1000, np.float32)))   # too short


class WhoIsTalking(_Folder):
    def test_a_voice_wins(self):
        self.assertEqual(people.decide("Shannon", voice_checked=True), "Shannon")

    def test_the_owner_is_none(self):
        self.assertIsNone(people.decide("ryan", voice_checked=True))

    def test_face_stands_in_when_voices_cant_be_compared(self):
        with mock.patch.object(presence, "who", return_value="Shannon"):
            self.assertEqual(people.decide(None, voice_checked=False), "Shannon")
            # a voice that was compared and matched nobody is the owner,
            # even with Shannon on camera
            self.assertIsNone(people.decide(None, voice_checked=True))

    def test_user_line_names_the_guest(self):
        people.add_prints("Shannon", "face", [SHANNON], pronouns="she/her")
        with turnctx.begin(speaker="Shannon"):
            line = people.user_line()
        self.assertIn("Shannon (she/her)", line)
        self.assertIn("not Ryan", line)


class GuestMemories(_Folder):
    def test_a_guests_facts_are_their_own(self):
        with mock.patch.object(longterm, "factstore") as store, \
                mock.patch.object(longterm, "backend", return_value="sqlite"):
            with turnctx.begin(speaker="Shannon"):
                self.assertTrue(longterm.add_fact("Shannon is allergic to cats."))
                self.assertFalse(longterm.add_fact("Shannon is allergic to cats."))
                self.assertEqual(longterm.relevant_facts("cats"), ["Shannon is allergic to cats."])
                self.assertEqual(longterm.get_facts(), ["Shannon is allergic to cats."])
            store.add.assert_not_called()
            store.search.assert_not_called()

    def test_a_guest_can_correct_and_forget_theirs(self):
        people.add_fact("Shannon", "Shannon drives a Civic.")
        with turnctx.begin(speaker="Shannon"):
            (old, new), _ = longterm.update_fact("Civic", "Shannon drives a Corolla.")
            self.assertEqual(people.facts("Shannon"), ["Shannon drives a Corolla."])
            removed, _ = longterm.forget_fact("Corolla")
        self.assertEqual(removed, "Shannon drives a Corolla.")
        self.assertEqual(people.facts("Shannon"), [])

    def test_the_owner_never_sees_a_guests_facts(self):
        people.add_fact("Shannon", "Shannon works nights.")
        with mock.patch.object(longterm, "backend", return_value="json"), \
                mock.patch.dict(longterm.memory, {"long_term_facts": ["Ryan builds Luna."]}):
            self.assertEqual(longterm.get_facts(), ["Ryan builds Luna."])


if __name__ == "__main__":
    unittest.main()
