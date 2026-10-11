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

    def test_canonical_links_explain_and_link_to_the_measured_route(self):
        """9 October 2026: an untested canonical route never shows another service's results; it says so and links
        to the tested route, whose page shows the single graph."""
        for canonical, hosted in [("anthropic-api.claude-sonnet-5-5", "puter.claude-sonnet-5-5"),
                                  ("openai-api.gpt-6.1-sol", "puter.gpt-6.1-sol"),
                                  ("xai-api.grok-4.7", "puter.x-ai-grok-4.7")]:
            with self.subTest(model=canonical):
                new = self.page("#model/" + canonical)
                self.assertEqual(new["dailyCharts"], 0)
                self.assertIn("Not tested by Baseline", new["text"])
                self.assertIn("Third-party host (Puter)", new["text"])                 # the explicit link
                old = self.page("#model/" + hosted)
                via_group = self.page(f"#model/{canonical}?service={hosted}")
                self.assertEqual(old["dailyCharts"], 1)
                self.assertEqual(via_group["aria"], old["aria"])
                self.assertIn("model identity not confirmed", old["text"])

    def test_search_has_one_result_on_its_measured_route(self):
        page = self.page("#models?q=claude-sonnet-5-5")
        self.assertEqual(len(page["modelRows"]), 1)
        self.assertIn("service=puter.claude-sonnet-5-5", page["modelRows"][0]["href"])
        old_filter = self.page("#models?q=claude-sonnet-5-5&access=direct_api")   # a retired filter is ignored
        self.assertEqual(old_filter["modelRows"], page["modelRows"])

    def test_apps_are_not_given_api_graphs(self):
        for app in ("anthropic-app.claude", "openai-app.chatgpt", "google-app.gemini"):
            self.assertEqual(self.page("#model/" + app)["dailyCharts"], 0)
