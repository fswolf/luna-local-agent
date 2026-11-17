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

    def test_what_shares_the_card(self):
        both = ("embeddings", "reranker")
        # a 12 GB card with the voice on it and both recall models (the first fresh install):
        # the 9B Q6 stays, the recall models go to the CPU rather than cost her a size
        m, side_on_gpu = install.plan(12.0, both, voice_gpu=True)
        self.assertEqual((m[0], side_on_gpu), ("9b-q6", False))
        # room for everything: they stay on the card
        self.assertEqual(install.plan(16.0, both)[0][0], "9b")
        self.assertTrue(install.plan(16.0, both)[1])
        self.assertTrue(install.plan(24.0, ("embeddings",), voice_gpu=True)[1])
        # the voice on the card can move her down a size
        self.assertEqual(install.plan(14.0)[0][0], "9b")
        self.assertEqual(install.plan(14.0, voice_gpu=True)[0][0], "9b-q6")
        # nothing extra: the plain tiers
        self.assertEqual(install.plan(12.0), (install.pick_model(12.0), True))
        # a model picked by hand: the recall models fit around it or go to the CPU
        self.assertFalse(install.plan(12.0, both, m=install._model_by_key("9b-q6"))[1])
        self.assertTrue(install.plan(12.0, both, m=install._model_by_key("9b-q4"))[1])

    def test_a_tight_card_gets_a_smaller_batch_and_cpu_recall(self):
        tmp = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(tmp, "llama", "models"))
            m = install.variant(install._model_by_key("9b-q6"))
            for f in (m[3], m[5]):
                open(os.path.join(tmp, "llama", "models", f), "w").close()
            state = {"backend": "llama", "extras": ["embeddings", "reranker"], "voice": {"device": "cuda"}}
            args = mock.Mock(model="auto", standard=False, yes=True)
            with mock.patch.object(install, "ROOT", tmp), mock.patch.object(install, "ARGS", args), \
                    mock.patch.object(install, "download") as download, \
                    mock.patch.object(install, "detect_vram", return_value=(12.0, "test")):
                install.model(state)
            download.assert_not_called()
            with open(os.path.join(tmp, "llama", "server.local.env"), encoding="utf-8") as f:
                text = f.read()
            self.assertIn(m[3], text)
            for line in ("EMBED_NGL=0", "RERANK_NGL=0", "UBATCH=512"):
                self.assertIn(line, text)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

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

    def test_an_older_install_keeps_its_model(self):
        # set up before the uncensored choice existed: a model, no flavour
        tmp = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(tmp, "llama", "models"))
            m = install._model_by_key("9b")
            open(os.path.join(tmp, "llama", "models", m[3]), "w").close()      # Qwen's own file is there
            state = {"model": "9b", "backend": "llama"}
            args = mock.Mock(model="auto", standard=False, yes=True)
            with mock.patch.object(install, "ROOT", tmp), mock.patch.object(install, "ARGS", args), \
                    mock.patch.object(install, "download") as download, \
                    mock.patch.object(install, "detect_vram", return_value=(16.0, "test")):
                install.model(state)
            download.assert_not_called()
            self.assertEqual(state["flavour"], "standard")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

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
                mock.patch.object(install, "linux_graphics", return_value=(16.0, "AMD")):
            self.assertEqual(install.detect_vram(), (16.0, "AMD"))


class LinuxGraphics(unittest.TestCase):
    """installer.linux_graphics against a made-up /sys/class/drm."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.drm = os.path.join(self.tmp, "drm")
        self.meminfo = os.path.join(self.tmp, "meminfo")
        self.ram(32)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def ram(self, gb):
        with open(self.meminfo, "w") as f:
            f.write(f"MemTotal:       {gb << 20} kB\nMemFree: 1 kB\n")

    def card(self, name, driver, vram=None, gtt=None):
        dev = os.path.join(self.drm, name, "device")
        os.makedirs(dev)
        os.makedirs(os.path.join(self.tmp, "drivers", driver), exist_ok=True)
        os.symlink(os.path.join(self.tmp, "drivers", driver), os.path.join(dev, "driver"))
        for file, gb in (("mem_info_vram_total", vram), ("mem_info_gtt_total", gtt)):
            if gb is not None:
                with open(os.path.join(dev, file), "w") as f:
                    f.write(str(int(gb * (1 << 30))))

    def read(self):
        return install.linux_graphics(self.drm, self.meminfo)

    def test_a_graphics_card(self):
        self.card("card1", "amdgpu", vram=20, gtt=16)
        self.assertEqual(self.read(), (20.0, "AMD"))

    def test_amd_integrated_shares_ram(self):
        self.card("card0", "amdgpu", vram=0.5, gtt=15.5)       # the BIOS's slice, and the shared window
        os.makedirs(os.path.join(self.drm, "card0-HDMI-A-1", "device"))   # a connector, skipped
        gb, what = self.read()
        self.assertEqual(gb, install.SHARED_CAP_GB)            # 15.5 shared, counted as 10: it's slow
        self.assertIn("AMD integrated graphics, sharing 15.5 of 32.0 GB", what)
        self.assertEqual(install.pick_model(gb)[0], "9b-q4")    # not the 4B any more

    def test_amd_integrated_no_vram_file(self):
        self.card("card0", "amdgpu")
        self.ram(16)
        self.assertEqual(self.read(), (8.0, "AMD integrated graphics, sharing 8.0 of 16.0 GB of RAM"))

    def test_intel_integrated(self):
        self.card("card0", "i915")
        self.ram(8)
        gb, what = self.read()
        self.assertEqual(gb, 4.0)
        self.assertTrue(what.startswith("Intel integrated graphics"))

    def test_a_dedicated_card_wins_over_integrated(self):
        self.card("card0", "amdgpu", vram=0.5, gtt=15)
        self.card("card1", "amdgpu", vram=16)
        self.assertEqual(self.read(), (16.0, "AMD"))

    def test_nothing(self):
        os.makedirs(self.drm)
        self.assertEqual(self.read(), (0, "no graphics memory found"))


if __name__ == "__main__":
    unittest.main()
