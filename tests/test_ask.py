"""plugins/ask.py: she asks a bigger model only when you tell her to.
No network: the call itself is replaced.

    python -m unittest discover tests        (from the repo folder)
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: E402,F401  (first: no real servers)

from core import turnctx  # noqa: E402
from plugins import ask  # noqa: E402


class Ask(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.patches = [
            mock.patch.object(ask, "_call", lambda p, q: self.calls.append((p, q)) or f"{p} says 42"),
            mock.patch.object(ask, "_key", lambda p: "k" if p in ("claude", "grok") else ""),
            mock.patch.object(ask, "_lewd", lambda: False),
            mock.patch.object(ask, "settings", lambda: {"provider": "claude", "models": {},
                                                        "daily_cap": 3, "max_tokens": 600}),
        ]
        for p in self.patches:
            p.start()
        ask._used.update(day="", count=0)
        ask.start()

    def tearDown(self):
        ask.stop()
        for p in self.patches:
            p.stop()

    def run_tool(self, said, question="what is 6x7?", **turn):
        ask.on_user_text(said)
        with turnctx.begin(**turn):
            return ask._run(question)

    def test_only_when_you_ask(self):
        self.assertIn("didn't ask", self.run_tool("what's 6 times 7?"))
        self.assertEqual(self.calls, [])
        self.assertIn("claude says 42", self.run_tool("ask Claude what 6 times 7 is"))
        self.assertIn("grok says 42", self.run_tool("can you check with grok?"))
        self.assertIn("claude says 42", self.run_tool("ask your big brother"))      # the default

    def test_a_message_is_good_for_a_follow_up_not_more(self):
        ask.on_user_text("ask claude about heat pumps")
        with turnctx.begin():
            self.assertIn("Claude answered", ask._run("how do heat pumps work?"))
            self.assertIn("Claude answered", ask._run("are they good in Alberta winters?"))
            self.assertIn("didn't ask", ask._run("and a third?"))

    def test_not_for_anyone_else(self):
        for turn in ({"private": False}, {"speaker": "guest"}, {"remote": "discord"}, {"job": "nightly"}):
            self.assertIn("Only the user's", self.run_tool("ask claude", **turn), turn)
        self.assertEqual(self.calls, [])

    def test_not_in_the_lewd_row(self):
        with mock.patch.object(ask, "_lewd", lambda: True):
            self.assertIn("Not now", self.run_tool("ask claude"))
        self.assertEqual(self.calls, [])

    def test_daily_cap(self):
        for _ in range(3):
            self.assertTrue(ask.ask("claude", "q")[0])
        ok, why = ask.ask("claude", "q")
        self.assertFalse(ok)
        self.assertIn("3 questions", why)

    def test_off_means_off(self):
        ask.stop()
        ask.on_user_text("ask claude")
        self.assertFalse(ask.running())
        import tools
        self.assertNotIn("ask_bigger_model", tools.names())

    def test_the_command(self):
        self.assertEqual(ask.command("what is 6x7?"), "Claude: claude says 42")
        self.assertEqual(ask.command("with grok what is 6x7?"), "Grok: grok says 42")
        self.assertIn("no ChatGPT key", ask.command("with openai hi"))
        self.assertEqual(ask._used["count"], 2)                                # that one didn't count
        self.assertIn("keys      claude, grok", ask.command(""))

    def test_a_mangled_key_file_doesnt_break_it(self):
        import tempfile
        self.patches[1].stop()
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
                f.write("{not json")
            with mock.patch.object(ask, "CREDENTIALS_FILE", f.name), \
                 mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "env-key"}):
                self.assertEqual(ask._key("claude"), "env-key")
                self.assertEqual(ask._key("grok"), "")
        finally:
            os.unlink(f.name)
            self.patches[1].start()

    def test_only_the_question_goes(self):
        self.run_tool("ask claude", question="  what is 6x7?  ")
        self.assertEqual(self.calls, [("claude", "what is 6x7?")])



class OnHerOwn(unittest.TestCase):
    """/ask auto on: she may ask when stuck, after trying her tools, once a turn,
    a few a day, and it always shows."""

    def setUp(self):
        self.calls, self.shown = [], []
        self.auto = {"provider": "claude", "models": {}, "daily_cap": 30, "max_tokens": 600,
                     "auto": True, "auto_daily": 2}
        import ui
        self.patches = [
            mock.patch.object(ask, "_call", lambda p, q: self.calls.append((p, q)) or "try a lock file"),
            mock.patch.object(ask, "_key", lambda p: "k" if p == "claude" else ""),
            mock.patch.object(ask, "_lewd", lambda: False),
            mock.patch.object(ask, "settings", lambda: self.auto),
            mock.patch.object(ui, "add_message", lambda who, text: self.shown.append(text)),
        ]
        for p in self.patches:
            p.start()
        ask._used.update(day="", count=0)
        ask._alone.update(day="", count=0)
        ask.on_user_text("the tests keep failing")      # nobody said "ask claude"
        ask.start()

    def tearDown(self):
        ask.stop()
        for p in self.patches:
            p.stop()

    def stuck(self, tried=True, **turn):
        with turnctx.begin(**turn):
            if tried:
                turnctx.current().exchanges.append({"name": "run_command", "arguments": {}, "result": "Error"})
            first = ask._run("why does pytest say the db is locked?")
            again = ask._run("and another?")
        return first, again

    def test_stuck_after_trying_she_asks_once_and_it_shows(self):
        first, again = self.stuck()
        self.assertIn("try a lock file", first)
        self.assertIn("on your own", first)
        self.assertIn("already asked", again)
        self.assertEqual(len(self.calls), 1)
        self.assertTrue(any("asked Claude on her own" in s for s in self.shown))

    def test_not_before_she_has_tried(self):
        first, _ = self.stuck(tried=False)
        self.assertIn("Try it yourself first", first)
        self.assertEqual(self.calls, [])

    def test_a_few_a_day(self):
        self.stuck()
        self.stuck()
        first, _ = self.stuck()
        self.assertIn("all the questions you can ask on your own today", first)
        self.assertEqual(len(self.calls), 2)

    def test_off_by_default(self):
        self.auto["auto"] = False
        first, _ = self.stuck()
        self.assertIn("didn't ask", first)
        self.assertEqual(self.calls, [])

    def test_never_for_anyone_else(self):
        for turn in ({"private": False}, {"speaker": "guest"}, {"remote": "discord"}, {"job": "nightly"}):
            first, _ = self.stuck(**turn)
            self.assertIn("Only the user's", first, turn)
        self.assertEqual(self.calls, [])

    def test_she_knows_she_can(self):
        with turnctx.begin(source="typed"):
            self.assertIn("ask_bigger_model", ask.prompt_line())
        self.auto["auto"] = False
        with turnctx.begin(source="typed"):
            self.assertEqual(ask.prompt_line(), "")

    def test_out_of_daily_questions_she_doesnt_try_or_hear_about_it(self):
        ask._used.update(day=ask.time.strftime("%Y-%m-%d"), count=30)
        first, _ = self.stuck()
        self.assertIn("all the questions", first)
        self.assertEqual(ask._alone["count"], 0)         # not spent on a question that can't go out
        with turnctx.begin(source="typed"):
            self.assertEqual(ask.prompt_line(), "")

    def test_search_first_only_if_she_can_search(self):
        for can in (True, False):
            with mock.patch.object(ask, "_can_search", return_value=can), turnctx.begin(source="typed"):
                self.assertEqual("Search the web" in ask.prompt_line(), can)

    def test_the_switch(self):
        with mock.patch.object(ask.config, "save_any") as saved:
            self.assertIn("on her own", ask.command("auto on"))
            saved.assert_called_with("plugins.ask.auto", True)
            self.assertIn("only when you tell her", ask.command("auto off"))
            saved.assert_called_with("plugins.ask.auto", False)



class Panes(unittest.TestCase):
    """The tools pane has the plugin and on-her-own switches; the settings pane knows the keys."""

    def rows(self, block):
        import plugins
        from ui import tools_pane
        fake = mock.Mock(running=lambda: False, available=lambda: True, why_unavailable=lambda: "")
        with mock.patch.object(plugins, "get", lambda n: fake if n == "ask" else None), \
                mock.patch.object(ask.config, "plugin_settings", lambda n: block):
            return {g[0]: g[1] for g in tools_pane._with_ask_switches([])}["Ask a bigger model"]

    def test_tools_pane_rows(self):
        rows = {r[0]: r for r in self.rows({"enabled": True, "auto": True})}
        self.assertTrue(rows["ask plugin"][1])
        self.assertEqual(rows["on her own"][5], "pluginset:plugins.ask.auto")
        self.assertTrue(rows["on her own"][1])
        self.assertGreater(rows["on her own"][4], 0)          # shows what the line costs
        self.assertFalse({r[0]: r for r in self.rows({})}["on her own"][1])

    def test_flipping_on_her_own_saves_it(self):
        from ui import tools_pane
        from ui.shared import view
        row = ("on her own", False, True, "", 80, "pluginset:plugins.ask.auto")
        with mock.patch.object(tools_pane, "_tool_rows", return_value=[row]), \
                mock.patch.object(view, "tool_cursor", 0), mock.patch.object(tools_pane, "add_message"), \
                mock.patch.object(tools_pane, "_refresh"), mock.patch.object(ask.config, "save_any") as saved:
            tools_pane._tool_toggle()
        saved.assert_called_with("plugins.ask.auto", True)

    def test_settings_pane_knows_them(self):
        from config.schema import SCHEMA
        for key in ("enabled", "provider", "auto", "auto_daily", "daily_cap"):
            self.assertIn(f"plugins.ask.{key}", SCHEMA)


if __name__ == "__main__":
    unittest.main()
