"""The identity ladder (people.py): owner, registered, guest met this
session, stranger. Prints are faked and files go to a temp folder.

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

import config  # noqa: E402
import facecheck  # noqa: E402
import longterm  # noqa: E402
import people  # noqa: E402
import presence  # noqa: E402
import turnctx  # noqa: E402

SHANNON, RYAN, MIKE = [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]
EDGE = [0.0, 0.3, 0.954]        # Ryan's score about 0.3: under the line, not clearly someone else
LINE = 0.36


class _Folder(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        for p in (mock.patch.object(people, "FOLDER", self.tmp),
                  mock.patch.object(config, "USER_NAME", "Ryan"),
                  mock.patch.object(config, "USER", "Ryan")):
            p.start()
            self.addCleanup(p.stop)
        people.reset_session()
        facecheck.reset()
        self.addCleanup(people.reset_session)
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def files(self):
        return sorted(os.listdir(self.tmp))


class Verdicts(_Folder):
    def test_a_match_is_a_name(self):
        people.add_prints("Shannon", "face", [SHANNON])
        self.assertEqual(people.verdict("face", SHANNON, LINE)[0], "Shannon")

    def test_clearly_not_the_owner_is_a_stranger(self):
        people.add_prints("Ryan", "face", [RYAN])
        self.assertEqual(people.verdict("face", MIKE, LINE)[0], people.STRANGER)

    def test_no_owner_prints_means_no_evidence(self):
        people.add_prints("Shannon", "face", [SHANNON])
        self.assertIsNone(people.verdict("face", MIKE, LINE)[0])

    def test_just_under_the_line_is_not_sure(self):
        people.add_prints("Ryan", "face", [RYAN])
        self.assertIsNone(people.verdict("face", EDGE, LINE)[0])

    def test_match_never_says_stranger(self):
        people.add_prints("Ryan", "face", [RYAN])
        self.assertIsNone(people.match("face", MIKE, LINE)[0])


class Deciding(_Folder):
    def test_a_station_stranger_stays_a_stranger(self):
        self.assertEqual(people.decide(people.STRANGER, True, 0.05, at_desk=False), people.STRANGER)

    def test_the_face_can_overrule_a_stranger_voice(self):
        with mock.patch.object(people, "_face", return_value="Ryan"):
            self.assertIsNone(people.decide(people.STRANGER, True, 0.05))

    def test_a_stranger_voice_with_no_face_to_go_on(self):
        with mock.patch.object(people, "_face", return_value=None):
            self.assertEqual(people.decide(people.STRANGER, True, 0.05), people.STRANGER)

    def test_unsure_voice_and_a_stranger_face(self):
        with mock.patch.object(people, "_face", return_value=people.STRANGER):
            self.assertEqual(people.decide(None, True, 0.25), people.STRANGER)

    def test_nothing_to_go_on_is_the_owner(self):
        with mock.patch.object(people, "_face", return_value=None):
            self.assertIsNone(people.decide(None, False))
            self.assertIsNone(people.decide(None, True, 0.25))

    def test_typed_stranger(self):
        with mock.patch.object(facecheck, "enabled", return_value=True), \
                mock.patch.object(people, "_face", return_value=people.STRANGER):
            self.assertEqual(people.typed_speaker(), people.STRANGER)

    def test_presence_reports_a_stranger(self):
        with mock.patch.object(presence, "present", return_value=True), \
                mock.patch.dict(presence._state, {"who": None, "stranger": True}):
            self.assertEqual(presence.verdict(), people.STRANGER)
            self.assertIsNone(presence.who())            # greetings never say "guest"


class Strangers(_Folder):
    def test_nothing_is_stored_for_a_stranger(self):
        with turnctx.begin(speaker=people.STRANGER):
            self.assertFalse(longterm.add_fact("They like trains a lot"))
            self.assertEqual(longterm.get_facts(), [])
        self.assertEqual(self.files(), [])

    def test_a_stranger_gets_the_short_tool_list(self):
        allowed = people.tools_for(people.STRANGER)
        self.assertIn("web_search", allowed)
        for private in ("read_file", "run_command", "check_email", "look_at_screen",
                        "search_history", "remember_fact"):
            self.assertNotIn(private, allowed)
        self.assertIsNone(people.tools_for(None))
        self.assertIsNone(people.tools_for("Shannon"))

    def test_the_prompt_line_keeps_the_owner_private(self):
        with turnctx.begin(speaker=people.STRANGER):
            line = people.user_line()
        self.assertIn("someone new", line)
        self.assertIn("private", line)

    def test_nobody_can_enroll_as_guest(self):
        self.assertFalse(people.meet(people.STRANGER)[0])


class SessionGuests(_Folder):
    def _seen(self):
        people.add_prints("Ryan", "face", [RYAN])
        people.verdict("face", MIKE, LINE)               # an unknown face, remembered for meet

    def test_meeting_puts_a_name_to_the_face(self):
        self._seen()
        ok, said = people.meet("Mike")
        self.assertTrue(ok, said)
        self.assertEqual(people.verdict("face", MIKE, LINE)[0], "Mike")
        self.assertEqual(self.files(), ["ryan.json"])   # nothing on disk for Mike

    def test_nobody_new_to_meet(self):
        self.assertFalse(people.meet("Mike")[0])

    def test_owner_and_enrolled_names_are_refused(self):
        self._seen()
        people.add_prints("Shannon", "face", [SHANNON])
        self.assertFalse(people.meet("ryan")[0])
        self.assertFalse(people.meet("Shannon")[0])

    def test_guest_facts_stay_in_memory(self):
        self._seen()
        people.meet("Mike")
        with turnctx.begin(speaker="Mike"):
            self.assertTrue(longterm.add_fact("Mike plays bass in a band"))
            self.assertIn("Mike plays bass in a band", longterm.get_facts())
            self.assertIn("met this session", people.user_line())
        self.assertEqual(self.files(), ["ryan.json"])
        self.assertIn("remember_fact", people.tools_for("Mike"))
        self.assertNotIn("read_file", people.tools_for("Mike"))

    def test_keep_makes_them_registered(self):
        self._seen()
        people.meet("Mike")
        people.add_fact("Mike", "Mike plays bass in a band")
        ok, said = people.keep("Mike")
        self.assertTrue(ok, said)
        self.assertIsNone(people.session_guest("Mike"))
        self.assertEqual(people.load("Mike")["facts"], ["Mike plays bass in a band"])
        self.assertEqual(len(people.load("Mike")["face"]), 1)
        self.assertIsNone(people.tools_for("Mike"))     # registered: the full list

    def test_forget_a_guest(self):
        self._seen()
        people.meet("Mike")
        self.assertTrue(people.forget_guest("mike"))
        self.assertEqual(people.verdict("face", MIKE, LINE)[0], people.STRANGER)

    def test_old_unknown_prints_cant_be_met(self):
        self._seen()
        vec, at = people._unknown["face"]
        people._unknown["face"] = (vec, at - people.MEET_WINDOW - 1)
        self.assertFalse(people.meet("Mike")[0])


class FaceCheckFreshness(_Folder):
    def test_someone_else_is_looked_at_again_sooner(self):
        with mock.patch.object(config, "PEOPLE_FACE_CHECK_MINUTES", 10, create=True):
            self.assertEqual(facecheck._fresh_for("Ryan"), 600)
            self.assertEqual(facecheck._fresh_for(None), 600)
            self.assertEqual(facecheck._fresh_for(people.STRANGER), facecheck.NOT_OWNER_EVERY)
            self.assertEqual(facecheck._fresh_for("Shannon"), facecheck.NOT_OWNER_EVERY)


if __name__ == "__main__":
    unittest.main()
