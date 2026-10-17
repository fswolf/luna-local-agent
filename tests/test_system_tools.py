"""system_health and last_boot: reading the journal and saying what it
means. No real journal: _run is faked with what journalctl, systemctl
and coredumpctl print.

    python -m unittest discover tests        (from the repo folder)
"""
import json
import os
import sys
import unittest
from unittest import mock

# The repo on the path, so this also runs on its own: python tests/<this file>
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: E402,F401  (first: no real servers)

from tools import system  # noqa: E402

T0 = 1_792_000_000_000_000          # microseconds


def entry(msg, who="kwin", t=0, kernel=False):
    e = {"MESSAGE": msg, "__REALTIME_TIMESTAMP": str(T0 + t * 1_000_000)}
    if kernel:
        e["_TRANSPORT"] = "kernel"
    else:
        e["SYSLOG_IDENTIFIER"] = who
    return json.dumps(e)


def fake(journal=None, errors=None, failed="", boots=None, dumps=None):
    """A _run that answers like the real tools would."""
    def run(args):
        if args[0] == "systemctl":
            return 0, failed if "--user" not in args else ""
        if args[0] == "coredumpctl":
            return (0, json.dumps(dumps)) if dumps is not None else (1, "")
        if "--list-boots" in args:
            return (0, json.dumps(boots)) if boots is not None else (1, "")
        lines = errors if "err" in args else journal
        return (0, "\n".join(lines)) if lines is not None else (1, "")
    return run


class LastBoot(unittest.TestCase):
    def go(self, **kw):
        with mock.patch.object(system, "_run", side_effect=fake(**kw)), \
                mock.patch.object(system, "_journal_scope", return_value=""):
            return system.last_boot()

    def test_a_freeze_with_a_gpu_hang(self):
        out = self.go(journal=[entry("Started session", t=1),
                               entry("amdgpu 0000:03:00.0: amdgpu: ring gfx_0.0.0 timeout", kernel=True, t=2)],
                      errors=[entry("amdgpu: GPU reset begin!", kernel=True, t=2)],
                      boots=[{"index": -1, "first_entry": T0 - 3_600_000_000, "last_entry": T0 + 2_000_000}],
                      dumps=[{"time": T0 + 1_000_000, "exe": "/usr/bin/kwin_wayland", "sig": 6},
                             {"time": T0 - 99 * 3_600_000_000, "exe": "/usr/bin/old", "sig": 11}])
        self.assertIn("ended abruptly", out)
        self.assertIn("the GPU hung", out)
        self.assertIn("kwin_wayland (signal 6)", out)
        self.assertNotIn("old (signal", out)              # a crash from another boot
        self.assertIn("outside content", out)

    def test_a_normal_shutdown(self):
        out = self.go(journal=[entry("Stopping things", t=1),
                               entry("Reached target System Power-Off.", who="systemd", t=2)],
                      errors=[])
        self.assertIn("normal shutdown", out)
        self.assertNotIn("abruptly", out)

    def test_a_freeze_that_left_nothing(self):
        out = self.go(journal=[entry("just music playing", t=1)], errors=[])
        self.assertIn("ended abruptly", out)
        self.assertIn("Nothing in the log says why", out)

    def test_no_journal(self):
        self.assertIn("can't be read", self.go())

    def test_log_text_is_cut_to_plain_short_lines(self):
        out = self.go(journal=[entry("bad\x1b[31m colour‮ and " + "x" * 400, t=1)], errors=[])
        line = next(ln for ln in out.splitlines() if "colour" in ln)
        self.assertNotIn("\x1b", line)
        self.assertNotIn("‮", line)
        self.assertLess(len(line), 230)


class Health(unittest.TestCase):
    def test_failed_services_and_errors_by_program(self):
        errors = [entry("oops one", who="kokoro", t=1), entry("oops two", who="kokoro", t=2),
                  entry("Out of memory: Killed process 1234 (llama-server)", kernel=True, t=3)]
        with mock.patch.object(system, "_run", side_effect=fake(errors=errors, failed="kokoro.service loaded failed failed Kokoro\n")), \
                mock.patch.object(system, "_journal_scope", return_value=""):
            out = system.health()
        self.assertTrue(out.startswith("Needs a look:"))
        self.assertIn("kokoro.service", out)
        self.assertIn("kokoro x2", out)
        self.assertIn("memory ran out", out)

    def test_all_quiet(self):
        with mock.patch.object(system, "_run", side_effect=fake(errors=[])), \
                mock.patch.object(system, "_disks", return_value=[("/", 500, 1000, 50)]), \
                mock.patch.object(system, "_cpu_temp", return_value=50), \
                mock.patch.object(system.machine, "gpus", return_value=[]), \
                mock.patch.object(system.machine, "memory", return_value=(32, 20)), \
                mock.patch.object(system, "_load", return_value="Load: 1 1 1 on 16 threads"):
            out = system.health()
        self.assertTrue(out.startswith("Nothing looks wrong."), out)
        self.assertIn("Errors since boot: none", out)

    def test_in_the_system_group(self):
        import tools
        self.assertEqual(tools.group_of("last_boot"), "System")
        self.assertEqual(tools.group_of("system_status"), "System")


if __name__ == "__main__":
    unittest.main()
