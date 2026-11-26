"""Scheduled jobs that run a script of yours (plugins/cron.py): the approved
text is pinned by hash, run by the scheduler, and refused once it changes."""
import json
import os
import tempfile
import unittest
from unittest import mock

from plugins import cron


class ScriptJobs(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = self.tmp.name
        self.scripts = os.path.join(root, "jobs")
        os.makedirs(self.scripts)
        self.marker = os.path.join(root, "ran")
        patches = [mock.patch.object(cron, "SCRIPTS_DIR", self.scripts),
                   mock.patch.object(cron, "JOBS_FILE", os.path.join(root, "cron.json")),
                   mock.patch.object(cron, "_jobs", []), mock.patch.object(cron, "_skipped", []),
                   mock.patch.object(cron, "_away")]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)
        self.write("copy.sh", f"echo copied 3\ntouch {self.marker}\n")

    def write(self, name, text):
        with open(os.path.join(self.scripts, name), "w") as f:
            f.write(text)

    def schedule(self, approve=True, script="copy.sh"):
        shown = {}

        def ask(title, body, note, timeout):
            shown["body"] = body
            return approve

        with mock.patch("ui.ask_approval", side_effect=ask):
            said = cron._schedule_job("nas", "0 4 * * 0", "say if anything failed", False, script)
        return said, shown.get("body", [])

    def fire(self):
        job = cron._jobs[0]
        job["_busy"] = True
        with mock.patch("core.assistant.respond_to_job", return_value="All good.") as respond:
            cron._fire(job)
        return respond.call_args[0][0]

    def test_the_popup_shows_the_whole_script_and_pins_it(self):
        said, body = self.schedule()
        self.assertIn("Scheduled nas", said)
        self.assertIn(f"touch {self.marker}", body)
        with open(cron.JOBS_FILE) as f:
            saved = json.load(f)[0]
        self.assertEqual(saved["script"], "copy.sh")
        self.assertEqual(len(saved["script_sha256"]), 64)

    def test_denied_is_not_scheduled(self):
        said, _ = self.schedule(approve=False)
        self.assertIn("Denied", said)
        self.assertEqual(cron._jobs, [])

    def test_an_approved_script_runs_and_she_gets_its_output(self):
        self.schedule()
        prompt = self.fire()
        self.assertTrue(os.path.exists(self.marker))
        self.assertIn("copied 3", prompt)
        self.assertIn("exit code 0", prompt)
        self.assertIn("untrusted", prompt)
        self.assertIn("Do it now: say if anything failed", prompt)

    def test_a_changed_script_does_not_run(self):
        self.schedule()
        self.write("copy.sh", f"touch {self.marker}\necho something else\n")
        prompt = self.fire()
        self.assertFalse(os.path.exists(self.marker))
        self.assertIn("did NOT run", prompt)
        self.assertIn("changed since it was approved", prompt)
        self.assertNotIn("Do it now", prompt)

    def test_a_hand_written_job_waits_for_approval(self):
        cron._jobs.append(cron._job({"name": "nas", "schedule": "0 4 * * 0", "task": "x", "script": "copy.sh"}))
        prompt = self.fire()
        self.assertFalse(os.path.exists(self.marker))
        self.assertIn("hasn't been approved", prompt)
        self.assertIn("hasn't been approved", cron.status())

    def test_approving_again_pins_the_new_text(self):
        self.schedule()
        self.write("copy.sh", f"echo v2\ntouch {self.marker}\n")
        with mock.patch("ui.ask_approval", return_value=True) as ask:
            said = cron._approve_job_script("nas")
        self.assertIn("Approved", said)
        self.assertIn("echo v2", ask.call_args.kwargs["body"])
        self.assertIn("v2", self.fire())
        self.assertTrue(os.path.exists(self.marker))
        self.assertIn("approved", cron.status())

    def test_approving_unchanged_asks_nothing(self):
        self.schedule()
        with mock.patch("ui.ask_approval") as ask:
            self.assertIn("already approved", cron._approve_job_script("nas"))
        ask.assert_not_called()

    def test_only_plain_files_in_the_jobs_folder(self):
        for bad in ("../cron.json", "sub/x.sh", ".hidden", ""):
            with self.assertRaises(ValueError):
                cron._script_text(bad)
        with self.assertRaises(ValueError):
            cron._script_text("missing.sh")
        os.symlink("/bin/true", os.path.join(self.scripts, "link.sh"))
        with self.assertRaises(ValueError):
            cron._script_text("link.sh")
        self.write("big.sh", "#" * (cron.MAX_SCRIPT_BYTES + 1))
        with self.assertRaises(ValueError):
            cron._script_text("big.sh")
        said, _ = self.schedule(script="../cron.json")
        self.assertIn("Not scheduled", said)

    def test_a_script_that_runs_too_long_is_stopped(self):
        with mock.patch("config.plugin_settings", return_value={"script_timeout": 10}), \
                mock.patch.object(cron.subprocess.Popen, "communicate",
                                  side_effect=[cron.subprocess.TimeoutExpired("bash", 10), (b"partial", None)]), \
                mock.patch.object(cron.os, "killpg") as kill:
            status, text = cron._run_script("copy.sh", b"sleep 100\n")
        self.assertIn("stopped after 10s", status)
        self.assertEqual(text, "partial")
        kill.assert_called_once()

    def test_a_stuck_child_never_hangs_the_scheduler(self):
        with mock.patch("config.plugin_settings", return_value={"script_timeout": 10}), \
                mock.patch.object(cron.subprocess.Popen, "communicate",
                                  side_effect=[cron.subprocess.TimeoutExpired("bash", 10),
                                               cron.subprocess.TimeoutExpired("bash", 10)]), \
                mock.patch.object(cron.subprocess.Popen, "kill") as kill, mock.patch.object(cron.os, "killpg"):
            status, text = cron._run_script("copy.sh", b"sleep 100\n")
        self.assertIn("stopped after 10s", status)
        self.assertEqual(text, "")
        kill.assert_called_once()

    def test_the_script_result_is_kept_even_when_her_turn_fails(self):
        self.schedule()
        job = cron._jobs[0]
        job["_busy"] = True
        with mock.patch("core.assistant.respond_to_job", side_effect=RuntimeError("model gone")):
            cron._fire(job)
        self.assertIn("[script exit code 0", cron._last["nas"][1])
        self.assertIn("script exit code 0", cron._away.call_args[0][0])

    def test_long_output_keeps_the_end(self):
        status, text = cron._run_script("copy.sh", b"seq 1 5000\n")
        self.assertIn("exit code 0", status)
        self.assertTrue(text.startswith("(the start is cut)"))
        self.assertTrue(text.endswith("5000"))

    def test_jobs_cant_approve_scripts(self):
        with mock.patch("config.plugin_settings", return_value={"job_tools": ["approve_job_script", "read_file"]}):
            self.assertEqual(cron._tools(), ["read_file"])


if __name__ == "__main__":
    unittest.main()
