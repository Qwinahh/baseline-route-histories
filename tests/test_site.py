"""T03 model-history page: build output, data mapping, freshness logic and contract v2."""
import contextlib
import copy
from datetime import datetime, timezone
import hashlib
import importlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest.mock
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
registry = importlib.import_module("registry")
build_site = importlib.import_module("build_site")
release_check = importlib.import_module("release_check")
aider_polyglot = importlib.import_module("aider_polyglot")

GENERATED = "2026-09-29T00:00:00Z"


def load_data(folder: Path) -> dict:
    text = (folder / "data.js").read_text(encoding="utf-8")
    prefix = "window.BASELINE_DATA = "
    assert text.startswith(prefix) and text.rstrip().endswith(";")
    return json.loads(text[len(prefix):].rstrip().rstrip(";"))


class BuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name) / "dist"
        cls.data = build_site.build(cls.out, generated_at=GENERATED)
        cls.records, _ = registry.load_registry(ROOT / "registry")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_bundle_contains_only_page_data_and_licence(self):
        files = sorted(p.relative_to(self.out).as_posix() for p in self.out.rglob("*") if p.is_file())
        self.assertEqual(files, sorted(list(build_site.SITE_FILES) + [
            "data.js", "licenses/aider-polyglot-LICENSE.txt", build_site.OWNER_MARKER]))

    def test_raw_snapshots_are_not_bundled(self):
        bundle = b"".join(p.read_bytes() for p in self.out.rglob("*") if p.is_file())
        snapshot = next((ROOT / "evidence" / "snapshots" / "aider-polyglot").glob("*/polyglot_leaderboard.yml"))
        self.assertNotIn(b"- dirname:", bundle)
        self.assertNotIn(snapshot.read_bytes()[:200], bundle)
        self.assertNotIn(b"SNAPSHOT.json", bundle)

    def test_bundled_licence_is_the_reviewed_one(self):
        digest = hashlib.sha256((self.out / "licenses" / "aider-polyglot-LICENSE.txt").read_bytes()).hexdigest()
        self.assertIn(digest, aider_polyglot.REVIEWED_LICENSE_SHA256)

    def test_data_matches_registry_without_joining_series(self):
        self.assertEqual(self.data, load_data(self.out))
        self.assertEqual(self.data["generated_at"], GENERATED)
        self.assertFalse(self.data["independent_monitoring"])
        observations = [o for r in self.data["routes"] for o in r["observations"]]
        self.assertEqual(len(observations), len(self.records["observations"]))
        by_id = {o["id"]: o for o in self.records["observations"]}
        for obs in observations:
            source = by_id[obs["id"]]
            for field in ("observed_at", "retrieved_at", "metric", "exclusions", "evidence_url", "series_id"):
                self.assertEqual(obs[field], source[field], (obs["id"], field))
            self.assertEqual(obs["precision"], "day")
            self.assertEqual(obs["source_label"], source["source_details"]["model"])
        for route in self.data["routes"]:
            letters = [o["series_letter"] for o in route["observations"]]
            self.assertEqual(len(set(letters)), len(route["series"]), route["id"])
            dates = [o["observed_at"] for o in route["observations"]]
            self.assertEqual(dates, sorted(dates))

    def test_every_setup_change_shows_its_configuration_break(self):
        series = {s["id"]: s for s in self.records["series"]}
        for route in self.data["routes"]:
            for before, obs in zip(route["observations"], route["observations"][1:]):
                fields = {b["field"] for b in obs["breaks"]}
                old, new = series[before["series_id"]], series[obs["series_id"]]
                if old["id"] == new["id"]:
                    self.assertFalse({"harness", "prompt_set", "suite_version"} & fields, obs["id"])
                for field in build_site.BREAK_FIELDS:
                    self.assertEqual(field in fields, old[field] != new[field], (obs["id"], field))
                if before["source_label"] != obs["source_label"]:
                    self.assertIn("source model label", fields, obs["id"])

    def test_superseded_development_runs_are_marked(self):
        superseded = {r["id"] for r in self.data["runs"] if r["superseded"]}
        expected = {c["target_id"] for c in self.records["corrections"]
                    if c["target_kind"] == "ingestion_runs" and c["action"] == "superseded"}
        self.assertEqual(superseded, expected)
        # The two T02 development runs stay marked however the log grows.
        self.assertTrue({"run-aider-polyglot-20260928t223324z", "run-aider-polyglot-20260928t223325z"} <= superseded)
        self.assertEqual(len(self.data["runs"]), len(self.records["ingestion_runs"]))

    def test_link_only_source_has_no_licence_or_numbers(self):
        livenerf = next(s for s in self.data["sources"] if s["id"] == "livenerf")
        self.assertIsNone(livenerf["licence"])
        self.assertFalse([r for r in self.data["routes"] if "livenerf" in r["source_ids"]])

    def test_script_closing_tags_are_escaped(self):
        self.assertNotIn("</", (self.out / "data.js").read_text(encoding="utf-8"))

    def test_invalid_registry_fails_before_touching_output(self):
        with tempfile.TemporaryDirectory() as folder:
            bad = Path(folder) / "registry"
            shutil.copytree(ROOT / "registry", bad)
            path = bad / "series.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data["records"][0]["harness"] = "edited"
            path.write_text(json.dumps(data), encoding="utf-8")
            out = Path(folder) / "dist"
            out.mkdir()
            (out / "keep.txt").write_text("existing", encoding="utf-8")
            with self.assertRaises(build_site.BuildError):
                build_site.build(out, registry_dir=bad)
            self.assertTrue((out / "keep.txt").is_file())


