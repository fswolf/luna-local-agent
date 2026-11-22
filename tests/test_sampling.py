"""Sampling settings per model (llm/prompts.py sampling_for): only for a model
with an entry, matched by part of its name, longest match, valid values only.

    python -m unittest discover tests        (from the repo folder)
"""
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: F401,E402  (first: no real servers)

from llm import prompts  # noqa: E402

QWEN = {"temperature": 1.0, "top_p": 0.95, "top_k": 20, "min_p": 0.0, "presence_penalty": 1.5}
LUNAS = "Qwen3.5-9B-The-Defiant-Fable-Uncnr-Heretic-NEO-MAX-MTP-Q8_0"


class PerModel(unittest.TestCase):
    def test_her_model_gets_qwens(self):
        self.assertEqual(prompts.sampling_for(LUNAS, {"qwen3.5": QWEN}), QWEN)

    def test_another_model_gets_nothing(self):
        self.assertEqual(prompts.sampling_for("gemma-4-12b-it", {"qwen3.5": QWEN}), {})
        self.assertEqual(prompts.sampling_for("", {"qwen3.5": QWEN}), {})

    def test_longest_name_wins(self):
        table = {"qwen3.5": QWEN, "Qwen3.5-9B": {"temperature": 0.7}}
        self.assertEqual(prompts.sampling_for(LUNAS, table), {"temperature": 0.7})

    def test_only_known_settings_in_range(self):
        table = {"qwen": {"temperature": "0.6", "top_k": 20.0, "seed": 4, "top_p": 7, "min_p": None,
                          "presence_penalty": True, "dry_multiplier": float("nan")}}
        self.assertEqual(prompts.sampling_for("qwen3.5", table), {"temperature": 0.6, "top_k": 20})

    def test_a_broken_table_is_nothing(self):
        for table in (None, [], "qwen", {"qwen": 5}, {"": QWEN}):
            self.assertEqual(prompts.sampling_for(LUNAS, table), {})

    def test_sent_with_the_request(self):
        with mock.patch.object(prompts, "GENERATION", {"max_tokens": 10, "sampling": {"qwen3.5": QWEN}}):
            params = prompts.build_generation_params(LUNAS)
            self.assertEqual(params["max_tokens"], 10)
            self.assertEqual(params["presence_penalty"], 1.5)
            self.assertNotIn("presence_penalty", prompts.build_generation_params("llama-3.3-8b"))

    def test_the_example_config_has_qwens_and_parses(self):
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(here, "config.example.json"), encoding="utf-8") as f:
            table = json.load(f)["generation"]["sampling"]
        self.assertEqual(prompts.sampling_for(LUNAS, table), QWEN)


class FromTheSettingsPage(unittest.TestCase):
    def test_checking_a_table(self):
        clean, problems = prompts.clean_sampling({" qwen3.5 ": {"temperature": "1", "top_k": 20.0}, "gemma": {}})
        self.assertEqual((clean, problems), ({"qwen3.5": {"temperature": 1.0, "top_k": 20}, "gemma": {}}, []))
        for table, says in (({"": {}}, "needs a model name"), ({"q": {"top_p": 3}}, "top_p has to be a number"),
                            ({"q": {"seed": 1}}, "no setting called"), ({"Q": {}, "q": {}}, "listed twice"),
                            ([], "isn't a table")):
            self.assertIn(says, " ".join(prompts.clean_sampling(table)[1]))

    def test_saved_to_config_and_used_at_once(self):
        import tempfile

        import config
        from web import settings_web

        path = os.path.join(tempfile.mkdtemp(), "config.json")
        with open(path, "w") as f:
            json.dump({"generation": {"max_tokens": 10}}, f)
        saved = dict(config.settings)
        generation = dict(config.GENERATION)
        config.settings.clear()
        config.settings.update({"generation": {"max_tokens": 10}})
        try:
            with mock.patch.object(config, "CONFIG_FILE", path), mock.patch("ui.settings_pane._after"), \
                    mock.patch("core.lmstudio.model", LUNAS):
                ok, message = settings_web.sampling_save({"qwen3.5": QWEN})
                self.assertTrue(ok, message)
                with open(path) as f:
                    self.assertEqual(json.load(f)["generation"], {"max_tokens": 10, "sampling": {"qwen3.5": QWEN}})
                self.assertEqual(prompts.build_generation_params(LUNAS)["presence_penalty"], 1.5)   # no restart
                self.assertEqual(settings_web.sampling_panel()["uses"], "qwen3.5")
                self.assertFalse(settings_web.sampling_save({"qwen3.5": {"temperature": 9}})[0])
        finally:
            config.settings.clear()
            config.settings.update(saved)
            config.GENERATION.clear()
            config.GENERATION.update(generation)


if __name__ == "__main__":
    unittest.main()
