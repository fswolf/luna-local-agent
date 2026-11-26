"""find_device and scan_network (tools/network.py): names from mDNS, hostnames
as given, and ".local" not counted as part of a name."""
import os
import struct
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: E402,F401  (first: no real servers)

from tools import network  # noqa: E402

TABLE = {"192.168.0.1": "dc:62:79:c7:60:b0", "192.168.0.98": "aa:bb:cc:dd:ee:01", "192.168.0.82": "aa:bb:cc:dd:ee:02"}


def reply(qid, ip, name, pointer=True):
    """An mDNS answer to our PTR question, the way avahi writes one (the answer's
    name points back at the question's)."""
    q = network._ptr_query(ip, qid)
    question = q[12:]
    target = b"".join(bytes([len(p)]) + p.encode() for p in name.split(".")) + b"\x00"
    owner = b"\xc0\x0c" if pointer else question[:-4]
    return (struct.pack(">HHHHHH", qid, 0x8400, 1, 1, 0, 0) + question
            + owner + struct.pack(">HHIH", 12, 0x8001, 120, len(target)) + target)


class Packets(unittest.TestCase):
    def test_reads_an_answer(self):
        for pointer in (True, False):
            self.assertEqual(network._ptr_answer(reply(7, "192.168.0.98", "UnraidTower.local", pointer), 7),
                             "UnraidTower.local")

    def test_ignores_someone_elses_answer_and_junk(self):
        self.assertEqual(network._ptr_answer(reply(7, "192.168.0.98", "x.local"), 8), "")
        for junk in (b"", b"\x00\x07", b"\x00\x07\x84\x00\x00\x01\x00\x01\xc0", b"\xff" * 40):
            self.assertEqual(network._ptr_answer(junk, 7), "")

    def test_a_pointer_loop_ends(self):
        packet = struct.pack(">HHHHHH", 7, 0x8400, 0, 1, 0, 0) + b"\xc0\x0c" + struct.pack(">HHIH", 12, 1, 1, 2) + b"\xc0\x0c"
        self.assertEqual(network._ptr_answer(packet, 7), "")


class Finding(unittest.TestCase):
    def setUp(self):
        network._last.update(at=0.0, found={})
        for p in (mock.patch.object(network, "_my_ip", return_value="192.168.0.40"),
                  mock.patch.object(network, "_wake"),
                  mock.patch.object(network, "_neighbors", return_value=dict(TABLE)),
                  mock.patch.object(network, "_reverse", return_value={"192.168.0.1": "_gateway",
                                                                       "192.168.0.40": "MewNix"}),
                  mock.patch.object(network, "_mdns_names", return_value={"192.168.0.98": "UnraidTower.local"}),
                  mock.patch.object(network, "_remembered", return_value=[])):
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(lambda: network._last.update(at=0.0, found={}))

    def test_the_scan_has_the_name_it_gives_itself(self):
        out = network._scan_network()
        self.assertIn("192.168.0.98  UnraidTower.local", out)
        self.assertIn("192.168.0.1  _gateway", out)

    def test_unraid_local_finds_unraidtower(self):
        resolved = []

        def resolve(name):
            resolved.append(name)
            return {}
        with mock.patch.object(network, "_resolve", side_effect=resolve):
            out = network._find_device("unraid.local")
        self.assertIn("192.168.0.98  UnraidTower.local", out)
        self.assertEqual(resolved[0], "unraid.local")          # tried as the hostname it is first
        self.assertNotIn("local", resolved[1:])                 # and "local" alone is never a guess

    def test_a_hostname_keeps_its_dots(self):
        seen = []
        with mock.patch("socket.getaddrinfo", side_effect=lambda h, *a: seen.append(h) or []):
            network._resolve("UnraidTower.local")
        self.assertEqual(seen, ["unraidtower.local"])

    def test_a_name_that_is_not_there(self):
        with mock.patch.object(network, "_resolve", return_value={}):
            self.assertIn("Nothing on the network calls itself 'jellyfin'", network._find_device("jellyfin"))


if __name__ == "__main__":
    unittest.main()
