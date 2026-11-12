"""llm.stable_prompt: the system prompt stays the same from turn to turn, and
what changes (the clock, the live lines, the memories picked for this
message) rides in a note in front of the latest message - never stored in
history. And the cards (mind/cards.py) that sit in the stable part.

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
from core import turnctx  # noqa: E402
from llm import prompts  # noqa: E402
from mind import cards, notebook  # noqa: E402


class _Live(unittest.TestCase):
    """Every changing part patched to say what it is, and to change."""

    def setUp(self):
        from mind import knowledge, longterm, projects, situation, skills
        self.tick = 0

        def now():
            self.tick += 1
            return f"CLOCK-{self.tick}"

        patches = [
            mock.patch.object(prompts.timeutil, "describe_now", now),
            mock.patch.object(situation, "block", lambda: "SITUATION-LINE\n"),
            mock.patch.object(longterm, "relevant_facts", lambda q, limit=None: [f"FACT-{q}"]),
            mock.patch.object(notebook, "relevant_lessons", lambda q: [f"LESSON-{q}"]),
            mock.patch.object(notebook, "latest_episode", lambda: None),
            mock.patch.object(notebook, "relevant_episodes", lambda q: []),
            mock.patch.object(notebook, "game_feelings", lambda: {}),
            mock.patch.object(projects, "prompt_block", lambda q: ""),
            mock.patch.object(skills, "prompt_block", lambda q: ("", [])),
            mock.patch.object(knowledge, "prompt_block", lambda q: ""),
            mock.patch.object(prompts.history, "get_summary", lambda: "SUMMARY-OLD"),
            mock.patch.object(prompts, "_card", lambda private: "CARD-RYAN\n" if private else ""),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def parts(self, query, on=True):
        with mock.patch.object(config, "LLM_STABLE_PROMPT", on, create=True):
            with turnctx.begin(source="typed"):
                return prompts.build_prompt_parts(query, "TIMING-NOTE")


class StablePrompt(_Live):
    def test_the_system_prompt_stays_the_same(self):
        one, live_one = self.parts("coffee")
        two, live_two = self.parts("servers")
        self.assertEqual(one, two)                                   # what the server reuses
        for changing in ("CLOCK-", "SITUATION-LINE", "FACT-", "LESSON-", "TIMING-NOTE"):
            self.assertNotIn(changing, one)
        self.assertIn("CARD-RYAN", one)                              # the card is stable: it stays up top
        self.assertIn("SUMMARY-OLD", one)
        self.assertIn("FACT-coffee", live_one)
        self.assertIn("FACT-servers", live_two)
        self.assertIn("LESSON-coffee", live_one)
        self.assertIn("SITUATION-LINE", live_one)
        self.assertIn("TIMING-NOTE", live_one)
        self.assertTrue(live_one.startswith(prompts.LIVE_OPEN))
        self.assertTrue(live_one.rstrip().endswith(prompts.LIVE_CLOSE))
        self.assertNotEqual(live_one, live_two)

    def test_off_is_the_old_prompt(self):
        whole, live = self.parts("coffee", on=False)
        self.assertEqual(live, "")
        for part in ("CLOCK-", "SITUATION-LINE", "FACT-coffee", "LESSON-coffee", "TIMING-NOTE", "CARD-RYAN"):
            self.assertIn(part, whole)
        self.assertLess(whole.index("Right now:"), whole.index("Personality:"))

    def test_stream_chat_gets_no_private_parts(self):
        with mock.patch.object(config, "LLM_STABLE_PROMPT", True, create=True):
            with turnctx.begin(source="typed"):
                system, live = prompts.build_prompt_parts("coffee", "", private=False)
        for private in ("CARD-RYAN", "SITUATION-LINE", "FACT-", "LESSON-", "SUMMARY-OLD"):
            self.assertNotIn(private, system + live)
        self.assertIn("CLOCK-", live)


class WithLive(unittest.TestCase):
    def test_words_or_parts(self):
        self.assertEqual(prompts.with_live("", "hi"), "hi")
        self.assertEqual(prompts.with_live("NOTE\n", "hi"), "NOTE\nhi")
        parts = [{"type": "text", "text": "(said out loud)\nhi"}, {"type": "input_audio", "input_audio": {}}]
        out = prompts.with_live("NOTE\n", parts)
        self.assertEqual(out[0]["text"], "NOTE\n(said out loud)\nhi")
        self.assertEqual(parts[0]["text"], "(said out loud)\nhi")          # the original isn't touched
        self.assertIs(out[1], parts[1])


class ATurn(_Live):
    """A whole turn: the note goes in front of the message, and history keeps the message."""

    def turn(self, on=True, recording=None):
        import llm
        sent, stored = [], []

        def generate(payload, *a):
            sent.append(payload)
            return "Okay."

        from core import history
        with mock.patch.object(config, "LLM_STABLE_PROMPT", on, create=True), \
                mock.patch.object(config, "ADAPTIVE_ENABLED", False, create=True), \
                mock.patch.object(config, "GROUNDING_ENABLED", False, create=True), \
                mock.patch.object(config, "FOLLOW_THROUGH", False, create=True), \
                mock.patch("llm.turns._record_thoughts", lambda *a, **k: None), \
                mock.patch("training.dataset.note_turn", lambda *a, **k: None), \
                mock.patch("llm.turns._generate", generate), \
                mock.patch("llm.turns._tool_rounds", lambda payload, *a: generate(payload)), \
                mock.patch.object(history, "add_message", lambda role, text, **k: stored.append((role, text))), \
                mock.patch.object(history, "save", lambda: None), \
                mock.patch.object(history, "maybe_summarize", lambda m: None), \
                mock.patch("core.transcript.add", lambda *a: None), \
                mock.patch("life.reminders.extract_in_background", lambda *a: None), \
                mock.patch("mind.longterm.extract_in_background", lambda *a: None), \
                turnctx.begin(source="voice", recording=recording):
            llm.ask("how's the coffee", "fake", context=None, tools_allowed=[], remember=True)
        return sent[0], stored

    def test_note_in_front_of_the_message_not_in_history(self):
        payload, stored = self.turn()
        last = payload["messages"][-1]["content"]
        self.assertTrue(last.startswith(prompts.LIVE_OPEN))
        self.assertTrue(last.endswith("how's the coffee"))
        self.assertIn("FACT-how's the coffee", last)
        self.assertNotIn("FACT-", payload["messages"][0]["content"])
        self.assertIn(("user", "how's the coffee"), stored)          # what was said, nothing else
        self.assertFalse(any(prompts.LIVE_OPEN in text for _r, text in stored))

    def test_off_sends_the_message_bare(self):
        payload, _stored = self.turn(on=False)
        self.assertEqual(payload["messages"][-1]["content"], "how's the coffee")
        self.assertIn("FACT-how's the coffee", payload["messages"][0]["content"])


class Cards(unittest.TestCase):
    MINE = ["Ryan runs Unraid", "Ryan builds Luna", "Ryan likes his coffee black", "Ryan streams on Mondays"]
    HERS = ["Shannon uses an iMac", "Shannon goes by NZ_Kitty", "Shannon plays Second Life"]

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        from senses import people
        everyone = {"Shannon": {"name": "Shannon", "facts": list(self.HERS)},
                    "Bob": {"name": "Bob", "facts": ["Bob is a plumber"]}}           # too little for a card
        self.patches = [mock.patch.object(notebook, "DB_FILE", os.path.join(self.tmp, "notebook.db")),
                        mock.patch.object(cards, "_owner_facts", lambda: list(self.MINE)),
                        mock.patch.object(people, "everyone", lambda: everyone),
                        mock.patch.object(people, "session_guest", lambda n: {"facts": []} if n == "Visitor" else None),
                        mock.patch("config.USER", "Ryan", create=True),
                        mock.patch("config.USER_NAME", "Ryan", create=True),
                        mock.patch("config.SELF_CARD", True, create=True)]
        for p in self.patches:
            p.start()
        self.asked = []

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def ask(self, prompt):
        self.asked.append(prompt)
        who = prompt.split("saved about ")[1].split(":")[0]
        return f"Here's the card: {who} is someone she knows well, card text."

    def test_who_gets_one_and_it_isnt_rewritten_for_nothing(self):
        written = cards.write(self.ask)
        self.assertEqual(written, ["Ryan", "Shannon"])               # yours first; Bob has too little
        self.assertEqual(cards.get("me")["text"], "Ryan is someone she knows well, card text.")
        self.assertEqual(cards.write(self.ask), [])                  # nothing changed, nothing asked
        self.assertEqual(len(self.asked), 2)
        self.MINE.append("Ryan bought a 7900 XT")
        try:
            self.assertEqual(cards.write(self.ask), ["Ryan"])        # only the one whose facts moved
        finally:
            self.MINE.pop()

    def test_each_turn_gets_its_own_card_and_never_yours(self):
        cards.write(self.ask)
        with turnctx.begin(source="typed"):
            self.assertIn("Ryan is someone", cards.prompt_block())
        with turnctx.begin(source="voice", speaker="Shannon"):
            block = cards.prompt_block()
            self.assertIn("Shannon is someone", block)
            self.assertNotIn("Ryan is", block)
        for nobody in ("someone new", "Visitor"):
            with turnctx.begin(source="voice", speaker=nobody):
                self.assertEqual(cards.prompt_block(), "")

    def test_a_failed_read_drops_nobody(self):
        cards.write(self.ask)

        def broken():
            raise OSError("facts.db is locked")
        with mock.patch.object(cards, "_owner_facts", broken):
            cards.write(self.ask)
        self.assertIsNotNone(cards.get("me"))

    def test_missing_until_written(self):
        self.assertTrue(cards.missing())
        cards.write(self.ask)
        self.assertFalse(cards.missing())
        cards.rebuild_all()
        self.assertTrue(cards.missing())                            # marked for rewriting
        cards.write(self.ask)
        self.assertFalse(cards.missing())
        with mock.patch("config.SELF_CARD", False, create=True):
            cards.forget("me")
            self.assertFalse(cards.missing())                       # off: nothing is missing

    def test_off_and_forget(self):
        cards.write(self.ask)
        with mock.patch("config.SELF_CARD", False, create=True), turnctx.begin(source="typed"):
            self.assertEqual(cards.prompt_block(), "")
        self.assertEqual(cards.forget("shannon"), "Shannon")
        self.assertIsNone(cards.get("Shannon"))
        self.assertEqual(cards.rebuild_all(), 1)
        self.assertEqual(cards.write(self.ask), ["Ryan", "Shannon"])


if __name__ == "__main__":
    unittest.main()
