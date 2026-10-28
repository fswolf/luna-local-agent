"""Pages (mind/pages.py): a short joined-up note per subject she knows a lot
about, written while idle, brought along when you talk about it.

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

from core import turnctx  # noqa: E402
from mind import notebook, pages  # noqa: E402

FACTS = [("Shannon is Ryan's wife", "family"), ("Shannon uses an iMac", "hardware"),
         ("Shannon goes by NZ_Kitty on Discord", ""), ("Ryan has an RX 6950 XT", "hardware"),
         ("Ryan ordered a second RX 6950 XT for the server", "hardware"), ("Ryan likes coffee black", ""),
         ("On Mondays Ryan streams", "")]


class Pages(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.patches = [mock.patch.object(notebook, "DB_FILE", os.path.join(self.tmp, "notebook.db")),
                        mock.patch.object(pages, "_facts", lambda: list(FACTS)),
                        mock.patch.object(pages, "_episodes", lambda s: []),
                        mock.patch("config.USER", "Ryan", create=True),
                        mock.patch("config.AGENT_NAME", "Luna", create=True)]
        for p in self.patches:
            p.start()
        self.asked = []

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def ask(self, prompt):
        self.asked.append(prompt)
        subject = prompt.split("to do with ")[1].split(":")[0]
        return f"Here's the note: {subject} is something Ryan cares about, joined up."

    def test_what_gets_a_page(self):
        found = pages.subjects()
        self.assertEqual(set(found), {"Shannon", "hardware"})       # 3 facts each; Ryan himself never
        self.assertNotIn("Mondays", found)

    def test_sentence_starts_and_vague_tags(self):
        facts = [("Runs an Unraid server", ""), ("Runs Hyprland on Fedora", ""), ("Runs a NUC for web", ""),
                 ("Uses Fedora", "general"), ("Likes Fedora themes", "general"), ("Fedora is on the desktop", "general")]
        found = pages.subjects(facts)
        self.assertNotIn("Runs", found)                         # only ever the first word
        self.assertNotIn("general", found)                      # a tag that says nothing
        self.assertEqual(len(found["Fedora"]), 4)               # starts one fact, but a name elsewhere

    def test_a_tag_and_a_name_are_one_subject(self):
        facts = [("Shannon has an iMac", "shannon"), ("Ryan's wife is Shannon", ""), ("Shannon likes tea", "")]
        self.assertEqual(list(pages.subjects(facts)), ["Shannon"])

    def test_none_in_the_prompt_means_none(self):
        pages.write(self.ask)
        with mock.patch("config.current", lambda path: 0 if path == "self.pages_in_prompt" else None):
            self.assertEqual(pages.relevant("tell me about Shannon"), [])

    def test_written_once_until_something_changes(self):
        self.assertEqual(sorted(pages.write(self.ask)), ["Shannon", "hardware"])
        self.assertEqual(pages.get("shannon")["text"], "Shannon is something Ryan cares about, joined up.")
        self.assertEqual(pages.write(self.ask), [])                 # nothing changed: no model calls
        self.assertEqual(len(self.asked), 2)
        FACTS.append(("Shannon's birthday is November 2", "family"))
        try:
            self.assertEqual(pages.write(self.ask), ["Shannon"])    # only the page whose facts changed
        finally:
            FACTS.pop()

    def test_a_page_goes_when_its_subject_does(self):
        pages.write(self.ask)
        fewer = [f for f in FACTS if f[0] != "Shannon is Ryan's wife" and "NZ_Kitty" not in f[0]]
        with mock.patch.object(pages, "_facts", lambda: fewer):        # Shannon down to one fact
            pages.write(self.ask)
        self.assertEqual(set(pages.pages()), {"hardware"})

    def test_into_the_prompt(self):
        pages.write(self.ask)
        with mock.patch("mind.embedmem.rank", lambda q, texts: None):
            with turnctx.begin():
                block = pages.prompt_block("how's Shannon's mac doing?")
                self.assertIn("- Shannon:", block)
                self.assertEqual(pages.prompt_block("what's the weather"), "")
            with turnctx.begin(speaker="mike"):
                self.assertEqual(pages.prompt_block("tell me about Shannon"), "")    # a guest never sees them

    def test_switched_off(self):
        with mock.patch("config.current", lambda path: False if path == "self.pages" else None):
            self.assertEqual(pages.write(self.ask), [])
            self.assertEqual(pages.relevant("Shannon"), [])

    def test_commands_bits(self):
        pages.write(self.ask)
        self.assertEqual(pages.rebuild_all(), 2)
        self.assertEqual(sorted(pages.write(self.ask)), ["Shannon", "hardware"])
        self.assertEqual(pages.forget("SHANNON"), "Shannon")
        self.assertIsNone(pages.get("Shannon"))

    def test_stops_when_a_turn_starts(self):
        class Stop(Exception):
            pass

        def busy():
            raise Stop()
        with self.assertRaises(Stop):
            pages.write(self.ask, yield_=busy)
        self.assertEqual(pages.pages(), {})


if __name__ == "__main__":
    unittest.main()
