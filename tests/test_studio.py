"""The studio (./studio.sh, studio.cmd, portrait/viewer/view.py): it stops when
no page is watching, which needs the live feed to notice a page closing."""
import socket
import types
import unittest

from tests.offline import FAKE  # noqa: F401  (first: no real servers)

from web import livefeed


class ClosedPage(unittest.TestCase):
    def gone(self, conn):
        return livefeed._Handler._gone(types.SimpleNamespace(connection=conn))

    def test_open_then_closed(self):
        a, b = socket.socketpair()
        try:
            self.assertFalse(self.gone(a))      # open and quiet: still watching
            b.close()
            self.assertTrue(self.gone(a))       # the page closed its end
        finally:
            a.close()

    def test_already_closed(self):
        a, b = socket.socketpair()
        b.close()
        a.close()
        self.assertTrue(self.gone(a))

    def test_cant_peek_counts_as_open(self):
        class TLSish:
            def fileno(self):
                return a.fileno()

            def recv(self, n, flags=0):
                raise ValueError("non-zero flags not allowed")
        a, b = socket.socketpair()
        try:
            b.sendall(b"x")
            self.assertFalse(self.gone(TLSish()))
        finally:
            a.close()
            b.close()


if __name__ == "__main__":
    unittest.main()
