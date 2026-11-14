"""The portrait's files and its part of the stream (web/portrait_serve.py),
which the live monitor and the relay stations both serve.

    python -m unittest discover tests        (from the repo folder)
"""
import json
import os
import queue
import re
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: E402,F401  (first: no real servers)

import config  # noqa: E402
from web import livefeed  # noqa: E402
from web.portrait_serve import PORTRAIT_KINDS, PortraitCut, portrait_file, portrait_only  # noqa: E402

VIEWER = os.path.join(config.BASE_DIR, "portrait", "viewer")


class Kinds(unittest.TestCase):
    def test_every_kind_the_portrait_acts_on_gets_through(self):
        # the handle() switch in both renderers: a kind added there and not
        # here would work on the PC and silently do nothing on a tablet
        seen = set()
        for name in ("portrait.js", "live2d.js"):
            with open(os.path.join(VIEWER, name), encoding="utf-8") as f:
                text = f.read()
            body = text[text.index("switch (ev.t)"):]
            body = body[:body.index("\nfunction ")]
            seen |= set(re.findall(r"case '([a-z_]+)'", body))
        self.assertEqual(seen, set(PORTRAIT_KINDS))

    def test_both_renderers_open_the_stream_relative_to_their_page(self):
        for name in ("portrait.js", "live2d.js"):
            with open(os.path.join(VIEWER, name), encoding="utf-8") as f:
                text = f.read()
            self.assertIn("new EventSource('events')", text, name)


class OnlyThePortraitsPart(unittest.TestCase):
    def test_your_words_stay_out(self):
        got = portrait_only({"t": "turn", "at": 1, "text": "my secret", "source": "voice", "guest": False})
        self.assertEqual(got, {"t": "turn", "at": 1, "source": "voice", "guest": False})

    def test_her_thinking_stays_out_what_she_says_gets_through(self):
        self.assertIsNone(portrait_only({"t": "tok", "p": "t", "s": "hmm"}))
        self.assertEqual(portrait_only({"t": "tok", "p": "a", "s": "*hugs*"})["s"], "*hugs*")

    def test_tools_only_that_they_happened(self):
        self.assertEqual(portrait_only({"t": "tool", "at": 2, "name": "run_command", "args": "rm -rf"}),
                         {"t": "tool", "at": 2})

    def test_the_rest_of_the_turn_stays_out(self):
        for kind in ("context", "server", "rethink", "round", "tool_result", "chess"):
            self.assertIsNone(portrait_only({"t": kind, "x": 1}), kind)

    def test_her_state_gets_through(self):
        ev = {"t": "mood", "warmth": 0.5, "energy": 0.1}
        self.assertEqual(portrait_only(ev), ev)


class InlineThinking(unittest.TestCase):
    """LM Studio with reasoning parsing off sends her thinking inside the
    reply, as <think>...</think>: a station's portrait still never sees it."""

    def _say(self, cut, *pieces):
        out = []
        for p in pieces:
            got = cut({"t": "tok", "p": "a", "s": p})
            if got:
                out.append(got["s"])
        return "".join(out)

    def test_a_think_block_split_across_tokens(self):
        cut = PortraitCut()
        cut({"t": "turn", "source": "voice"})
        self.assertEqual(self._say(cut, "<th", "ink>secret", " plan</thi", "nk>", "*waves* hi"), "*waves* hi")

    def test_an_open_block_holds_everything_back(self):
        cut = PortraitCut()
        self.assertEqual(self._say(cut, "<think>still thinking"), "")

    def test_a_plain_reply_and_a_lone_less_than(self):
        cut = PortraitCut()
        self.assertEqual(self._say(cut, "*hugs* ", "2 <", " 3"), "*hugs* 2 < 3")

    def test_each_turn_starts_fresh(self):
        cut = PortraitCut()
        self._say(cut, "first reply")
        cut({"t": "turn", "source": "typed"})
        self.assertEqual(self._say(cut, "second"), "second")


class FilteredStream(unittest.TestCase):
    def setUp(self):
        self.snap = mock.patch.dict(livefeed._snapshot, clear=True)
        self.snap.start()

    def tearDown(self):
        self.snap.stop()

    def _lines(self, q):
        out = []
        while True:
            try:
                out.append(json.loads(q.get_nowait()[6:]))
            except queue.Empty:
                return out

    def test_a_filtered_page_gets_its_cut(self):
        q = livefeed.subscribe(portrait_only)
        try:
            self.assertTrue(livefeed.watching())
            livefeed.emit("turn", text="my secret", source="typed", guest=False)
            livefeed.emit("tok", p="t", s="thinking")
            livefeed.emit("mood", warmth=0.2)
            got = self._lines(q)
        finally:
            livefeed.unsubscribe(q)
        self.assertEqual([e["t"] for e in got], ["turn", "mood"])
        self.assertNotIn("text", got[0])
        self.assertFalse(livefeed.watching())

    def test_it_starts_with_where_things_stand(self):
        livefeed.emit("mood", warmth=0.3)
        livefeed.emit("context", used=5)
        q = livefeed.subscribe(portrait_only)
        try:
            got = self._lines(q)
        finally:
            livefeed.unsubscribe(q)
        self.assertEqual([e["t"] for e in got], ["mood"])

    def test_a_filter_that_breaks_loses_one_event_not_the_stream(self):
        def picky(ev):
            if ev["t"] == "mood":
                raise KeyError("x")
            return ev
        q = livefeed.subscribe(picky)
        try:
            livefeed.emit("mood", warmth=0.1)
            livefeed.emit("stage", status="idle")
            got = self._lines(q)
        finally:
            livefeed.unsubscribe(q)
        self.assertEqual([e["t"] for e in got], ["stage"])


class Files(unittest.TestCase):
    def test_the_page_and_its_config(self):
        code, kind, body, _cache = portrait_file("")
        self.assertEqual((code, kind.split(";")[0]), (200, "text/html"))
        self.assertIn(b"boot.js", body)
        code, kind, body, _cache = portrait_file("config.json")
        self.assertEqual(code, 200)
        self.assertIsInstance(json.loads(body), dict)

    def test_nothing_outside_portrait(self):
        for rel in ("../config/server.py", "..%2F..%2Fconfig.json", "/etc/passwd", "viewer/../../README.md"):
            self.assertEqual(portrait_file(rel)[0], 404, rel)


if __name__ == "__main__":
    unittest.main()