def _refuse_destruction(*args, **kwargs):
    raise AssertionError("a destructive or writing operation was reached")


class BuildSafetyTests(unittest.TestCase):
    """docs/T03_REVIEW.md R1. Dangerous targets are exercised only with every write and
    delete operation replaced by a function that fails the test if reached."""

    def guarded_build(self, target):
        with unittest.mock.patch.object(Path, "unlink", _refuse_destruction), \
             unittest.mock.patch.object(Path, "write_bytes", _refuse_destruction), \
             unittest.mock.patch.object(Path, "write_text", _refuse_destruction), \
             unittest.mock.patch.object(Path, "mkdir", _refuse_destruction), \
             unittest.mock.patch.object(shutil, "rmtree", _refuse_destruction), \
             unittest.mock.patch.object(os, "remove", _refuse_destruction):
            with self.assertRaises(build_site.BuildError) as caught:
                build_site.build(target, generated_at=GENERATED)
        return str(caught.exception)

    def test_project_and_protected_targets_are_refused_before_any_write(self):
        targets = [ROOT, ROOT.parent, Path(ROOT.anchor), ROOT / "registry", ROOT / "evidence",
                   ROOT / "evidence" / "snapshots", ROOT / "site", ROOT / "scripts", ROOT / "tests",
                   ROOT / ".git", ROOT / "docs", ROOT / "dist" / "nested", ROOT / "dist" / ".."]
        for target in targets:
            with self.subTest(target=str(target)):
                message = self.guarded_build(target)
                self.assertIn("refusing output", message)

    def test_cli_rejects_any_output_argument(self):
        with unittest.mock.patch.object(build_site, "build", side_effect=AssertionError("build called")):
            for argv in (["."], [str(ROOT)], ["some-folder"]):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(build_site.main(argv), 2)

    def test_cli_default_builds_project_dist_only(self):
        seen = []
        fake = {"routes": [], "generated_at": GENERATED}
        with unittest.mock.patch.object(build_site, "build", side_effect=lambda out: seen.append(out) or fake):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(build_site.main([]), 0)
        self.assertEqual(seen, [ROOT / "dist"])

    def test_unrelated_nonempty_folder_is_refused_and_kept(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "out"
            (out / "licenses").mkdir(parents=True)
            (out / "notes.txt").write_text("sentinel", encoding="utf-8")
            (out / "index.html").write_text("someone else's page", encoding="utf-8")
            with self.assertRaises(build_site.BuildError):
                build_site.build(out, generated_at=GENERATED)
            self.assertEqual((out / "notes.txt").read_text(encoding="utf-8"), "sentinel")
            self.assertEqual((out / "index.html").read_text(encoding="utf-8"), "someone else's page")

    def test_foreign_file_inside_licenses_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "out"
            build_site.build(out, generated_at=GENERATED)
            (out / "licenses" / "keep.txt").write_text("sentinel", encoding="utf-8")
            with self.assertRaises(build_site.BuildError):
                build_site.build(out, generated_at=GENERATED)
            self.assertTrue((out / "licenses" / "keep.txt").is_file())

    def test_file_target_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "out"
            out.write_text("sentinel", encoding="utf-8")
            with self.assertRaises(build_site.BuildError):
                build_site.build(out, generated_at=GENERATED)
            self.assertEqual(out.read_text(encoding="utf-8"), "sentinel")

    def test_rebuild_replaces_only_its_own_files(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "out"
            build_site.build(out, generated_at=GENERATED)
            (out / "licenses" / "old-source-LICENSE.txt").write_text("stale", encoding="utf-8")
            build_site.build(out, generated_at="2026-09-30T00:00:00Z")
            files = sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file())
            self.assertEqual(files, sorted(list(build_site.SITE_FILES) + [
                "data.js", "licenses/aider-polyglot-LICENSE.txt", build_site.OWNER_MARKER]))
            self.assertEqual(load_data(out)["generated_at"], "2026-09-30T00:00:00Z")

    def test_licence_failure_leaves_previous_output_untouched(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "out"
            build_site.build(out, generated_at=GENERATED)
            before = {p.name: p.read_bytes() for p in out.rglob("*") if p.is_file()}
            with self.assertRaises(build_site.BuildError):
                build_site.build(out, evidence_root=Path(folder) / "no-evidence", generated_at="2026-09-30T00:00:00Z")
            after = {p.name: p.read_bytes() for p in out.rglob("*") if p.is_file()}
            self.assertEqual(before, after)

    def test_symlink_or_junction_target_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            real = Path(folder) / "real"
            real.mkdir()
            (real / "sentinel.txt").write_text("keep", encoding="utf-8")
            link = Path(folder) / "link"
            try:
                os.symlink(real, link, target_is_directory=True)
            except (OSError, NotImplementedError):
                if os.name != "nt":
                    self.skipTest("cannot create a symlink here")
                result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(real)],
                                        capture_output=True, text=True)
                if result.returncode != 0:
                    self.skipTest("cannot create a symlink or junction here")
            with self.assertRaises(build_site.BuildError) as caught:
                build_site.build(link, generated_at=GENERATED)
            self.assertIn("symlink or junction", str(caught.exception))
            self.assertEqual((real / "sentinel.txt").read_text(encoding="utf-8"), "keep")
            self.assertEqual(sorted(p.name for p in real.iterdir()), ["sentinel.txt"])


