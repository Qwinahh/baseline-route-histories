"""Grouping changes navigation only; measured routes never populate a different service."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_site


@unittest.skipUnless(shutil.which("node"), "node unavailable")
class ModelNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.temp.name) / "dist"
        cls.data = build_site.build(cls.out)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def page(self, suffix):
        result = subprocess.run(["node", str(ROOT / "tests/render_page.js"), str(self.out), suffix],
                                capture_output=True, encoding="utf-8", check=True)
        return json.loads(result.stdout)

    def test_canonical_model_and_old_measured_link_show_same_single_graph(self):
        for canonical, hosted in [("anthropic-api.claude-sonnet-5-5", "puter.claude-sonnet-5-5"),
                                  ("openai-api.gpt-6.1-sol", "puter.gpt-6.1-sol"),
                                  ("xai-api.grok-4.7", "puter.x-ai-grok-4.7")]:
            with self.subTest(model=canonical):
                new = self.page("#model/" + canonical)
                old = self.page("#model/" + hosted)
                self.assertEqual(new["dailyCharts"], 1)
                self.assertEqual(new["aria"], old["aria"])
                self.assertEqual(new["selectedService"], hosted)
                self.assertEqual(set(new["serviceOptions"]), {canonical, hosted})
                self.assertIn("model identity unverified", new["text"])
                direct = self.page(f"#model/{canonical}?service={canonical}")
                self.assertEqual(direct["dailyCharts"], 0)
                self.assertIn("No Baseline test history yet.", direct["text"])

    def test_search_has_one_result_and_access_filter_keeps_route_scope(self):
        page = self.page("#models?q=claude-sonnet-5-5")
        self.assertEqual(len(page["modelRows"]), 1)
        self.assertIn("service=puter.claude-sonnet-5-5", page["modelRows"][0]["href"])
        direct = self.page("#models?q=claude-sonnet-5-5&access=direct_api")
        self.assertEqual(len(direct["modelRows"]), 1)
        self.assertIn("service=anthropic-api.claude-sonnet-5-5", direct["modelRows"][0]["href"])
        self.assertIn("Not tested by Baseline", direct["text"])
        self.assertNotIn("Collecting baseline", direct["text"])

    def test_apps_are_not_given_api_graphs(self):
        for app in ("anthropic-app.claude", "openai-app.chatgpt", "google-app.gemini"):
            self.assertEqual(self.page("#model/" + app)["dailyCharts"], 0)
