"""T05 release candidate: local refresh simulations, publication gate and templates.

Everything runs on temporary copies of registry/ and evidence/ with a stub upstream;
nothing touches the network or the real registry. These simulations show the local
logic only: they do not prove that a hosted or scheduled run would succeed."""
from datetime import datetime, timedelta, timezone
import contextlib
import hashlib
import importlib
import io
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
refresh = importlib.import_module("refresh")
release_check = importlib.import_module("release_check")
build_site = importlib.import_module("build_site")
registry = importlib.import_module("registry")

# Expected values are derived from the current, validated registry rather than frozen,
# so ordinary evidence growth never breaks the publication suite (review T05 R2).
RECORDS, _LOAD_ERRORS = registry.load_registry(ROOT / "registry")
SOURCE = next(s for s in RECORDS["sources"] if s["id"] == "aider-polyglot")
REVISION = SOURCE["revision"]
SNAPSHOT = ROOT / "evidence" / "snapshots" / "aider-polyglot" / REVISION


def _latest_timestamp(records) -> datetime:
    stamps = [SOURCE["retrieved_at"], SOURCE["last_successful_check"]]
    stamps += [o["retrieved_at"] for o in records["observations"]]
    stamps += [r["finished_at"] for r in records["ingestion_runs"]]
    stamps += [c["recorded_at"] for c in records["corrections"]]
    return max(registry.parse_utc(t) for t in stamps if t)


