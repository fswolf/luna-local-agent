"""Reading a page asks like a browser (mind/webpage.py), and a page that
won't open points her at the other search results, not a made-up address
(tools/web.py).

    python -m unittest discover tests        (from the repo folder)
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: F401,E402  (first: no real servers)

from mind import webpage  # noqa: E402


class BrowserHeaders(unittest.TestCase):
    def test_sent_like_a_browser(self):
        response = mock.Mock(is_redirect=False)
        with mock.patch.object(webpage, "_local_reason", return_value=""), \
                mock.patch.object(webpage.requests, "get", return_value=response) as get:
            webpage._get("https://example.com/")
        sent = get.call_args.kwargs["headers"]
        self.assertIn("*/*", sent["Accept"])                 # no */* got 406s
        self.assertTrue(sent["Accept-Language"])
        self.assertIn("Chrome/", sent["User-Agent"])


class RefusedPage(unittest.TestCase):
    def test_points_at_the_other_results(self):
        from tools import web

        with mock.patch.object(web, "_may_send", return_value=True), \
                mock.patch.object(web.webpage, "fetch", return_value=(None, "the site answered 406")):
            out = web._read_page("https://example.com/story")
        self.assertIn("406", out)
        self.assertIn("other pages", out)
        self.assertIn("never make up an address", out)


if __name__ == "__main__":
    unittest.main()
