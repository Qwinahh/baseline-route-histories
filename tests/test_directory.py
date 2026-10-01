"""Runs tests/test_directory.js (Node) so CI runs the directory's behavioural tests."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "node not available")
class DirectoryHelperTests(unittest.TestCase):
    def test_directory_helpers(self):
        result = subprocess.run(["node", str(ROOT / "tests" / "test_directory.js")], capture_output=True,
                                text=True, timeout=60, encoding="utf-8", errors="replace")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("all assertions passed", result.stdout)


@unittest.skipUnless(shutil.which("node"), "node not available")
class ResultsChartTests(unittest.TestCase):
    """Runs tests/test_results_chart.js against daily series built from the labelled graph fixtures (T13)."""

    def test_results_chart_layout(self):
        import importlib
        import json
        import sys
        import tempfile
        sys.path.insert(0, str(ROOT / "scripts"))
        own_results = importlib.import_module("own_results")
        entries = json.loads((ROOT / "catalog" / "models.json").read_text(encoding="utf-8"))["entries"]
        graph = ROOT / "tests" / "fixtures" / "own_results" / "graph"

        def series(*names):
            dataset = own_results.empty_dataset()
            for i, name in enumerate(names):
                bundle = json.loads((graph / name).read_text(encoding="utf-8"))
                dataset = own_results.merge(dataset, bundle, {"sha256": f"{i:064x}", "reviewed_at": "2026-10-13T00:00:00Z"})
            return own_results.site_tests(dataset, entries)["entries"]["google-api.gemini-3.5-flash-lite"]["daily_series"]
        views = {"several-points": series("several-points.json"), "schedule-only": series("schedule-only.json"),
                 "one-point": series("one-point.json"), "two-setups": series("several-points.json", "second-setup.json"),
                 "open-day": series("open-day.json")}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "views.json"
            path.write_text(json.dumps(views), encoding="utf-8")
            result = subprocess.run(["node", str(ROOT / "tests" / "test_results_chart.js"), str(path)],
                                    capture_output=True, text=True, timeout=60, encoding="utf-8", errors="replace")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("all assertions passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
