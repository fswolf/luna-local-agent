"""A turn she was sent back into (a follow-through) is kept in the order it
happened - her reply, the note that sent her back, what she called and said
after - and replayed that way, never as one glued reply said twice over."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: E402,F401

from core import history  # noqa: E402
from llm import replay, second_look  # noqa: E402
from llm.streaming import _last_raw  # noqa: E402

CALL = {"name": "system_status", "arguments": "{}", "result": "GPU 3% busy"}


class Steps(unittest.TestCase):
    def setUp(self):
        self.saved = {k: _last_raw.get(k) for k in ("steps", "steps_said", "exchanges")}
        _last_raw.update(steps=[], steps_said="", exchanges=[])
        self.addCleanup(_last_raw.update, self.saved)

    def follow(self, answer, prefix, more, calls, nudge="(Not from Ryan: do it now.)"):
        def rounds(payload, model, on_text, on_sentence):
            self.sent = payload["messages"]
            _last_raw["exchanges"] = list(calls)
            return more
        with mock.patch.object(second_look, "_tool_rounds", side_effect=rounds):
            return second_look._follow_through({"messages": []}, [{"role": "user", "content": "hi"}],
                                               answer, "m", None, None, prefix, nudge)

    def test_a_promise_kept_is_three_steps(self):
        full = self.follow("Fans are spinning! Let me check the hardware.", "", "Only 3% busy.", [CALL])
        self.assertEqual(full, "Fans are spinning! Let me check the hardware.\n\nOnly 3% busy.")
        self.assertEqual(second_look.turn_steps(full), [
            {"content": "Fans are spinning! Let me check the hardware.", "tools": []},
            {"note": "(Not from Ryan: do it now.)"},
            {"content": "Only 3% busy.", "tools": [CALL]},
        ])

    def test_calls_made_before_stay_with_the_first_reply(self):
        _last_raw["exchanges"] = [{"name": "list_files", "arguments": "{}", "result": "a b"}]
        full = self.follow("Done, it's fixed.", "", "Actually it wasn't - fixed now.", [CALL])
        steps = second_look.turn_steps(full)
        self.assertEqual(steps[0]["tools"][0]["name"], "list_files")
        self.assertEqual(steps[2]["tools"], [CALL])

    def test_a_prefix_is_part_of_what_she_said_after(self):
        full = self.follow("It's 42.", "Hang on, let me check.", "It's 41.", [CALL])
        self.assertEqual(second_look.turn_steps(full)[2]["content"], "Hang on, let me check. It's 41.")

    def test_a_hedge_added_afterwards_joins_the_last_step(self):
        full = self.follow("Let me check.", "", "3% busy.", [CALL])
        steps = second_look.turn_steps(full + " I'm not totally sure about that one, though.")
        self.assertEqual(steps[2]["content"], "3% busy. I'm not totally sure about that one, though.")

    def test_a_second_follow_through_carries_on(self):
        first = self.follow("Let me check.", "", "It's Tuesday.", [])
        second = self.follow(first, "Actually, let me double-check that.", "It's Monday.", [CALL],
                             nudge="(Not from Ryan - grounding.)")
        steps = second_look.turn_steps(second)
        self.assertEqual([("note" in s) for s in steps], [False, True, False, True, False])
        self.assertEqual(steps[-1]["content"], "Actually, let me double-check that. It's Monday.")

    def test_no_follow_through_no_steps(self):
        self.assertIsNone(second_look.turn_steps("Just a reply."))

    def test_she_was_shown_her_reply_then_the_note(self):
        self.follow("Let me check.", "", "3%.", [CALL])
        self.assertEqual([m["role"] for m in self.sent[-2:]], ["assistant", "user"])


class Replayed(unittest.TestCase):
    def test_in_the_order_it_happened(self):
        steps = [{"content": "Fans spinning! Let me check.", "tools": []},
                 {"note": "(Not from Ryan: do it now.)"},
                 {"content": "Only 3% busy.", "tools": [CALL]}]
        msgs = replay._replay({"role": "assistant", "content": "Fans spinning! Let me check.\n\nOnly 3% busy.",
                               "tools": [CALL], "steps": steps})
        self.assertEqual([(m["role"], m.get("content") or m.get("tool_calls") and "call") for m in msgs], [
            ("assistant", "Fans spinning! Let me check."),
            ("user", "(Not from Ryan: do it now.)"),
            ("assistant", "call"),
            ("tool", "GPU 3% busy"),
            ("assistant", "Only 3% busy."),
        ])
        self.assertEqual(msgs[2]["tool_calls"][0]["id"], msgs[3]["tool_call_id"])

    def test_stored_with_its_steps_and_cleaned_like_the_reply(self):
        steps = [{"content": "secret word", "tools": []}, {"note": "n"}, {"content": "more", "tools": [CALL]}]
        with mock.patch.object(history, "_data", {"summary": "", "messages": []}), \
                mock.patch("mind.forgetting.tombstones", return_value=["x"]), \
                mock.patch("mind.forgetting.clean", side_effect=lambda t, tombs=None: t.replace("secret", "[gone]")), \
                mock.patch("mind.forgetting.clean_calls", side_effect=lambda c, tombs=None: c):
            history.add_message("assistant", "secret word\n\nmore", tools=[CALL], steps=steps)
            entry = history.get_messages_full()[-1]
        self.assertEqual(entry["content"], "[gone] word\n\nmore")
        self.assertEqual(entry["steps"][0]["content"], "[gone] word")
        self.assertEqual(entry["steps"][1], {"note": "n"})
        self.assertEqual(entry["steps"][2]["tools"][0]["name"], "system_status")


class PromiseNudge(unittest.TestCase):
    def test_it_says_not_to_repeat_the_reply(self):
        src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "llm", "turns.py")).read()
        promise = src[src.index("but you didn't call a tool"):src.index("kept_promise = True")]
        self.assertIn("don't repeat any of it", promise)


if __name__ == "__main__":
    unittest.main()
