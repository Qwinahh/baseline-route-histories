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


if __name__ == "__main__":
    unittest.main()
