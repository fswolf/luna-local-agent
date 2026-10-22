"""The installer's model pick (installer/install.py): the biggest model that
fits the machine, written where llama/start.sh will find it.

    python -m unittest discover tests        (from the repo folder)
"""
import importlib.util
import os
import shutil
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("luna_installer", os.path.join(ROOT, "installer", "install.py"))
install = importlib.util.module_from_spec(spec)
spec.loader.exec_module(install)


class Pick(unittest.TestCase):
    def test_tiers(self):
        expect = {0: "4b-q4", 4: "4b-q4", 6: "4b", 8: "9b-q4", 12: "9b-q6", 16: "9b", 24: "27b", 32: "27b-q6"}
        for vram, key in expect.items():
            self.assertEqual(install.pick_model(vram)[0], key, f"{vram} GB")

    def test_every_pick_fits_with_room(self):
        for m in install.MODELS:
            if m[6]:
                # the model, its eyes and its context fit in the memory it asks for
                self.assertLessEqual(m[4] + (1.0 if m[5] else 0) + 1.0, m[6], m[0])

    def test_table_is_well_formed(self):
        least = [m[6] for m in install.MODELS]
        self.assertEqual(least, sorted(least, reverse=True))
        for key, label, repo, file, size, mmproj, _least, ctx, lms in install.MODELS:
            self.assertTrue(file.endswith(".gguf") and repo.count("/") == 1, key)
            self.assertTrue(not mmproj or mmproj.startswith("mmproj-"), key)
            self.assertIn("@", lms)
            self.assertGreaterEqual(ctx, 8192)

    def test_uncensored_is_the_default_and_matches_the_tiers(self):
        for m in install.MODELS:
            u = install.variant(m)
            self.assertIn("uncensored", u[1])
            self.assertIn("abliterated", u[3])
            self.assertEqual((u[0], u[6], u[7]), (m[0], m[6], m[7]))          # same size tier, memory, context
            self.assertTrue(u[3].endswith(".gguf") and u[2].count("/") == 1)
            self.assertEqual(bool(u[5]), bool(m[5]), m[0])                     # eyes where the standard has them
            self.assertTrue(abs(u[4] - m[4]) < 2.5, m[0])                       # about the same download
            self.assertLessEqual(u[4] + (1.0 if u[5] else 0) + 1.0, m[6] or 99, m[0])
            self.assertTrue(u[8].startswith(u[2] + "@"))
            self.assertIs(install.variant(m, uncensored=False), m)

    def test_local_env_is_written_for_start_sh(self):
        tmp = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(tmp, "llama"))
            with mock.patch.object(install, "ROOT", tmp):
                path = install._write_local_env({"MODEL": "/m/a b.gguf", "MMPROJ": "off", "CTX": 16384})
            with open(path) as f:
                text = f.read()
            self.assertIn('MODEL="/m/a b.gguf"', text)
            self.assertIn("CTX=16384", text)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_amd_vram_from_sysfs(self):
        with mock.patch.object(install, "SYSTEM", "Linux"), mock.patch.object(install.shutil, "which", return_value=None), \
                mock.patch("glob.glob", return_value=["/x"]), \
                mock.patch("builtins.open", mock.mock_open(read_data=str(16 << 30))):
            self.assertEqual(install.detect_vram(), (16.0, "AMD"))


if __name__ == "__main__":
    unittest.main()