# Simulated clocks: the day after the latest recorded timestamp, so they stay later
# than every retrieval and check time however the registry grows.
_DAY = (_latest_timestamp(RECORDS) + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
MIDNIGHT_RUN = _DAY.replace(minute=17)
MORNING_RUN = _DAY.replace(hour=6, minute=17)
LATER = _DAY + timedelta(days=1)


def stamp(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def synthetic_row():
    """SYNTHETIC TEST ROW for temporary copies only. Its name, date and harness version
    are derived from the current registry, so it is always new and always a new series.
    Returns (row text, observed date)."""
    n = len(RECORDS["observations"])
    observed = (_DAY - timedelta(days=1)).date().isoformat()
    row = (f"\n- dirname: {observed}-00-00-00--synthetic-test-row-{n}\n"
           "  test_cases: 225\n  model: SYNTHETIC TEST ROW\n  edit_format: diff\n  commit_hash: abc1234\n"
           "  pass_rate_1: 10.0\n  pass_rate_2: 50.2\n  pass_num_1: 22\n  pass_num_2: 113\n"
           "  total_tests: 225\n  command: aider --model deepseek/deepseek-chat\n"
           f"  date: {observed}\n  versions: 99.{n}.0.synthetic\n")
    return row, observed


class Upstream:
    """Stub GitHub: serves one revision (the current one by default), or fails like an outage."""

    def __init__(self, revision=REVISION, data=None, fail=False):
        self.revision, self.fail = revision, fail
        self.data = data if data is not None else (SNAPSHOT / "polyglot_leaderboard.yml").read_bytes()
        self.calls = []

    def get(self, url, accept=None):
        self.calls.append(url)
        if self.fail:
            raise OSError("simulated network failure")
        if url.startswith("https://api.github.com/"):
            return self.revision.encode()
        if url.endswith("/LICENSE.txt"):
            return (SNAPSHOT / "LICENSE.txt").read_bytes()
        return self.data


def new_upstream():
    """Upstream serving the current snapshot plus a synthetic row, under a new revision
    derived from that content."""
    row, observed = synthetic_row()
    data = (SNAPSHOT / "polyglot_leaderboard.yml").read_bytes() + row.encode()
    return Upstream(hashlib.sha1(data).hexdigest(), data), observed


class Workspace:
    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.registry = base / "registry"
        self.evidence = base / "evidence" / "snapshots"
        self.out = base / "site-out"
        shutil.copytree(ROOT / "registry", self.registry)
        shutil.copytree(ROOT / "evidence" / "snapshots", self.evidence)

    def files(self):
        return {p.name: p.read_bytes() for p in self.registry.iterdir()}

    def snapshot_files(self):
        return sorted(p.relative_to(self.evidence).as_posix() for p in self.evidence.rglob("*") if p.is_file())

    def refresh(self, upstream, now):
        return refresh.refresh(self.registry, self.evidence, now=now, get=upstream.get)

    def release(self, now=LATER):
        return release_check.check_release(self.out, registry_dir=self.registry, evidence_root=self.evidence,
                                           generated_at=stamp(now), now=now)


class RefreshSimulationTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(_LOAD_ERRORS, [])
        self.ws = Workspace()
        self.addCleanup(self.ws.tmp.cleanup)
        self.before = self.ws.files()
        self.before_snapshots = self.ws.snapshot_files()
        self.count = len(RECORDS["observations"])

    def test_successful_refresh_with_new_upstream_data(self):
        upstream, observed = new_upstream()
        result = self.ws.refresh(upstream, MORNING_RUN)
        self.assertEqual((result["failed_runs"], result["registry_valid"]), ([], True))
        self.assertTrue(result["evidence_changed"])
        self.assertEqual((result["publish"], result["publish_reason"]), (True, "evidence_changed"))
        self.assertEqual(refresh.exit_code(result), 0)
        records, _ = registry.load_registry(self.ws.registry)
        self.assertEqual(len(records["observations"]), self.count + 1)
        new = records["observations"][-1]
        self.assertEqual((new["observed_at"], new["retrieved_at"]), (observed, stamp(MORNING_RUN)))
        # Earlier observations are byte-identical: new lines are appended only.
        after = self.ws.files()["observations.jsonl"]
        self.assertTrue(after.startswith(self.before["observations.jsonl"]))
        self.assertTrue(set(self.before_snapshots) < set(self.ws.snapshot_files()))
        self.assertIn(f"aider-polyglot/{upstream.revision}/LICENSE.txt", self.ws.snapshot_files())
        release = self.ws.release()
        self.assertTrue(release["ok"], release["problems"])
        self.assertEqual(release["observations"], self.count + 1)

    def test_no_op_refresh_changes_only_the_check_record(self):
        result = self.ws.refresh(Upstream(), MORNING_RUN)
        self.assertEqual((result["failed_runs"], result["evidence_changed"]), ([], False))
        self.assertEqual((result["publish"], result["publish_reason"]), (False, "none"))
        after = self.ws.files()
        for name in refresh.EVIDENCE_FILES:
            self.assertEqual(after[name], self.before[name], name)
        self.assertEqual(self.ws.snapshot_files(), self.before_snapshots)
        runs = after["ingestion_runs.jsonl"].decode().splitlines()
        self.assertEqual(len(runs), len(self.before["ingestion_runs.jsonl"].decode().splitlines()) + 1)
        self.assertEqual(json.loads(runs[-1])["status"], "succeeded")
        source = next(s for s in json.loads(after["sources.json"])["records"] if s["id"] == "aider-polyglot")
        self.assertEqual(source["last_successful_check"], stamp(MORNING_RUN))

    def test_first_run_of_the_day_republishes_the_check_time(self):
        result = self.ws.refresh(Upstream(), MIDNIGHT_RUN)
        self.assertEqual((result["evidence_changed"], result["publish"], result["publish_reason"]),
                         (False, True, "daily_check_refresh"))

    def test_source_failure_keeps_observations_and_records_the_failure(self):
        result = self.ws.refresh(Upstream(fail=True), MIDNIGHT_RUN)
        self.assertEqual(len(result["failed_runs"]), 1)
        self.assertEqual((result["evidence_changed"], result["publish"]), (False, False))
        self.assertEqual(refresh.exit_code(result), 1)
        after = self.ws.files()
        for name in refresh.EVIDENCE_FILES + ("sources.json",):
            self.assertEqual(after[name], self.before[name], name)  # check time not advanced
        self.assertEqual(self.ws.snapshot_files(), self.before_snapshots)
        failure = json.loads(after["ingestion_runs.jsonl"].decode().splitlines()[-1])
        self.assertEqual((failure["status"], failure["problems"][-1]["type"]), ("failed", "fetch_error"))
        release = self.ws.release()
        self.assertTrue(release["ok"], release["problems"])
        self.assertEqual(release["observations"], self.count)

    def test_invalid_data_is_refused_for_publication(self):
        good = self.ws.release()
        self.assertTrue(good["ok"])
        published = {p.name: p.read_bytes() for p in self.ws.out.rglob("*") if p.is_file()}
        path = self.ws.registry / "observations.jsonl"
        lines = path.read_text(encoding="utf-8").splitlines()
        broken = json.loads(lines[0])
        broken["metric"]["numerator"] = broken["metric"]["denominator"] + 1
        path.write_text("\n".join([json.dumps(broken)] + lines[1:]) + "\n", encoding="utf-8")
        with self.assertRaises(build_site.BuildError):
            self.ws.release()
        self.assertEqual(published, {p.name: p.read_bytes() for p in self.ws.out.rglob("*") if p.is_file()})


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name) / "out"
        self.result = release_check.check_release(self.out, generated_at=stamp(LATER))

    def test_real_bundle_passes_with_exact_files_and_licence(self):
        self.assertTrue(self.result["ok"], self.result["problems"])
        self.assertEqual(sorted(self.result["files"]), sorted(list(build_site.SITE_FILES) + [
            "data.js", build_site.OWNER_MARKER, "licenses/aider-polyglot-LICENSE.txt"]))
        licence = hashlib.sha256((SNAPSHOT / "LICENSE.txt").read_bytes()).hexdigest()
        self.assertEqual(self.result["files"]["licenses/aider-polyglot-LICENSE.txt"], licence)

    def test_pilot_raw_and_private_material_is_detected(self):
        data = build_site.build_data(registry.load_registry(ROOT / "registry")[0], stamp(LATER))
        records, _ = registry.load_registry(ROOT / "registry")
        cases = {
            "raw.yml": b"- dirname: 2025-01-01--x\n",
            "trial.jsonl": b'{"data_class": "simulated_trial"}\n',
            "panel.json": b'{"status": "draft_pending_human_review"}',
            ".env": b"CLOUDFLARE_API_TOKEN=x\n",
        }
        for name, content in cases.items():
            with self.subTest(name=name):
                (self.out / name).write_bytes(content)
                problems = release_check.inspect_bundle(self.out.resolve(), data, records)
                self.assertTrue(any(name in p for p in problems), problems)
                self.assertTrue(any("forbidden text" in p for p in problems), problems)
                (self.out / name).unlink()
        (self.out / "licenses" / "aider-polyglot-LICENSE.txt").unlink()
        problems = release_check.inspect_bundle(self.out.resolve(), data, records)
        self.assertIn("missing file in bundle: licenses/aider-polyglot-LICENSE.txt", problems)

    def test_cli_rejects_unknown_arguments_and_manifest_inside_dist(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(release_check.main(["dist"]), 2)
            self.assertEqual(refresh.main(["--unknown", "x"]), 2)
            self.assertEqual(refresh.main(["--ref"]), 2)
            for bad in ("../../users", "main;rm -rf", "-x", "a b", ""):
                self.assertEqual(refresh.main(["--ref", bad]), 2, bad)


class TemplateTests(unittest.TestCase):
    TEMPLATES = ROOT / "ops" / "templates"

    def texts(self):
        return {p.name: p.read_text(encoding="utf-8") for p in self.TEMPLATES.glob("*.yml")}

    def test_templates_are_labelled(self):
        self.assertEqual(sorted(self.texts()), ["ci.yml", "publish-site.yml", "refresh-sources.yml"])
        for name, text in self.texts().items():
            self.assertTrue(text.startswith("# WORKFLOW TEMPLATE"), name)

    def test_schedule_and_separation(self):
        texts = self.texts()
        self.assertIn('- cron: "17 */6 * * *"', texts["refresh-sources.yml"])
        self.assertEqual(sum("cron:" in t for t in texts.values()), 1)
        self.assertIn("workflow_dispatch", texts["refresh-sources.yml"])
        self.assertIn("uses: ./.github/workflows/publish-site.yml", texts["refresh-sources.yml"])
        self.assertIn("group: baseline-registry-writer", texts["refresh-sources.yml"])
        self.assertIn("cancel-in-progress: false", texts["refresh-sources.yml"])
        self.assertIn("group: baseline-publish", texts["publish-site.yml"])
        for text in texts.values():
            self.assertNotIn("collector.py", text)

    def test_least_privilege_and_no_untrusted_writes(self):
        texts = self.texts()
        for name, text in texts.items():
            self.assertRegex(text, r"(?m)^permissions:", name)
            self.assertNotIn("pull_request_target", text, name)
            self.assertNotIn("write-all", text, name)
            for uses in re.findall(r"uses: (\S+)", text):
                if not uses.startswith("./"):
                    self.assertRegex(uses, r"@[0-9a-f]{40}$", f"{name}: {uses} must be pinned to a commit")
        self.assertEqual(texts["ci.yml"].count("contents: write"), 0)
        self.assertEqual(texts["publish-site.yml"].count("contents: write"), 0)
        self.assertEqual(texts["refresh-sources.yml"].count("contents: write"), 1)
        self.assertIn("permissions: {}", texts["refresh-sources.yml"])
        self.assertNotIn("secrets.", texts["ci.yml"])
        self.assertIn("persist-credentials: false", texts["ci.yml"])
        self.assertIn("persist-credentials: false", texts["publish-site.yml"])
        self.assertNotIn("pull_request", texts["refresh-sources.yml"])
        self.assertNotIn("pull_request", texts["publish-site.yml"])

    def test_workflow_inputs_never_reach_a_shell_command_directly(self):
        for name, text in self.texts().items():
            for line in text.splitlines():
                if "${{ inputs." in line:
                    self.assertRegex(line.strip(), r"^(ref|SOURCE_REF): ", f"{name}: {line.strip()}")

    def test_publication_is_gated_by_tests_and_release_check(self):
        text = self.texts()["publish-site.yml"]
        deploy = text.index("pages deploy dist")
        self.assertLess(text.index("python -B -m unittest discover -s tests"), deploy)
        self.assertLess(text.index("python -B scripts/release_check.py"), deploy)

    def test_refresh_code_never_runs_the_collector(self):
        source = (ROOT / "scripts" / "refresh.py").read_text(encoding="utf-8")
        self.assertNotIn("import collector", source)
        self.assertNotIn("os.environ", source)


if __name__ == "__main__":
    unittest.main()