@unittest.skipUnless(shutil.which("node"), "node not available")
class RenderedCoverageWordingTests(unittest.TestCase):
    """Rendered text and accessibility labels, view by view (T03 R2, T05 R3, T07).
    Gaps describe this registry's coverage only; apps never show API results; wording
    stays true before and after publication. Expectations come from the current data."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name) / "dist"
        cls.data = build_site.build(cls.out, generated_at=GENERATED)
        cls.pages = {}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def render(self, hash_):
        if hash_ not in self.pages:
            result = subprocess.run(["node", str(ROOT / "tests" / "render_page.js"), str(self.out), hash_],
                                    capture_output=True, text=True, timeout=60, encoding="utf-8")
            self.assertEqual(result.returncode, 0, result.stderr)
            page = json.loads(result.stdout)
            page["everything"] = page["text"] + " " + " ".join(page["aria"])
            self.pages[hash_] = page
        return self.pages[hash_]

    def measured_entries(self):
        return [e for e in self.data["catalog"] if e["route_ids"]]

    def test_directory_lists_every_entry_honestly(self):
        page = self.render("#models")
        self.assertIn(f"{len(self.data['catalog'])} entries", page["text"])
        self.assertIn("runs no independent tests of any model", page["text"])
        self.assertIn("API results are never shown as app results", page["text"])
        for entry in self.data["catalog"]:
            self.assertIn(entry["name"], page["text"])

    def test_every_measured_route_uses_scoped_gap_wording(self):
        routes = {r["id"]: r for r in self.data["routes"]}
        for entry in self.measured_entries():
            for route_id in entry["route_ids"]:
                with self.subTest(route=route_id):
                    page = self.render(f"#model/{entry['id']}?route={route_id}")
                    route = routes[route_id]
                    latest = route["observations"][-1]["observed_at"]
                    self.assertIn("No observations are recorded here between these runs or after the latest one",
                                  page["text"])
                    self.assertIn("other measurements may exist elsewhere", page["text"])
                    self.assertIn("Baseline has not run its own tests on this route.", page["text"])
                    charts = [a for a in page["aria"] if a.startswith("Pass rate for ")]
                    self.assertEqual(len(charts), 1)
                    self.assertIn("Points are not connected.", charts[0])
                    self.assertIn(f"Hatched band: no observations recorded here after {latest}.", charts[0])
                    for obs in route["observations"]:
                        self.assertIn(obs["observed_at"] + (" (date only)" if obs["precision"] == "day" else ""),
                                      page["text"])

    def test_no_unscoped_absence_or_deployment_claims(self):
        for hash_ in ("#models", "#sources", "#about", "#model/openai-app.chatgpt",
                      f"#model/{self.measured_entries()[0]['id']}"):
            with self.subTest(view=hash_):
                lowered = self.render(hash_)["everything"].lower()
                for phrase in ("nothing was measured", "not measured", "unmeasured", "nobody measured"):
                    self.assertNotIn(phrase, lowered)
                for claim in release_check.DEPLOYMENT_CLAIMS:
                    self.assertNotIn(claim, lowered)

    def test_apps_show_no_measurements_and_say_why(self):
        for entry in self.data["catalog"]:
            if entry["access_kind"] != "consumer_app":
                continue
            with self.subTest(app=entry["id"]):
                page = self.render(f"#model/{entry['id']}")
                self.assertIn("No measurements recorded here", page["text"])
                self.assertIn("never shown as app results", page["text"])
                self.assertNotIn("Pass rate", page["text"])
                self.assertFalse([a for a in page["aria"] if a.startswith("Pass rate for ")])

    def variant(self, mutate):
        """Render from a temporary copy of the built page whose data.js is changed by `mutate`."""
        folder = Path(tempfile.mkdtemp(dir=self.tmp.name))
        shutil.copytree(self.out, folder / "dist")
        path = folder / "dist" / "data.js"
        prefix = "window.BASELINE_DATA = "
        data = json.loads(path.read_text(encoding="utf-8")[len(prefix):].rstrip().rstrip(";"))
        mutate(data)
        path.write_text(prefix + json.dumps(data) + ";\n", encoding="utf-8")

        def render(hash_):
            result = subprocess.run(["node", str(ROOT / "tests" / "render_page.js"), str(folder / "dist"), hash_],
                                    capture_output=True, text=True, timeout=60, encoding="utf-8")
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)["text"]
        return render

    def test_age_wording_follows_measurement_dates(self):
        """T07 R3: all-old, mixed-age, fresh-only and no-measurement data; wording and badges agree."""
        today = datetime.now(timezone.utc).date().isoformat()
        measured = self.measured_entries()
        fresh_entry, old_entry = measured[0], measured[-1]
        fresh_routes = set(fresh_entry["route_ids"])

        def set_dates(data, route_ids, day):
            for route in data["routes"]:
                if route["id"] in route_ids:
                    for obs in route["observations"]:
                        obs["observed_at"] = day
        all_ids = {r["id"] for r in self.data["routes"]}
        old_day = "2025-01-02"  # explicit dates: the test must not depend on the evolving registry
        cases = {
            "all old": lambda d: set_dates(d, all_ids, old_day),
            "mixed": lambda d: (set_dates(d, all_ids, old_day), set_dates(d, fresh_routes, today)),
            "fresh only": lambda d: set_dates(d, all_ids, today),
        }
        for label, mutate in cases.items():
            with self.subTest(case=label):
                render = self.variant(mutate)
                directory = render("#models")
                self.assertNotIn("historical results", directory)
                self.assertIn("Baseline runs no independent tests of any model", directory)
                fresh = render(f"#model/{fresh_entry['id']}")
                old = render(f"#model/{old_entry['id']}")
                self.assertIn("These results come from Aider project", fresh)  # from the source record
                if label == "all old":
                    self.assertIn("more than 30 days old", fresh)
                    self.assertNotIn("Recent measurements", directory)
                else:
                    self.assertIn("The newest measurement is from the last 7 days.", fresh)
                    self.assertIn("Recent measurements", directory)
                    self.assertNotIn("more than 30 days old", fresh)
                if label == "mixed":
                    self.assertIn("more than 30 days old", old)
                    self.assertIn("Historical evidence only", directory)
                if label == "fresh only":
                    self.assertNotIn("Historical evidence only", directory)
                for page in (fresh, old):
                    self.assertIn("Baseline has not run its own tests on this route.", page)
                    self.assertIn("each lettered setup is a separate configuration", page)

        def no_measurements(data):
            data["routes"] = []
            for entry in data["catalog"]:
                entry["route_ids"] = []
        render = self.variant(no_measurements)
        directory = render("#models")
        self.assertIn(" 0 have dated measurements", directory)
        self.assertNotIn("Recent measurements", directory)
        self.assertNotIn("Historical evidence only", directory)
        self.assertIn("No measurements recorded here", render(f"#model/{fresh_entry['id']}"))

    def test_legacy_route_links_open_their_model(self):
        page = self.render("#deepseek-api.deepseek-chat")
        self.assertEqual(page["hash"], "#model/deepseek-api.deepseek-chat?route=deepseek-api.deepseek-chat")
        self.assertIn("deepseek-chat", page["text"])
        self.assertIn("Pass rate by run", page["text"])

    def test_unknown_ids_get_a_usable_page(self):
        for hash_ in ("#model/no-such-model", "#model/%E0%A4%A", "#no-such-route"):
            with self.subTest(hash=hash_):
                page = self.render(hash_)
                self.assertIn("Not found", page["text"])
                self.assertIn("Go to the model directory", page["text"])

    def test_sources_and_about_keep_attribution_and_limits(self):
        sources = self.render("#sources")["text"]
        self.assertIn("Apache License 2.0", sources)
        self.assertIn("link only", sources)
        self.assertIn("Ingestion log", sources)
        about = self.render("#about")["text"]
        self.assertIn("missing evidence, not a score of zero", about)


class PageSourceTests(unittest.TestCase):
    def test_page_loads_nothing_external_and_sets_csp(self):
        html = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
        self.assertIn("Content-Security-Policy", html)
        self.assertIn("default-src 'none'", html)
        for attr in ('src="http', "href=\"http", "src=\"//", "href=\"//"):
            self.assertNotIn(attr, html)
        css = (ROOT / "site" / "styles.css").read_text(encoding="utf-8")
        self.assertNotIn("@import", css)
        self.assertNotIn("url(http", css)

    def test_renderer_never_injects_html_strings(self):
        js = (ROOT / "site" / "app.js").read_text(encoding="utf-8")
        for risky in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
            self.assertNotIn(risky, js)


@unittest.skipUnless(shutil.which("node"), "node not available")
class FreshnessTests(unittest.TestCase):
    """Runs site/freshness.js under Node with fixed clocks."""

    def run_js(self, expression):
        script = ("const F = require(%s); const out = (%s); process.stdout.write(JSON.stringify(out));"
                  % (json.dumps(str(ROOT / "site" / "freshness.js")), expression))
        result = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_age_grows_with_the_clock_for_the_same_data(self):
        out = self.run_js("""[
          F.describeAge('2025-10-03', Date.parse('2026-09-29T10:00:00Z')),
          F.describeAge('2025-10-03', Date.parse('2026-10-29T10:00:00Z')),
          F.measurementStatus('2026-09-25', Date.parse('2026-09-29T10:00:00Z')).key,
          F.measurementStatus('2026-09-25', Date.parse('2026-10-10T10:00:00Z')).key,
          F.measurementStatus('2026-09-25', Date.parse('2026-12-01T10:00:00Z')).key
        ]""")
        self.assertEqual(out, ["about 361 days ago", "about 391 days ago", "recent", "aging", "stale"])

    def test_day_precision_is_never_shown_in_hours(self):
        out = self.run_js("""[
          F.describeAge('2026-09-29', Date.parse('2026-09-29T18:00:00Z')),
          F.describeAge('2026-09-29T10:00:00Z', Date.parse('2026-09-29T13:30:00Z')),
          F.describeAge('2026-09-29T10:00:00Z', Date.parse('2026-09-29T10:20:00Z')),
          F.describeAge('not a date', Date.parse('2026-09-29T10:00:00Z'))
        ]""")
        self.assertEqual(out, ["today (date only)", "3 hours ago", "under an hour ago", "unknown age"])

    def test_newest_and_gap_helpers(self):
        out = self.run_js("""[
          F.newest(['2024-12-21', '2025-10-03', '2025-03-24']),
          F.longestGapDays(['2024-12-21', '2025-10-03', '2025-03-24'])
        ]""")
        self.assertEqual(out, ["2025-10-03", 193])


class ContractV2Tests(unittest.TestCase):
    def setUp(self):
        self.records, errors = registry.load_registry(ROOT / "tests" / "fixtures" / "registry_valid")
        assert not errors
        self.now = datetime(2026, 12, 31, tzinfo=timezone.utc)

    def run_record(self):
        return {"id": "fixture-run-1", "fixture": True, "source_id": "fixture-source-a",
                "started_at": "2026-01-02T00:00:00Z", "finished_at": "2026-01-02T00:00:01Z",
                "status": "succeeded", "source_revision": None, "snapshot_path": None,
                "snapshot_sha256": None, "counts": {}, "problems": []}

    def correction(self, **changes):
        base = {"id": "fixture-correction-1", "fixture": True, "target_kind": "ingestion_runs",
                "target_id": "fixture-run-1", "action": "superseded", "reason": "test",
                "recorded_at": "2026-01-03T00:00:00Z"}
        base.update(changes)
        return base

    def errors(self, correction):
        records = copy.deepcopy(self.records)
        records["ingestion_runs"].append(self.run_record())
        records["corrections"].append(correction)
        return registry.validate_records(records, fixture_mode=True, now=self.now)

    def test_valid_correction_passes(self):
        self.assertEqual(self.errors(self.correction()), [])

    def test_correction_must_target_an_existing_run(self):
        self.assertTrue(any("unknown ingestion_runs id" in e for e in self.errors(self.correction(target_id="fixture-run-9"))))

    def test_unknown_action_or_kind_rejected(self):
        self.assertTrue(any(".action:" in e for e in self.errors(self.correction(action="deleted"))))
        self.assertTrue(any(".target_kind:" in e for e in self.errors(self.correction(target_kind="observations"))))

    def test_schema_version_is_2_everywhere(self):
        self.assertEqual(registry.SCHEMA_VERSION, 2)
        for folder in (ROOT / "registry", ROOT / "tests" / "fixtures" / "registry_valid"):
            for kind in registry.JSON_FILES:
                data = json.loads((folder / f"{kind}.json").read_text(encoding="utf-8"))
                self.assertEqual(data["schema_version"], 2, (folder, kind))


if __name__ == "__main__":
    unittest.main()
