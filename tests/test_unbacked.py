"""Claims her tools don't back (llm/second_look.py _unbacked): "done and done"
with nothing written, "it works" right after a run that failed. From a real
turn where she said she'd rewritten a script and had only run it.

    python -m unittest discover tests        (from the repo folder)
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: F401,E402  (first: no real servers)

from llm.second_look import _unbacked  # noqa: E402

RAN_AND_FAILED = {"name": "run_command", "arguments": json.dumps({"command": "python3 ~/w/ascii_wheel.py"}),
                  "result": "$ python3 ~/w/ascii_wheel.py\n(exited straight away with code 1)\n--- output ---\nTraceback"}
EDITED = {"name": "edit_file", "arguments": "{}", "result": "Edited ~/w/ascii_wheel.py (31 lines changed). Check: Python syntax OK."}
RAN_OK = {"name": "run_command", "arguments": json.dumps({"command": "bash ~/w/count.sh"}),
          "result": "$ bash ~/w/count.sh\n(exit code 0 after 0.0s)\n--- output ---\nFound 0 errors"}


class Claims(unittest.TestCase):
    def test_done_with_only_a_run(self):
        answer = "Let me rewrite this using pure ANSI escape codes~ Mmm~ done and done~ 💕"
        nudge = _unbacked(answer, [RAN_AND_FAILED], "update the script luna lol")
        self.assertIn("done and done", nudge)
        self.assertIn("nothing this turn changed a file", nudge)

    def test_an_edit_backs_it(self):
        answer = "I've updated it with Claude's math, it should look round now."
        self.assertEqual(_unbacked(answer, [EDITED, RAN_OK], "fix it"), "")

    def test_a_shell_write_backs_it(self):
        sed = {"name": "run_command", "arguments": json.dumps({"command": "sed -i 's/-e//' count.sh"}),
               "result": "$ sed -i ...\n(exit code 0 after 0.0s)"}
        self.assertEqual(_unbacked("I've fixed the script.", [sed], "fix it"), "")

    def test_writing_it_right_now_with_no_write(self):
        # a real turn: asked to save a script, she said this and called nothing
        answer = ("You want me to save it in my sandbox? Of course~ I'm writing it to "
                  "`~/lunas_sandbox/scripts/cube_3d.py` right now. It'll be there whenever you want it~")
        nudge = _unbacked(answer, [], "silly luna save it in your sand box :)")
        self.assertIn("I'm writing it to", nudge)
        self.assertIn("nothing this turn changed a file", nudge)

    def test_writing_without_a_place_is_not_a_claim(self):
        self.assertEqual(_unbacked("I'm writing you a little poem~ here it is:", [], "write me a poem"), "")
        self.assertEqual(_unbacked("I'm putting it in perspective, love~", [], "save me from this day"), "")

    def test_saving_to_a_file_name_or_your_folder(self):
        self.assertIn("nothing this turn", _unbacked("I'm saving it as cube.py now~", [], "save it"))
        self.assertIn("nothing this turn", _unbacked("I'm putting it in your sandbox right now", [], "save it"))

    def test_praise_is_not_held_to_it(self):
        self.assertEqual(_unbacked("I wrote it for you, after all~ 🌸", [], "thats beautiful luna!"), "")

    def test_a_claimed_email_needs_a_send(self):
        nudge = _unbacked("I've sent it to you, Daddy~", [EDITED], "email me the story")
        self.assertIn("I've sent", nudge)
        self.assertIn("nothing this turn sent an email", nudge)

    def test_it_works_after_a_failed_run(self):
        nudge = _unbacked("Ran it, works perfectly now~", [EDITED, RAN_AND_FAILED], "test it")
        self.assertIn("the last run_command failed (exited with code 1)", nudge)

    def test_owning_up_is_fine(self):
        self.assertEqual(_unbacked("It crashed with a traceback when I ran it - curses needs a "
                                   "real terminal. Can you try it?", [EDITED, RAN_AND_FAILED], "test it"), "")

    def test_a_failed_run_fixed_later(self):
        self.assertEqual(_unbacked("Fixed, it works now.", [RAN_AND_FAILED, EDITED, dict(RAN_AND_FAILED, result=RAN_OK["result"])], "fix"), "")


if __name__ == "__main__":
    unittest.main()
