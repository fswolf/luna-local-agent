"""llama.cpp's ready-made release (installer/install.py --prebuilt): the
right file for the machine, unpacked into server/llama/bin, a build of your
own left alone. No download: a stand-in archive.

    python -m unittest discover tests        (from the repo folder)
"""
import importlib.util
import io
import os
import tarfile
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("luna_installer_prebuilt", os.path.join(ROOT, "installer", "install.py"))
install = importlib.util.module_from_spec(spec)
spec.loader.exec_module(install)


def fake_release(dest, top="llama-b100"):
    with tarfile.open(dest, "w:gz") as t:
        for name in ("llama-server", "libllama.so"):
            data = b"x"
            info = tarfile.TarInfo(f"{top}/{name}")
            info.size, info.mode = len(data), 0o755
            t.addfile(info, io.BytesIO(data))
    return True


class Asset(unittest.TestCase):
    def test_per_machine(self):
        cases = {("Linux", "x86_64"): "llama-b1-bin-ubuntu-vulkan-x64.tar.gz",
                 ("Linux", "aarch64"): "llama-b1-bin-ubuntu-vulkan-arm64.tar.gz",
                 ("Darwin", "arm64"): "llama-b1-bin-macos-arm64.tar.gz",
                 ("Darwin", "x86_64"): "llama-b1-bin-macos-x64.tar.gz",
                 ("Windows", "AMD64"): None, ("Linux", "riscv64"): None}
        for (system, machine), want in cases.items():
            with mock.patch.object(install, "SYSTEM", system), mock.patch.object(install.platform, "machine",
                                                                                 return_value=machine):
                self.assertEqual(install.llama_asset("b1"), want, (system, machine))

    def test_a_pinned_release(self):
        with mock.patch.dict(os.environ, {"LUNA_LLAMA_TAG": "b12397"}):
            self.assertEqual(install.latest_llama_tag(), "b12397")
        with mock.patch.dict(os.environ, {"LUNA_LLAMA_TAG": "latest; rm -rf"}):
            self.assertIsNone(install.latest_llama_tag())


class Unpack(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "server", "llama"))
        self.bin = os.path.join(self.root, "server", "llama", "bin")
        self.p = [mock.patch.object(install, "ROOT", self.root), mock.patch.object(install, "SYSTEM", "Linux"),
                  mock.patch.object(install.platform, "machine", return_value="x86_64"),
                  mock.patch.object(install, "latest_llama_tag", return_value="b100"),
                  mock.patch("builtins.print")]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()

    def test_into_bin_and_marked(self):
        with mock.patch.object(install, "download", side_effect=lambda url, dest: fake_release(dest)) as dl:
            self.assertTrue(install.prebuilt_llama())
        self.assertIn("/b100/llama-b100-bin-ubuntu-vulkan-x64.tar.gz", dl.call_args[0][0])
        self.assertEqual(sorted(os.listdir(self.bin)), [".release", "libllama.so", "llama-server"])
        with open(os.path.join(self.bin, ".release")) as f:
            self.assertEqual(f.read().strip(), "b100")
        self.assertEqual([d for d in os.listdir(os.path.dirname(self.bin)) if d.startswith("luna-llama-")], [])
        with mock.patch.object(install, "download") as again:         # the same release: nothing to fetch
            self.assertTrue(install.prebuilt_llama())
        again.assert_not_called()

    def test_your_own_build_is_kept(self):
        os.makedirs(self.bin)
        open(os.path.join(self.bin, "llama-server"), "w").close()
        with mock.patch.object(install, "download") as dl:
            self.assertTrue(install.prebuilt_llama())
        dl.assert_not_called()

    def test_an_odd_archive_is_refused(self):
        with mock.patch.object(install, "download", side_effect=lambda url, dest: fake_release(dest, top="")):
            self.assertFalse(install.prebuilt_llama())
        self.assertFalse(os.path.exists(self.bin))


if __name__ == "__main__":
    unittest.main()
