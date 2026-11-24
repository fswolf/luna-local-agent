"""Spelling suggestions for the pages' right-click menu (core/spelling.py,
GET /chat/spell): the browser's own can't be read by a page."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: F401,E402

from core import spelling  # noqa: E402

try:
    import spellchecker  # noqa: F401
    HAVE = True
except ImportError:
    HAVE = False


@unittest.skipUnless(HAVE, "pyspellchecker isn't installed")
class Suggestions(unittest.TestCase):
    def test_a_misspelling_gets_the_word_meant(self):
        for wrong, right in (("skool", "school"), ("definately", "definitely"), ("recieve", "receive"),
                             ("teh", "the"), ("luv", "love")):
            out = spelling.check(wrong)
            self.assertFalse(out["known"], wrong)
            self.assertIn(right, out["suggestions"][:3], wrong)

    def test_written_the_way_it_was(self):
        self.assertIn("School", spelling.check("Skool")["suggestions"])
        self.assertIn("SCHOOL", spelling.check("SKOOL")["suggestions"])

    def test_right_words_and_non_words_are_left_alone(self):
        for word in ("the", "don't", "b4", "C:/path", "x", "https://a.example", ""):
            self.assertEqual(spelling.check(word), {"known": True, "suggestions": []}, word)

    def test_never_more_than_five(self):
        self.assertLessEqual(len(spelling.check("teh")["suggestions"]), 5)


class WithoutThePackage(unittest.TestCase):
    def test_quietly_nothing(self):
        with mock.patch.dict(spelling._state, {"checker": None, "failed": True}):
            self.assertEqual(spelling.check("skool"), {"known": True, "suggestions": []})


class Endpoint(unittest.TestCase):
    def test_the_page_asks_for_what_was_typed_at_once(self):
        import json
        from web import chat_web
        answer = lambda w: {"known": w != "skool", "suggestions": ["school"] if w == "skool" else []}
        with mock.patch("core.spelling.check", side_effect=answer):
            code, _kind, body = chat_web.handle("GET", "/spell", b"", {"query": "w=went&w=skool&w=skool"})
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body), {"went": {"known": True, "suggestions": []},
                                            "skool": {"known": False, "suggestions": ["school"]}})

    def test_a_batch_is_capped(self):
        with mock.patch("core.spelling.check", return_value={"known": True, "suggestions": []}):
            self.assertEqual(len(spelling.check_many([f"w{i}" for i in range(200)])), spelling.BATCH)


@unittest.skipUnless(HAVE, "pyspellchecker isn't installed")
class Remembered(unittest.TestCase):
    def test_the_same_word_isnt_worked_out_twice(self):
        spelling.check("wierdd")
        with mock.patch.object(spelling, "_suggest") as again:
            out = spelling.check("Wierdd")
        again.assert_not_called()
        self.assertTrue(all(w[:1].isupper() for w in out["suggestions"]))     # still written its way


if __name__ == "__main__":
    unittest.main()
