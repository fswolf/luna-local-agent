"""web_search.engines: named engines asked side by side, each result saying
which returned it (mind/websearch.py)."""
import sys
import types
import unittest
from unittest import mock

import config
from mind import websearch


def _fake_ddgs(by_engine, calls):
    class DDGS:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def text(self, query, max_results=None, backend="auto"):
            calls.append(backend)
            if backend == "auto":
                return [{"title": "A", "body": "a", "href": "https://a.example"}]
            if by_engine.get(backend) is None:
                raise RuntimeError("blocked")
            return by_engine[backend][:max_results]
    return types.SimpleNamespace(DDGS=DDGS)


def r(url):
    return {"title": url, "body": "about " + url, "href": url}


class Engines(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.by = {
            "mojeek": [r("https://one.example"), r("https://two.example/")],
            "brave": [r("https://two.example"), r("https://three.example")],
            "startpage": None,
        }
        self.mod = mock.patch.dict(sys.modules, {"ddgs": _fake_ddgs(self.by, self.calls)})
        self.mod.start()
        self.known = mock.patch.object(websearch, "known_engines",
                                       return_value=["brave", "mojeek", "startpage", "wikipedia"])
        self.known.start()

    def tearDown(self):
        self.mod.stop()
        self.known.stop()

    def search(self, engines, n=3):
        with mock.patch.object(config, "WEB_SEARCH_ENGINES", engines, create=True):
            return websearch.search("q", n), websearch.engines()

    def test_auto_is_one_call_without_labels(self):
        out, _ = self.search("auto")
        self.assertEqual(self.calls, ["auto"])
        self.assertNotIn("engines", out[0])

    def test_named_each_asked_and_labelled(self):
        out, _ = self.search("mojeek, brave")
        self.assertEqual(sorted(self.calls), ["brave", "mojeek"])
        urls = [x["href"] for x in out]
        # turns: mojeek 1, brave 1 (same page as mojeek 2), then brave 2
        self.assertEqual(urls, ["https://one.example", "https://two.example", "https://three.example"])
        self.assertEqual(out[1]["engines"], ["brave", "mojeek"])
        self.assertEqual(out[0]["engines"], ["mojeek"])

    def test_one_failing_engine_keeps_the_rest(self):
        out, _ = self.search("startpage,mojeek")
        self.assertEqual([x["engines"] for x in out], [["mojeek"], ["mojeek"]])

    def test_unknown_names_dropped_and_all_unknown_is_auto(self):
        self.search("yandex, brave")
        self.assertEqual(self.calls, ["brave"])
        self.calls.clear()
        self.search("yandex")
        self.assertEqual(self.calls, ["auto"])

    def test_she_reads_the_engines(self):
        out, _ = self.search("mojeek, brave, startpage")
        with mock.patch.object(config, "WEB_SEARCH_ENGINES", "mojeek, brave, startpage", create=True):
            text = websearch.format_results("q", out)
        self.assertIn("(https://two.example) [brave, mojeek]", text)
        self.assertIn("Searched mojeek, brave, startpage.", text)
        self.assertIn("No results from startpage.", text)

    def test_list_setting(self):
        with mock.patch.object(config, "WEB_SEARCH_ENGINES", ["Brave", "brave", " mojeek "], create=True):
            self.assertEqual(websearch.engines(), ["brave", "mojeek"])


if __name__ == "__main__":
    unittest.main()
