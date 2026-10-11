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
own_results = importlib.import_module("own_results")

GENERATED = "2026-09-29T00:00:00Z"


def empty_own_results(folder: Path) -> dict:
    """An isolated, empty own-results dataset, so wording tests do not depend on what has been admitted."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "data.json").write_bytes(own_results.dumps(own_results.empty_dataset()))
    (folder / "review.json").write_bytes(own_results.dumps(own_results.empty_review()))
    return {"own_data_path": folder / "data.json", "own_review_path": folder / "review.json"}


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
        cls.own = empty_own_results(Path(cls.tmp.name) / "own")
        cls.data = build_site.build(cls.out, generated_at=GENERATED, **cls.own)
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

    def test_the_home_lists_only_tested_models(self):
        """9 October 2026: with no scored Baseline result the home lists no model, no catalogue entry and no
        third-party result; retired filter links still open it."""
        for hash_ in ("#models", "#models?evidence=measured&access=consumer_app&availability=retired&sort=date"):
            with self.subTest(view=hash_):
                page = self.render(hash_)
                self.assertEqual((page["modelRows"], page["focus"], page["sparks"], page["dailyCharts"]), ([], None, 0, 0))
                self.assertIn("Baseline has no scored test result of its own to show yet.", page["text"])
                for gone in ("Featured", "New releases", "All models", "Other published tests", "Catalogue listing only",
                             "Aider", "models and apps", "Not tested by Baseline"):
                    self.assertNotIn(gone, page["text"])

    def test_third_party_results_stay_in_the_data_but_are_never_rendered(self):
        """Only Baseline's own measurements are product content: an entry with only outside results gets the honest
        explanation, no chart, no dated outside table and no outside score (owner decision, 9 October 2026)."""
        routes = {r["id"]: r for r in self.data["routes"]}
        self.assertTrue(any(r["observations"] for r in routes.values()))       # the evidence is still built
        for entry in self.measured_entries():
            with self.subTest(entry=entry["id"]):
                page = self.render(f"#model/{entry['id']}?route={entry['route_ids'][0]}")
                self.assertIn("Not tested by Baseline", page["text"])
                self.assertIn("results published by others are no longer displayed", page["text"])
                self.assertEqual((page["totalCharts"], page["dailyCharts"]), (0, 0))
                for gone in ("Aider coding results", "Pass rate", "not run by Baseline", "View dated results",
                             "Passed by 2nd try", "Source and licence", "Other published tests"):
                    self.assertNotIn(gone, page["everything"])
                self.assertFalse([a for a in page["aria"] if a.startswith("Pass rate for ")])

    def test_no_unscoped_absence_or_deployment_claims(self):
        for hash_ in ("#models", "#sources", "#about", "#how-we-test", "#model/openai-app.chatgpt",
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
                self.assertIn("Not tested by Baseline", page["text"])
                self.assertIn("Baseline has no scored test of " + entry["name"] + " through this app to show.", page["text"])
                self.assertNotIn("Pass rate", page["text"])
                self.assertEqual(page["totalCharts"], 0)
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
        render.folder = folder / "dist"
        return render

    def test_legacy_route_links_open_their_model(self):
        page = self.render("#deepseek-api.deepseek-chat")
        self.assertEqual(page["hash"], "#model/deepseek-api.deepseek-chat?route=deepseek-api.deepseek-chat")
        self.assertIn("deepseek-chat", page["text"])
        self.assertIn("Not tested by Baseline", page["text"])                  # an honest page, no outside table
        self.assertIn("See the models Baseline has tested", page["text"])
        self.assertNotIn("View dated results and sources", page["text"])

    def test_unknown_ids_get_a_usable_page(self):
        for hash_ in ("#model/no-such-model", "#model/%E0%A4%A", "#no-such-route"):
            with self.subTest(hash=hash_):
                page = self.render(hash_)
                self.assertIn("Not found", page["text"])
                self.assertIn("See the models Baseline has tested", page["text"])

    def test_sources_and_about_keep_attribution_and_limits(self):
        sources = self.render("#sources")["text"]
        self.assertIn("Apache License 2.0", sources)
        # An intermediary's model listing is shown under that service, never as the maker's own listing.
        self.assertIn("Puter: api.puter.com/puterai/chat/models (checked 2026-10-07)", sources)
        self.assertNotIn("Anthropic: api.puter.com", sources)
        self.assertIn("does not confirm which model answers a request", sources)
        self.assertIn("link only", sources)
        self.assertIn("Ingestion log", sources)
        self.assertIn("Third-party measurement sources (not displayed)", sources)
        about = self.render("#about")["text"]          # the first release's About link still works
        self.assertEqual(about, self.render("#how-we-test")["text"])
        self.assertIn("How we test", about)
        self.assertIn("missing evidence, not a score of zero", about)
        self.assertIn("Baseline's own recurring tests have not started yet.", about)

    # ---------------------------------------------------------------- T08 monitoring-first
    def test_zero_baseline_runs_never_show_a_trend(self):
        """With no Baseline runs no page shows a score, a trend or a change; model pages say "Not tested by Baseline"."""
        self.assertEqual(self.data["baseline_tests"], own_results.EMPTY_TESTS)
        hashes = ["#models", "#model/openai-app.chatgpt", f"#model/{self.measured_entries()[0]['id']}",
                  "#model/anthropic-api.claude-opus-5-5"]
        judged = ("Collecting baseline", "Not enough evidence to judge", "Lower on our tests", "Higher on our tests",
                  "No meaningful change detected", "Test unavailable", "% change", "0%", "percentage point",
                  "Largest observed movement", "Latest measurement", "First measurement")
        for hash_ in hashes:
            with self.subTest(view=hash_):
                text = self.render(hash_)["text"]
                if hash_ != "#models":
                    self.assertIn("Not tested by Baseline", text)
                    self.assertIn("Baseline has no scored test of", text)
                for phrase in judged:
                    self.assertNotIn(phrase, text)
                self.assertEqual(self.render(hash_)["totalCharts"], 0)

    def test_release_dates_are_cited_and_unknowns_say_so(self):
        dated = sorted((e for e in self.data["catalog"] if e.get("release")),
                       key=lambda e: e["release"]["date"], reverse=True)
        undated = [e for e in self.data["catalog"] if not e.get("release")]
        self.assertTrue(dated and undated)
        newest = self.render(f"#model/{dated[0]['id']}")["text"]
        self.assertIn(dated[0]["release"]["source"]["claim"], newest)        # under "Model details"
        unknown = self.render(f"#model/{undated[0]['id']}")["text"]
        self.assertIn("No verified release date recorded", unknown)
        self.assertNotIn("No release date was found", unknown)       # no claim of a search not documented

    def test_review_example_sorts_by_its_cited_release(self):
        """T08 R1: Command A+ carries Cohere's own release note and sorts by that date."""
        entry = next(e for e in self.data["catalog"] if e["id"] == "cohere-api.command-a-plus-05-2026")
        self.assertEqual(entry["release"]["date"], "2026-05-20")
        self.assertTrue(entry["release"]["source"]["url"].startswith("https://docs.cohere.com/changelog/"))
        script = ("const D = require(%s); global.window = {}; eval(require('fs').readFileSync(%s, 'utf8'));"
                  "const list = D.filterEntries(window.BASELINE_DATA.catalog, D.parseState('#models'), Date.now());"
                  "process.stdout.write(JSON.stringify(list.map((e) => [e.id, e.release ? e.release.date : null])));"
                  % (json.dumps(str(ROOT / "site" / "directory.js")), json.dumps(str(self.out / "data.js"))))
        result = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=60, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        order = json.loads(result.stdout)
        at = [i for i, (entry_id, _) in enumerate(order) if entry_id == entry["id"]][0]
        dates = [d for _, d in order]
        self.assertTrue(all(d is not None and d >= "2026-05-20" for d in dates[:at]))
        self.assertTrue(all(d is None or d <= "2026-05-20" for d in dates[at + 1:]))
        self.assertIsNotNone(dates[at + 1])                               # dated entries follow, not only unknowns
        page = self.render(f"#model/{entry['id']}")["text"]
        self.assertIn("20 May 2026 — ", page)

    def data_name(self, entry_id):
        return next(e["name"] for e in self.data["catalog"] if e["id"] == entry_id)

    def test_status_states_render_only_from_labelled_fixtures_and_never_ship(self):
        """Fixture data reaches every non-default state; the release gate refuses it."""
        target = next(e for e in self.data["catalog"] if e["identity_kind"] == "exact" and e["access_kind"] == "direct_api")["id"]
        today = datetime.now(timezone.utc).date().isoformat()
        cases = {
            "Collecting baseline": {"runs": 3, "latest_run": today},
            "No recent test": {"runs": 3, "latest_run": "2026-09-01"},
            "Not enough evidence to judge a change": {"runs": 40, "latest_run": today, "baseline_complete": True},
            "Lower on our tests": {"runs": 40, "latest_run": today, "baseline_complete": True,
                                   "analysis": {"reviewed": True, "verdict": "lower"}},
            "Test unavailable": {"runs": 40, "latest_attempt": "failed"},
        }
        records, _ = registry.load_registry(ROOT / "registry")
        for label, rec in cases.items():
            with self.subTest(state=label):
                def mutate(data, rec=rec):
                    rec = dict(rec, daily_series=[fixture_series(today)], calibration=[])
                    data["baseline_tests"] = {"runs": rec["runs"], "label": release_check.FIXTURE_LABEL,
                                              "entries": {target: rec}}
                render = self.variant(mutate)
                detail = render(f"#model/{target}")
                self.assertIn(label, detail)
                self.assertNotIn("Not tested by Baseline", detail)
                self.assertIn("1 tested model", render("#models"))              # the fixture alone is listed
                folder = render.folder
                data = json.loads((folder / "data.js").read_text(encoding="utf-8")[len("window.BASELINE_DATA = "):]
                                  .rstrip().rstrip(";"))
                problems = release_check.inspect_bundle(folder.resolve(), data, records, **self.own)
                self.assertTrue(any("do not match the admitted own-results dataset" in p for p in problems), problems)
                self.assertTrue(any("FIXTURE-NOT-FOR-PUBLICATION" in p for p in problems), problems)


def fixture_series(day: str) -> dict:
    """One labelled synthetic 40-question daily view with a single scored day (status-state fixtures only)."""
    record = {"date": day, "status": "completed", "evidence": "verified", "valid_day": True, "first_attempt_correct": 30,
              "scheduled_items": 40, "attempted_items": 40, "first_attempt_outcomes": {"correct": 30, "incorrect": 10},
              "retry_recovered": {"correct": 0, "incorrect": 0, "format_error": 0, "other": 0}}
    return {"series_id": "fixture--daily--000000000000", "as_of": day + "T12:00:00Z",
            "schedule": {"type": "daily", "start_date": day, "end_date": day, "window_start_utc": "02:00",
                         "window_minutes": 60},
            "rows": [{"date": day, "state": "completed", "eligible": True, "record": record}], "not_yet_due": 0,
            "pending_dates": [], "open_dates": [], "panel_items": 40, "panel_id": "fixture-panel",
            "settings": {"temperature": 1, "thinking_level": "MINIMAL", "max_output_tokens": 4096, "timeout_seconds": 120},
            "grader_version": "grader-v0", "config_fingerprint": "f" * 64}


OWN_FIXTURES = ROOT / "tests" / "fixtures" / "own_results"
# The synthetic graph fixtures are dated October 2026; validate them as of a fixed later time.
FIXTURE_NOW = datetime(2026, 11, 30, tzinfo=timezone.utc)
GEMINI = "google-api.gemini-3.5-flash-lite"


def retarget(bundle: dict, entry: dict) -> dict:
    """The same synthetic bundle on another exact API entry (for the mixed external/own case)."""
    b = copy.deepcopy(bundle)
    route_id = entry["route_ids"][0] if entry["route_ids"] else entry["id"]
    b["route"].update(route_id=route_id, maker=entry["maker"], exact_identifier=entry["exact_identifier"])
    b["series"]["series_id"] = f"{route_id}--{b['series']['kind']}--{b['series']['config_fingerprint'][:12]}"
    for r in b["records"]:
        r.update(route_id=route_id, requested_model=entry["exact_identifier"], series_id=b["series"]["series_id"])
    return b


@unittest.skipUnless(shutil.which("node"), "node not available")
class OwnResultsPageTests(unittest.TestCase):
    """T12: Baseline's own results render from the admitted dataset only, calibration apart from daily."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def site(self, bundles, preview=(), now=None):
        """Build into a fresh folder with these bundles imported through a temporary review manifest."""
        folder = Path(tempfile.mkdtemp(dir=self.tmp.name))
        own = empty_own_results(folder / "own")
        review = json.loads(own["own_review_path"].read_text(encoding="utf-8"))
        paths = []
        for i, bundle in enumerate(bundles):
            path = folder / f"candidate-{i}.json"
            path.write_bytes(own_results.dumps(bundle))
            review["admitted"].append({"sha256": own_results.sha256_bytes(path.read_bytes()), "reviewed_at": "2026-09-28T09:00:00Z"})
            paths.append(path)
        review["admitted"].sort(key=lambda e: e["sha256"])
        own["own_review_path"].write_bytes(own_results.dumps(review))
        for path in paths:
            own_results.import_bundle(path, own["own_review_path"], own["own_data_path"], now=FIXTURE_NOW)
        out = folder / "dist"
        data = build_site.build(out, generated_at=GENERATED, own_preview=tuple(preview), now=FIXTURE_NOW, **own)

        def page(hash_, setup=None, advance=None, refresh="tick"):
            args = ["node", str(ROOT / "tests" / "render_page.js"), str(out), hash_] + ([] if setup is None else [setup])
            env = dict(os.environ, RENDER_NOW=now) if now else None          # a fixed page clock for dated fixtures
            if advance:                                    # then move the clock and refresh the same open page
                env.update(RENDER_ADVANCE=advance, RENDER_REFRESH=refresh)
            result = subprocess.run(args, capture_output=True, text=True, timeout=60, encoding="utf-8", env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            render.last_result = json.loads(result.stdout)
            return render.last_result

        def render(hash_, setup=None):
            return page(hash_, setup)["text"]
        render.page = page
        records, _ = registry.load_registry(ROOT / "registry")
        render.problems = lambda: release_check.inspect_bundle(out.resolve(), data, records, **own)
        render.data = data
        return render

    def fixture(self, name):
        return json.loads((OWN_FIXTURES / name).read_text(encoding="utf-8"))

    def test_calibration_only_is_a_one_off_setup_test_not_monitoring(self):
        render = self.site([self.fixture("calibration.json")])
        directory = render("#models")
        self.assertIn("Baseline has published only a one-off setup test so far.", directory)
        self.assertEqual(render.page("#models")["modelRows"], [])               # a setup test is not a history
        self.assertNotIn("Baseline's own recurring tests have not started yet.", directory)
        page = render(f"#model/{GEMINI}")
        for text in ("One-off setup test", "31 of 40 correct on this test", "measured 18 Sep 2026",
                     "Not enough repeated tests to judge a change", "not part of the daily history",
                     "Waiting for daily results.",
                     "No daily test results have been published for this model yet.", "Refused: 1",
                     "Wrong answer format: 3", "Technical details", "live-calibration-20260918T043000Z-cdcdcdcdcd",
                     "Prompts and raw responses stay private"):
            self.assertIn(text, page)
        for judged in ("Collecting baseline", "Lower on our tests", "Higher on our tests", "No meaningful change",
                       "Daily results by date"):
            self.assertNotIn(judged, page)
        for other in ("google-app.gemini", "google-openrouter.gemma-3-27b-it"):     # same maker, app or other host
            self.assertIn("Not tested by Baseline", render(f"#model/{other}"))
        how = render("#how-we-test")
        for text in ("Our test method", "40 short questions written for Baseline", "structured extraction",
                     "not publicly preregistered", "No formal plan for judging changes exists yet", "grader-v0"):
            self.assertIn(text, how)
        self.assertNotIn("published before any result is shown", how)
        self.assertEqual(render.problems(), [])                       # reviewed in its own isolated manifest

    def test_daily_history_keeps_every_kind_of_missing_day_visible(self):
        render = self.site([self.fixture("daily-part1.json"), self.fixture("daily-part2.json"),
                            self.fixture("calibration.json")])
        page = render(f"#model/{GEMINI}")
        for text in ("Reference test: all 40 questions", "Daily results by date", "rows are not joined into a trend",
                     "Missed (recorded gap) — no run took place", "No record — nothing was recorded for this date",
                     "Stopped early — fewer than 90% attempted; not a usable day", "Interrupted — evidence unavailable",
                     "38 of 40", "37 of 40", "1 refused", "3 later scheduled dates were not yet due",
                     "Scheduled once a day between 02:00 and 03:00 UTC, 20 Sep 2026 to 30 Sep 2026",
                     "Latest scheduled date: 27 Sep 2026 — Completed", "One-off setup test", "31 of 40 correct on this test"):
            self.assertIn(text, page)
        # The newest usable day is days old by now: never presented as current monitoring.
        self.assertIn("No recent test", page)
        self.assertIn("this is not current monitoring", page)
        self.assertNotIn("Collecting baseline", page)
        directory = render("#models")
        self.assertIn("38 of 40latest result 27 Sep 2026", directory)
        self.assertIn("Baseline runs its own fixed tests on a small set of exact models", directory)

    def test_own_results_show_and_outside_results_stay_out_of_the_page(self):
        build = self.site([])
        measured = next(e for e in build.data["catalog"] if e["route_ids"] and e["identity_kind"] == "exact"
                        and e["access_kind"] == "direct_api")
        render = self.site([retarget(self.fixture("calibration.json"), measured)])
        page = render(f"#model/{measured['id']}")
        self.assertIn("31 of 40 correct on this test · measured", page)
        self.assertNotIn("Not tested by Baseline", page)
        for gone in ("Aider coding results", "not run by Baseline", "Other published tests"):
            self.assertNotIn(gone, page)

    def test_a_review_copy_never_passes_the_release_gate(self):
        render = self.site([], preview=[OWN_FIXTURES / "calibration.json"])
        self.assertIn("Review copy: this page includes Baseline test results that have not yet been approved",
                      render(f"#model/{GEMINI}"))
        self.assertTrue(render.data["own_results_preview"])
        problems = render.problems()
        self.assertTrue(any("review copy" in p for p in problems), problems)
        self.assertTrue(any("do not match the admitted own-results dataset" in p for p in problems), problems)

    def test_cli_review_copy_is_refused_inside_the_project(self):
        candidate = str(OWN_FIXTURES / "calibration.json")
        with unittest.mock.patch.object(build_site, "build", side_effect=AssertionError("build called")):
            for target in (ROOT / "dist", ROOT, ROOT / "site"):
                with self.subTest(target=str(target)), contextlib.redirect_stdout(io.StringIO()) as out:
                    self.assertEqual(build_site.main(["--own-results-preview", candidate, str(target)]), 1)
                self.assertIn("outside the project", out.getvalue())


GRAPH_FIXTURES = OWN_FIXTURES / "graph"


@unittest.skipUnless(shutil.which("node"), "node not available")
class DailyGraphPageTests(OwnResultsPageTests):
    """T13: the daily score graph from labelled fixtures; never a zero for a missing day, never a verdict."""

    def graph(self, name):
        return json.loads((GRAPH_FIXTURES / name).read_text(encoding="utf-8"))

    def test_several_points_render_with_gaps_marks_and_details(self):
        render = self.site([self.graph("several-points.json")])
        result = render.page(f"#model/{GEMINI}")
        text, aria = result["text"], result["aria"]
        for phrase in ("Reference test: all 40 questions", "Correct answers out of 40 (first attempts), by test date (UTC)",
                       "Lines join consecutive days only", "x a missed day", "~ an incomplete run",
                       "These scores describe this fixed test. A rise or fall alone does not establish an overall "
                       "change in model quality.", "Results checked up to 2026-10-09 12:00:00 UTC.",
                       "Daily results as a table", "Daily results by date"):
            self.assertIn(phrase, text)
        graph = [a for a in aria if a.startswith("Daily test scores:")]
        self.assertEqual(graph, ["Daily test scores: correct answers out of 40 by test date. 4 daily scores and "
                                 "4 dates without a score."])
        points = [a for a in aria if " correct on the first attempt" in a]
        self.assertEqual(len(points), 4)
        self.assertTrue(any(a.startswith("3 Oct 2026: 0 of 40 correct") for a in points))      # a real zero
        marks = [a for a in aria if a.startswith(("4 Oct", "5 Oct", "6 Oct", "7 Oct"))]
        self.assertEqual(len(marks), 4)
        self.assertTrue(any("recorded gap" in a for a in marks))
        self.assertTrue(any("nothing was recorded" in a for a in marks))
        self.assertTrue(any("37 of 40 questions attempted" in a and "Not plotted" in a for a in marks))
        self.assertTrue(any("evidence unavailable" in a for a in marks))
        ours = text[:text.index("Model details")].lower().replace("that does not mean the model is stable", "")
        for word in ("stable", "nerf", "significan", "confidence interval", "declin", "improv"):
            self.assertNotIn(word, ours)

    def test_two_makers_have_separate_graphs_on_their_own_pages(self):
        """T14: Gemini (Google API) and gpt-oss (OpenAI, hosted by Groq) never share a page or a line."""
        groq = copy.deepcopy(self.graph("second-setup.json"))
        route_id = "groq.openai.gpt-oss-120b"
        groq["route"] = {"route_id": route_id, "maker": "OpenAI", "exact_identifier": "gpt-oss-120b",
                         "access_kind": "intermediary", "service_provider": "Groq"}
        groq["series"]["series_id"] = f"{route_id}--daily--{groq['series']['config_fingerprint'][:12]}"
        for r in groq["records"]:
            r.update(route_id=route_id, requested_model="gpt-oss-120b", series_id=groq["series"]["series_id"])
        render = self.site([self.graph("several-points.json"), groq])
        gemini_page = render(f"#model/{GEMINI}")
        groq_page = render("#model/openai-groq.gpt-oss-120b")
        self.assertIn("Reference test: all 40 questions", groq_page)
        self.assertIn("Third-party host (Groq)", groq_page)
        self.assertIn("Results checked up to 2026-10-12 12:00:00 UTC.", groq_page)
        self.assertNotIn("Results checked up to 2026-10-12", gemini_page)
        self.assertIn("Results checked up to 2026-10-09 12:00:00 UTC.", gemini_page)
        for other in ("openai-app.chatgpt", "openai-openrouter.gpt-oss-120b"):
            other_page = render(f"#model/{other}")                                 # not ChatGPT, not another host
            self.assertNotIn("Reference test", other_page)
            self.assertIn("Not tested by Baseline", other_page)
        self.assertEqual(render.problems(), [])

    def test_an_open_day_is_shown_unresolved_not_missed(self):
        render = self.site([self.graph("open-day.json")])
        result = render.page(f"#model/{GEMINI}")
        self.assertIn("Still open — run not yet resolved when last checked; no score", result["text"])
        self.assertIn("o a run still open or unresolved when last checked", result["text"])
        self.assertTrue(any(a.startswith("3 Oct 2026: Run still open or unresolved") for a in result["aria"]))
        self.assertTrue(any(a.startswith("4 Oct 2026: Missed: no run took place") for a in result["aria"]))
        self.assertEqual(render.problems(), [])

    def test_schedule_only_and_one_point_messages(self):
        render = self.site([self.graph("schedule-only.json")])
        text = render(f"#model/{GEMINI}")
        self.assertIn("Waiting for daily results.", text)
        self.assertIn("Results checked up to 2026-10-01 12:00:00 UTC.", text)
        self.assertIn("28 later scheduled dates were not yet due", text)
        self.assertNotIn("Collecting baseline", text)                     # schedule only is not a test
        self.assertEqual(render.data["baseline_tests"]["runs"], 0)
        self.assertEqual(render.problems(), [])
        one = self.site([self.graph("one-point.json")])(f"#model/{GEMINI}")
        self.assertIn("One daily test; more days are needed to show a pattern.", one)

    def test_one_chart_with_setup_selector(self):
        render = self.site([self.graph("several-points.json"),
                            self.graph("second-setup.json")])
        current = render(f"#model/{GEMINI}")
        self.assertEqual(render.last_result["dailyCharts"], 1)
        self.assertEqual(render.last_result["selectedSetup"], "0")
        self.assertEqual(current.count("Correct answers out of 40 (first attempts)"), 1)
        earlier = render(f"#model/{GEMINI}", setup="1")
        self.assertEqual(render.last_result["dailyCharts"], 1)
        self.assertEqual(render.last_result["selectedSetup"], "1")
        self.assertNotEqual(current, earlier)
        for text in (current, earlier):
            self.assertIn("Test setup", text)
            self.assertIn("Choose a test setup. Different setups are kept separate and are never joined into one trend.",
                          text)
            self.assertIn("Latest setup", text)                                   # an option label, not "active"
            self.assertNotIn("history below", text)
            self.assertNotIn("Current setup", text)
        self.assertIn("Results checked up to 2026-10-12 12:00:00 UTC.", current)   # the newest setup first
        self.assertNotIn("Results checked up to 2026-10-09", current)
        self.assertIn("Results checked up to 2026-10-09 12:00:00 UTC.", earlier)   # only the chosen setup
        self.assertNotIn("Results checked up to 2026-10-12", earlier)
        self.assertIn("Selected: temperature 1, thinking level MINIMAL", earlier)
        self.assertIn("Selected: temperature 1, thinking level LOW", current)
        self.assertIn("daily 02:00–03:00 UTC · configuration b2b2b2b2", current)   # labels name window and setup
        self.assertIn("configuration a1a1a1a1", current)
        render(f"#model/{GEMINI}", setup="0")                                      # and back again
        self.assertEqual((render.last_result["dailyCharts"], render.last_result["selectedSetup"]), (1, "0"))
        single = self.site([self.graph("several-points.json")])
        text = single(f"#model/{GEMINI}")
        self.assertIsNone(single.last_result["selectedSetup"])                     # one setup: no selector
        self.assertEqual(single.last_result["dailyCharts"], 1)
        self.assertIn("Setup: temperature 1, thinking level MINIMAL", text)        # the same description

    def test_a_newer_setup_with_no_scores_stays_empty_without_borrowing_older_ones(self):
        newer = copy.deepcopy(self.graph("second-setup.json"))
        newer.update(records=[], format_version=2, open_dates=[])                 # scheduled, nothing collected yet
        render = self.site([self.graph("several-points.json"), newer])
        opened = render.page(f"#model/{GEMINI}")                                  # never hidden by the empty setup
        self.assertEqual((opened["dailyCharts"], opened["selectedSetup"]), (1, "1"))
        self.assertEqual(len([a for a in opened["aria"] if " correct on the first attempt" in a]), 4)
        latest = render.page(f"#model/{GEMINI}?setup={newer['series']['series_id']}")   # an explicit link: respected
        self.assertEqual((latest["dailyCharts"], latest["selectedSetup"]), (1, "0"))
        self.assertIn("Waiting for daily results.", latest["text"])
        self.assertFalse([a for a in latest["aria"] if " correct on the first attempt" in a])   # no older score shown
        self.assertNotIn("0 of 40 correct", latest["text"])

    def test_calibration_and_unmeasured_app_entries_stay_outside_the_graph(self):
        render = self.site([self.fixture("calibration.json"), self.graph("several-points.json"),
                            self.graph("second-setup.json")])
        for setup in (None, "1"):
            text = render(f"#model/{GEMINI}", setup=setup)
            self.assertEqual(render.last_result["dailyCharts"], 1)
            graph = text[text.index("Reference test: all 40 questions"):text.index("One-off setup test")]
            self.assertNotIn("correct on this test", graph)                       # calibration never in a setup
            self.assertIn("31 of 40 correct on this test", text[text.index("One-off setup test"):])
        app = render.page("#model/google-app.gemini")                             # similar name, different access
        self.assertEqual((app["dailyCharts"], app["selectedSetup"]), (0, None))
        self.assertIn("Baseline has no scored test of", app["text"])
        self.assertNotIn("Reference test", app["text"])

    def test_calibration_and_daily_stay_apart_and_entries_without_results_unchanged(self):
        render = self.site([self.fixture("calibration.json"), self.graph("several-points.json")])
        text = render(f"#model/{GEMINI}")
        self.assertLess(text.index("Reference test: all 40 questions"), text.index("One-off setup test"))
        self.assertIn("31 of 40 correct on this test", text)
        self.assertNotIn("31 of 40", text[text.index("Reference test: all 40 questions"):text.index("One-off setup test")])
        other = render("#model/google-app.gemini")
        self.assertNotIn("Reference test", other)
        self.assertIn("Baseline has no scored test of", other)

    def test_release_shape_setup_test_plus_schedule_only(self):
        """The first daily release: the setup test plus a schedule with no closed run yet (labelled fixtures)."""
        render = self.site([self.fixture("calibration.json"), self.graph("schedule-only.json")])
        text = render(f"#model/{GEMINI}")
        self.assertIn("Waiting for daily results.", text)
        self.assertIn("28 later scheduled dates were not yet due", text)
        self.assertNotIn("No daily test results have been published", text)      # a schedule is published
        self.assertIn("One-off setup test", text)
        self.assertIn("31 of 40 correct on this test", text)
        self.assertEqual(render.data["baseline_tests"]["runs"], 0)
        self.assertEqual(render.problems(), [])

    def test_states_across_a_daily_campaign(self):
        """Calibration-only, schedule-only, first point, later gap and open day, each from a temporary
        admitted fixture dataset (never production)."""
        cal = self.fixture("calibration.json")
        stages = {
            "calibration only": ([cal], ["Waiting for daily results.",
                                         "No daily test results have been published for this model yet."]),
            "schedule only": ([cal, self.graph("schedule-only.json")], ["Waiting for daily results."]),
            "first daily point": ([cal, self.graph("schedule-only.json"), self.graph("one-point.json")],
                                  ["One daily test; more days are needed to show a pattern."]),
            "later gap": ([cal, self.graph("one-point.json"), self.graph("several-points.json")],
                          ["Missed (recorded gap) — no run took place"]),
            "open day": ([cal, self.graph("one-point.json"), self.graph("open-day.json")],
                         ["Still open — run not yet resolved when last checked; no score",
                          "One daily test; more days are needed to show a pattern."]),
        }
        for label, (bundles, expected) in stages.items():
            with self.subTest(stage=label):
                render = self.site(bundles)
                text = render(f"#model/{GEMINI}")
                for phrase in expected:
                    self.assertIn(phrase, text)
                self.assertIn("31 of 40 correct on this test", text)                  # the setup card stays
                if label not in ("calibration only", "schedule only"):
                    self.assertNotIn("Waiting for daily results", text)
                self.assertEqual(render.problems(), [])

    def test_production_entry_matches_its_admitted_data(self):
        """Integration with the real admitted dataset: expectations are derived from it, never frozen,
        so legitimate daily publication cannot break this test."""
        out = Path(tempfile.mkdtemp(dir=self.tmp.name)) / "dist"
        data = build_site.build(out, generated_at=GENERATED)
        self.assertEqual(data["baseline_tests"], own_results.site_tests(own_results.load_admitted(), data["catalog"]))
        self.assertEqual(release_check.inspect_own_results(data), [])
        for entry_id, rec in data["baseline_tests"]["entries"].items():
            with self.subTest(entry=entry_id):
                result = subprocess.run(["node", str(ROOT / "tests" / "render_page.js"), str(out), f"#model/{entry_id}"],
                                        capture_output=True, text=True, timeout=60, encoding="utf-8")
                self.assertEqual(result.returncode, 0, result.stderr)
                text = json.loads(result.stdout)["text"]
                for cal in rec["calibration"]:
                    if cal["evidence"] == "verified":
                        self.assertIn(f"{cal['first_attempt_correct']} of {cal['scheduled_items']} correct on this test",
                                      text)
                if not rec["daily_series"]:
                    self.assertIn("No daily test results have been published for this model yet.", text)
                # The page opens on its measured setup (site/measured.js), never on a newer empty one. Other
                # setups are checked by the selector tests, not simultaneously rendered in this page.
                scored = [s for s in rec["daily_series"] if any(r["eligible"] for r in s["rows"])]
                full = [s for s in scored if s.get("contract") != "puter-subset-v1"]    # a full test opens first
                opened = full or scored or rec["daily_series"]
                for series in opened[:1]:
                    points = sum(1 for row in series["rows"] if row["eligible"])
                    message = ({0: "No daily results yet.", 1: "Not enough history to show change."}
                               if series.get("contract") == "puter-subset-v1" else
                               {0: "No complete reference evaluation yet.", 1: "Not enough history to show change."}
                               if series.get("contract") == "puter-reference-v1" else
                               {0: "Waiting for daily results.", 1: "One daily test; more days are needed to show a pattern."})
                    if points in message:
                        self.assertIn(message[points], text)
                    if any(row["state"] == "open" for row in series["rows"]):
                        self.assertIn("Still open", text)
                    if any(row["state"] == "gap" for row in series["rows"]):
                        self.assertIn("Missed (recorded gap)", text)
                self.assertIn("Correct answers out of", text)


PUTER_FIXTURES = OWN_FIXTURES / "puter"


@unittest.skipUnless(shutil.which("node"), "node not available")
@unittest.skipUnless(PUTER_FIXTURES.is_dir(), "synthetic Puter fixtures stay private (not in the public package)")
class PuterSetupSelectorTests(OwnResultsPageTests):
    """Selecting a four-question series changes the scale, explanation and identity caveats together."""

    def test_selected_puter_setup_has_its_own_scale_and_caveats(self):
        render = self.site([], preview=[PUTER_FIXTURES / name for name in build_site.PUTER_PREVIEW])
        entry = "puter.claude-sonnet-5-5"
        self.assertEqual(len(render.data["baseline_tests"]["entries"][entry]["daily_series"]), 2)
        caveat = "Four questions are a small sample and are not comparable with the 40-question tests."
        pages = [render.page(f"#model/{entry}", setup=setup) for setup in ("0", "1")]
        for page in pages:
            text = page["text"]
            self.assertEqual(page["dailyCharts"], 1)
            self.assertIn("Correct answers out of 4, by test date (UTC)", text)
            self.assertNotIn("out of 40", text)
            self.assertEqual(text.count(caveat), 1)                               # only for the selected series
            self.assertEqual(text.count("Small sample: 4 questions"), 1)
            self.assertIn("Synthetic preview — not real measurements", text)
            self.assertTrue(any("Daily test scores: correct answers out of 4 by test date" in a for a in page["aria"]))
        self.assertNotEqual(pages[0]["text"], pages[1]["text"])
        self.assertEqual([p["selectedSetup"] for p in pages], ["0", "1"])
        gpt = render.page("#model/puter.gpt-6.1-sol")                             # one setup with an identity caveat
        self.assertEqual((gpt["dailyCharts"], gpt["selectedSetup"]), (1, None))
        self.assertIn("Model identity not confirmed", gpt["text"])                # its own identity caveat
        self.assertEqual(gpt["text"].count(caveat), 1)


@unittest.skipUnless(shutil.which("node"), "node not available")
class ThirdPartyEvidenceTests(OwnResultsPageTests):
    """Third-party records stay as attributed tables; Baseline's daily history is the page's only graph."""

    def external_entry(self, data):
        with_records = {r["id"]: r for r in data["routes"] if r["observations"]}
        entry = next(e for e in data["catalog"] if set(e["route_ids"]) & set(with_records))
        route = with_records[next(i for i in entry["route_ids"] if i in with_records)]
        source = next(s for s in data["sources"] if s["id"] == route["source_ids"][0])
        return entry, route, source

    def assert_evidence_not_rendered(self, text, route, source):
        """The outside records stay in the bundle's data; the page shows none of them (9 October 2026)."""
        for gone in ("Other published tests", "These third-party results use a different test", "Source and licence",
                     "Passed by 2nd try", source["author"]):
            self.assertNotIn(gone, text)

    def test_an_external_only_model_has_no_graph_and_an_honest_empty_state(self):
        render = self.site([])
        entry, route, source = self.external_entry(render.data)
        page = render.page(f"#model/{entry['id']}")
        self.assertEqual((page["totalCharts"], page["dailyCharts"], page["selectedSetup"]), (0, 0, None))
        self.assertIn("Not tested by Baseline", page["text"])
        self.assertIn("results published by others are no longer displayed", page["text"])
        self.assert_evidence_not_rendered(page["text"], route, source)

    def test_a_model_with_both_kinds_of_evidence_draws_only_baseline_s_graph(self):
        data = self.site([]).data
        entry, route, source = self.external_entry(data)
        render = self.site([retarget(self.graph_fixture("several-points.json"), entry)])
        page = render.page(f"#model/{entry['id']}")
        self.assertEqual((page["totalCharts"], page["dailyCharts"]), (1, 1))
        self.assertIn("Reference test: all 40 questions", page["text"])
        self.assert_evidence_not_rendered(page["text"], route, source)
        self.assertEqual(len(render.data["routes"]), len(data["routes"]))         # still in the data, unchanged

    def graph_fixture(self, name):
        return json.loads((GRAPH_FIXTURES / name).read_text(encoding="utf-8"))


@unittest.skipUnless(shutil.which("node"), "node not available")
class MeasuredCoverageTests(OwnResultsPageTests):
    """The measured list, test names and denominators come from published results (8 October 2026)."""

    def published(self, route_prefix, kind="daily"):
        """The newest public admitted candidate of a route's `kind` of series (by default its four-question daily quick
        check; a route can also publish reference evaluations): genuine aggregates already published, re-imported
        here through a temporary review manifest (never the production dataset)."""
        found = []
        for path in sorted((ROOT / "own_results" / "admitted").glob("*.json")):
            bundle = json.loads(path.read_text(encoding="utf-8"))
            if bundle["series"]["series_id"].startswith(route_prefix) and bundle["series"].get("kind") == kind:
                found.append(bundle)
        if not found:
            self.skipTest("no published candidate for " + route_prefix)
        return max(found, key=lambda b: b["as_of"])

    @staticmethod
    def measured_section(text):
        start = text.index("Models tested by Baseline")
        return text[start:text.index("Each entry is one exact model", start)]

    def test_the_measured_list_is_computed_from_published_results_as_they_grow(self):
        empty = self.site([])
        self.assertIn("Baseline has no scored test result of its own to show yet.", empty("#models"))
        self.assertEqual(empty.page("#models")["modelRows"], [])
        one = self.site([self.fixture("daily-part1.json")])
        section = self.measured_section(one("#models"))
        self.assertIn("1 tested model", section)
        self.assertIn("Reference test: all 40 questions", section)
        puter = [self.published(p) for p in ("puter-claude-sonnet-5-5--", "puter-gpt-6.1-sol--", "puter-x-ai-grok-4.7--")]
        four = self.site([self.fixture("daily-part1.json")] + puter)
        page = four.page("#models")
        section = self.measured_section(page["text"])
        self.assertIn("4 tested models", section)
        self.assertEqual(len(page["modelRows"]), 4)
        self.assertEqual(page["sparks"], 4)                                  # one mini history per model
        for name in ("Claude Sonnet 5.5", "gpt-6.1-sol", "grok-4.7", "gemini-3.5-flash-lite"):   # canonical group names
            self.assertIn(name, section)
        self.assertEqual(section.count("Quick check: 4 of the 40 reference questions, through Puter"), 3)
        self.assertEqual(section.count("Reference test: all 40 questions"), 1)
        for app in ("Claude app", "ChatGPT", "Grok app", "Gemini app"):
            self.assertNotIn(app, page["text"])                          # apps are never measured by association
        tested = {k for k, r in four.data["baseline_tests"]["entries"].items() if r["runs"]}
        self.assertEqual(tested, {GEMINI, "puter.claude-sonnet-5-5", "puter.gpt-6.1-sol", "puter.x-ai-grok-4.7"})
        self.assertNotIn("Catalogue listing only", page["text"])

    def test_each_graph_names_its_test_and_keeps_its_own_denominator(self):
        grok, claude = self.published("puter-x-ai-grok-4.7--"), self.published("puter-claude-sonnet-5-5--")
        render = self.site([self.fixture("daily-part1.json"), grok, claude])
        page = render.page("#model/puter.x-ai-grok-4.7")
        self.assertIn("Quick check: 4 of the 40 reference questions, through Puter", page["text"])
        self.assertIn("Correct answers out of 4", page["text"])
        self.assertNotIn("out of 40", page["text"])
        self.assertEqual(page["dailyCharts"], 1)
        gemini = render.page(f"#model/{GEMINI}")
        self.assertIn("Reference test: all 40 questions", gemini["text"])
        self.assertIn("Correct answers out of 40", gemini["text"])
        self.assertNotIn("Quick check", gemini["text"])
        rows = render.data["baseline_tests"]["entries"]["puter.claude-sonnet-5-5"]["daily_series"][0]["rows"]
        self.assertEqual([(r["date"], r["record"]["correct"]) for r in rows if r["record"]],
                         [(r["date"], r["correct"]) for r in claude["records"]])   # the published history, unchanged

    @staticmethod
    def card_link(render, name):
        """The href of the home page's measured entry named `name` (render_page.js reports them)."""
        return next(row["href"] for row in render.page("#models")["modelRows"] if row["name"] == name)

    def test_review_r1_an_older_measured_setup_survives_a_new_empty_setup(self):
        """Codex's reproduction: two historical points, then a newer setup without results."""
        render = self.site([self.fixture("daily-part1.json"), self.fixture("graph/schedule-only.json")])
        tests = render.data["baseline_tests"]["entries"][GEMINI]
        self.assertEqual(tests["runs"], 0)                                   # the newest setup has no result yet
        section = self.measured_section(render("#models"))
        self.assertIn("1 tested model", section)
        self.assertIn("Reference test: all 40 questions · a newer test setup has no result yet", section)
        self.assertIn("37 of 40latest result 21 Sep 2026", section)          # the measured setup's own result
        href = self.card_link(render, "gemini-3.5-flash-lite")
        old = "gemini-api.gemini-3.5-flash-lite--daily--abababababab"
        self.assertIn("setup=" + old, href)                                  # the link opens the measured setup
        page = render.page(href)
        self.assertEqual(page["selectedSetup"], "1")                         # the older setup, not the empty one
        self.assertIn("Reference test: all 40 questions", page["text"])
        self.assertIn("21 Sep 2026", page["text"])
        opened = render.page(f"#model/{GEMINI}")
        self.assertEqual(opened["selectedSetup"], "1")                       # a new empty setup never hides it
        empty = render.page(f"#model/{GEMINI}?setup=" + render.data["baseline_tests"]["entries"][GEMINI]["daily_series"][0]["series_id"])
        self.assertEqual(empty["selectedSetup"], "0")                        # an explicit setup link is respected

    def test_review_r1_a_zero_score_counts_and_a_gap_or_calibration_does_not(self):
        zero = copy.deepcopy(self.published("puter-x-ai-grok-4.7--"))
        zero["records"] = [dict(r, correct=0, incorrect=r["answered"] - r["format_error"]) for r in zero["records"]]
        self.assertTrue(zero["records"])
        gap_only = copy.deepcopy(self.fixture("graph/open-day.json"))
        gap_only["records"] = [r for r in gap_only["records"] if r["status"] == "gap"]
        gap_only["as_of"] = "2026-10-05T03:00:00Z"
        render = self.site([zero, gap_only, self.fixture("calibration.json")])
        section = self.measured_section(render("#models"))
        self.assertIn("1 tested model", section)                             # Grok's genuine zero only
        self.assertIn("grok-4.7", section)
        self.assertNotIn("gemini-3.5-flash-lite", section)                   # a gap or a one-off setup test is not one
        grok = render.page("#model/puter.x-ai-grok-4.7")
        self.assertIn("0 of 4 correct; all 4 questions attempted", grok["text"])   # a scored zero, not a gap

    def test_review_r1_card_route_and_test_name_come_from_the_same_result(self):
        claude = self.published("puter-claude-sonnet-5-5--")
        render = self.site([self.fixture("graph/several-points.json"), claude])
        section = self.measured_section(render("#models"))
        self.assertIn("Quick check: 4 of the 40 reference questions, through Puter", section)
        self.assertIn("model identity not confirmed", section)
        href = self.card_link(render, "Claude Sonnet 5.5")
        self.assertIn("service=puter.claude-sonnet-5-5", href)
        self.assertIn("setup=" + claude["series"]["series_id"], href)
        page = render.page(href)
        self.assertIn("Quick check: 4 of the 40 reference questions, through Puter", page["text"])
        self.assertIn("Correct answers out of 4", page["text"])
        gemini = render.page(self.card_link(render, "gemini-3.5-flash-lite"))
        self.assertIn("Reference test: all 40 questions", gemini["text"])
        self.assertNotIn("Quick check", gemini["text"])

    def test_the_editorial_list_carries_no_fixed_result_counts(self):
        featured = json.loads((ROOT / "catalog" / "featured.json").read_text(encoding="utf-8"))
        self.assertNotIn("Measured by Baseline", [g["family"] for g in featured["groups"]])
        text = json.dumps(featured).lower()
        for stale in ("so far", "pending", "one four-question", "first daily result", "have one"):
            self.assertNotIn(stale, text)


def reference_bundle(records, route_id="puter-claude-sonnet-5-5", as_of="2026-10-15T00:00:00Z"):
    """A labelled synthetic puter-reference-v1 bundle (40 questions in batches), built from public fields only."""
    route = dict(own_results.PUTER_ROUTES[route_id], route_id=route_id, access_kind="intermediary",
                 service_provider=own_results.PUTER_SERVICE)
    ids = [f"{c}-{n:02d}" for c in ("ext", "con", "evi", "rea") for n in range(1, 11)]
    cats = [c for c in ("structured_extraction", "constraint_following", "evidence_bound", "bounded_reasoning")
            for _ in range(10)]
    series = {"contract": own_results.PUTER_REFERENCE_CONTRACT, "kind": "reference", "synthetic": True,
              "parent_panel_id": "baseline-calibration-v1", "parent_panel_sha256": "9" * 64, "grader_version": "grader-v0",
              "planned_items": 40, "item_ids": ids, "item_sha256": [hashlib.sha256(f"item {i}".encode()).hexdigest() for i in ids],
              "prompt_sha256": [hashlib.sha256(f"prompt {i}".encode()).hexdigest() for i in ids], "categories": cats,
              "settings": {"sdk_package": "@heyputer/puter.js", "sdk_version": "2.6.3", "model": route["exact_identifier"],
                           "provider": route["requested_provider"], "max_tokens": 128, "stream": False,
                           "reasoning_effort": None, "retries": 0},
              "batch_plan": [10, 10, 10, 10]}
    series["series_fingerprint"] = own_results.reference_series_fingerprint(series)
    series["series_id"] = f"{route_id}--reference--{series['series_fingerprint'][:12]}"
    out = []
    for r in records:
        attempted = 40 - r.get("not_sent", 0)
        uncertain = r.get("uncertain", 0)
        answered = attempted - uncertain
        out.append({"record_version": 1, "evaluation_id": r["id"], "status": r["status"], "date": r["finished"][:10],
                    "started_at": r["started"], "finished_at": r["finished"], "batches": r["batches"],
                    "batch_evidence_sha256": [hashlib.sha256(f"{r['id']} {n}".encode()).hexdigest()
                                              for n in range(r["batches"])],
                    "route_id": route_id, "series_id": series["series_id"], "planned_items": 40,
                    "attempted": attempted, "answered": answered, "correct": r["correct"],
                    "incorrect": answered - r["correct"], "format_error": 0,
                    "not_graded": {"error": 0, "malformed": 0, "missing_text": 0, "refusal": 0, "truncated": 0,
                                   "uncertain": uncertain},
                    "not_sent": 40 - attempted, "identity": {"unknown": attempted, "reported_match": 0, "mismatch": 0},
                    "interpretation": own_results.REFERENCE_INTERPRETATION})
    return {"format": own_results.BUNDLE_FORMAT, "format_version": 4, "as_of": as_of, "route": route,
            "series": series, "records": out}


@unittest.skipUnless(shutil.which("node"), "node not available")
class ReferenceSetupTests(MeasuredCoverageTests):
    """A 40-question reference evaluation is its own setup in the selector: its interval, 40 denominator and
    partial evaluations stay visible; the quick-check history is untouched."""

    def bundles(self):
        return [self.published("puter-claude-sonnet-5-5--"), reference_bundle([
            {"id": "puter-ref1", "status": "complete", "started": "2026-10-12T23:50:00Z",
             "finished": "2026-10-13T01:20:00Z", "batches": 4, "correct": 35},
            {"id": "puter-ref2", "status": "partial", "started": "2026-10-14T04:00:00Z",
             "finished": "2026-10-14T05:00:00Z", "batches": 3, "correct": 14, "uncertain": 16, "not_sent": 8}])]

    def test_the_reference_setup_shows_its_interval_scale_and_partial_evaluations(self):
        render = self.site(self.bundles())
        page = render.page("#model/puter.claude-sonnet-5-5")
        text = page["text"]
        self.assertEqual((page["dailyCharts"], page["selectedSetup"]), (1, "0"))      # newest setup: the reference
        self.assertIn("Reference test: all 40 questions, through Puter, in batches", text)
        self.assertIn("Correct answers out of 40", text)
        self.assertIn("12 Oct 2026 23:50 to 13 Oct 2026 01:20 UTC", text)
        self.assertIn("Partial (not a score)", text)
        self.assertIn("8 not sent", text)
        self.assertIn("(16 uncertain)", text)
        self.assertNotIn("Four questions are a small sample", text)
        self.assertIn("Model identity not confirmed", text)
        self.assertTrue(any(a.startswith("Evaluation 12 Oct 2026 23:50 to 13 Oct 2026 01:20 UTC: 35 of 40 correct")
                            for a in page["aria"]), page["aria"])
        quick = render.page("#model/puter.claude-sonnet-5-5", setup="1")              # the quick check, unchanged
        self.assertIn("Quick check: 4 of the 40 reference questions, through Puter", quick["text"])
        self.assertIn("Correct answers out of 4", quick["text"])
        self.assertNotIn("Correct answers out of 40", quick["text"])
        section = self.measured_section(render("#models"))
        self.assertIn("Reference test: all 40 questions, through Puter, in batches", section)   # its newest result
        how = render.page("#how-we-test")["text"]
        self.assertIn("Reference tests through Puter", how)
        self.assertIn("A reference test sends all 40 questions of the set once", how)
        self.assertIn("never counted as correct", how)
        without = self.site([self.published("puter-claude-sonnet-5-5--")]).page("#how-we-test")["text"]
        self.assertNotIn("Reference tests through Puter", without)                  # only once one is published

    def test_an_evaluation_without_a_complete_score_is_listed_not_plotted(self):
        render = self.site([reference_bundle([
            {"id": "puter-ref1", "status": "expired", "started": "2026-10-12T04:00:00Z",
             "finished": "2026-10-12T05:00:00Z", "batches": 2, "correct": 12, "not_sent": 20}])])
        page = render.page("#model/puter.claude-sonnet-5-5")
        self.assertIn("No complete reference evaluation yet", page["text"])
        self.assertIn("Expired (not a score)", page["text"])
        self.assertIn("20 not sent", page["text"])
        self.assertNotIn("Measured by Baseline1 exact model", page["text"].replace(" ", ""))


def several_points(changes=None, graded=True):
    """The labelled several-points fixture (8 Oct 39/40, 9 Oct 38/40). Its 8 Oct run has one request timeout, so
    by default that day is graded instead (39 correct, 1 incorrect): a fully gradeable pair that may be compared.
    `changes` replaces other days by outcome counts; the shared contract must still accept the bundle."""
    bundle = json.loads((GRAPH_FIXTURES / "several-points.json").read_text(encoding="utf-8"))
    changes = dict({"2026-10-08": {"correct": 39, "incorrect": 1}} if graded else {}, **(changes or {}))
    for r in bundle["records"]:
        if r["date"] in changes:
            outcomes = {k: 0 for k in r["first_attempt_outcomes"]}
            outcomes.update(changes[r["date"]])
            r.update(first_attempt_outcomes=outcomes, first_attempt_correct=outcomes["correct"],
                     attempted_items=40 - outcomes["not_sent"], retry_recovered={k: 0 for k in r["retry_recovered"]})
    own_results.validate_bundle(bundle)
    return bundle


@unittest.skipUnless(shutil.which("node"), "node not available")
class MeasuredSiteTests(unittest.TestCase):
    """The measured site (9 October 2026): the focus history, its descriptive comparison, the measured list and
    old links, rendered from labelled fixtures with a fixed page clock. Nothing here is production data."""
    site = OwnResultsPageTests.site
    fixture = OwnResultsPageTests.fixture
    published = MeasuredCoverageTests.published

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def graph(self, name):
        return json.loads((GRAPH_FIXTURES / name).read_text(encoding="utf-8"))

    def groq(self, name="second-setup.json"):
        bundle = copy.deepcopy(self.graph(name))
        route_id = "groq.openai.gpt-oss-120b"
        bundle["route"] = {"route_id": route_id, "maker": "OpenAI", "exact_identifier": "gpt-oss-120b",
                           "access_kind": "intermediary", "service_provider": "Groq"}
        bundle["series"]["series_id"] = f"{route_id}--daily--{bundle['series']['config_fingerprint'][:12]}"
        for r in bundle["records"]:
            r.update(route_id=route_id, requested_model="gpt-oss-120b", series_id=bundle["series"]["series_id"])
        return bundle

    def test_the_focus_is_the_first_element_and_shows_a_comparable_movement(self):
        raw = self.site([self.graph("several-points.json")], now="2026-10-10T06:00:00Z").page("#models")
        self.assertEqual(raw["focus"]["kicker"], "Latest measurement")          # 8 Oct had a request timeout
        render = self.site([several_points()], now="2026-10-10T06:00:00Z")
        home = render.page("#models")
        focus = home["focus"]
        self.assertEqual(focus["kicker"], "Largest observed movement in our latest comparable tests")
        self.assertEqual(focus["name"], "gemini-3.5-flash-lite")
        self.assertIn("service=" + GEMINI, focus["href"])
        self.assertTrue(focus["caption"].startswith("Down 2.5 percentage points: 39 of 40 correct on 8 Oct 2026, then "
                                                    "38 of 40 correct on 9 Oct 2026 (one UTC day apart)."))
        self.assertIn("not a confirmed change", focus["caption"])
        self.assertEqual(home["dailyCharts"], 1)                                 # the real history, drawn
        text = home["text"]
        self.assertLess(text.index("What changed in our latest model tests?"), text.index(focus["kicker"]))
        self.assertLess(text.index("Correct answers out of 40"), text.index("Models tested by Baseline"))
        self.assertIn("Reference test: all 40 questions · latest result 9 Oct 2026", text)   # size and result date
        for banned in ("nerf", "best model", "confirmed decline", "significan"):
            self.assertNotIn(banned, text.lower())
        later = self.site([several_points()], now="2026-10-11T00:00:01Z").page("#models")
        self.assertEqual(later["focus"]["kicker"], "Latest measurement")          # stale: never a movement
        self.assertIn("38 of 40 correct on 9 Oct 2026", later["focus"]["caption"])
        self.assertIn("does not mean the model is stable", later["focus"]["caption"])

    def test_the_largest_movement_wins_and_rises_and_falls_share_the_rule(self):
        render = self.site([several_points(), self.groq()], now="2026-10-12T12:00:00Z")
        focus = render.page("#models")["focus"]
        self.assertEqual(focus["name"], "gpt-oss-120b")                         # 31 to 29 on consecutive days
        self.assertTrue(focus["caption"].startswith("Down 5 percentage points: 31 of 40 correct on 11 Oct 2026"))
        rising = copy.deepcopy(self.groq())
        for r in rising["records"]:
            if r["date"] == "2026-10-12":                                       # 29 becomes 33: a rise of 5
                r["first_attempt_correct"] = 33
                r["first_attempt_outcomes"]["correct"] += 4
                r["first_attempt_outcomes"]["incorrect"] -= 4
        focus = self.site([several_points(), rising], now="2026-10-12T12:00:00Z").page("#models")["focus"]
        self.assertTrue(focus["caption"].startswith("Up 5 percentage points: 31 of 40 correct on 11 Oct 2026, then "
                                                    "33 of 40 correct on 12 Oct 2026"))

    def test_a_returned_model_mismatch_is_never_compared(self):
        bundle = several_points({"2026-10-09": {"correct": 38, "incorrect": 1, "answered_identity_mismatch": 1}})
        focus = self.site([bundle], now="2026-10-10T06:00:00Z").page("#models")["focus"]
        self.assertEqual(focus["kicker"], "Latest measurement")
        self.assertNotIn("percentage point", focus["caption"])

    def test_first_measurement_quick_check_and_nothing(self):
        one = self.site([self.graph("one-point.json")], now="2026-10-03T00:00:00Z").page("#models")
        self.assertEqual(one["focus"]["kicker"], "First measurement")
        self.assertIn("first result of this test setup", one["focus"]["caption"])
        self.assertIn("One daily test; more days are needed to show a pattern", one["text"])   # a point, not a line
        quick = self.site([self.published("puter-claude-sonnet-5-5--")]).page("#models")
        self.assertEqual(quick["focus"]["kicker"], "Latest quick check")
        self.assertIn("4-question quick check is a small sample", quick["focus"]["caption"])
        self.assertIn("Quick check: 4 of the 40 reference questions", quick["text"])
        schedule = self.site([self.graph("schedule-only.json")]).page("#models")
        self.assertEqual((schedule["focus"], schedule["modelRows"]), (None, []))   # a schedule is not a result

    def test_a_complete_reference_model_is_listed_and_an_unfinished_one_is_not(self):
        complete = self.site([reference_bundle([
            {"id": "puter-ref1", "status": "complete", "started": "2026-10-12T23:50:00Z",
             "finished": "2026-10-13T01:20:00Z", "batches": 4, "correct": 35}])], now="2026-10-13T06:00:00Z")
        home = complete.page("#models")
        self.assertEqual([r["name"] for r in home["modelRows"]], ["Claude Sonnet 5.5"])
        self.assertEqual(home["focus"]["kicker"], "First measurement")
        self.assertIn("Reference test: all 40 questions, through Puter, in batches", home["text"])
        self.assertIn("35 of 40", home["text"])
        self.assertNotIn("daily monitoring", home["text"].lower())
        expired = self.site([reference_bundle([
            {"id": "puter-ref1", "status": "expired", "started": "2026-10-12T04:00:00Z",
             "finished": "2026-10-12T05:00:00Z", "batches": 2, "correct": 12, "not_sent": 20}])])
        self.assertEqual(expired.page("#models")["modelRows"], [])
        page = expired.page("#model/puter.claude-sonnet-5-5")                    # its own page stays truthful
        self.assertIn("Expired (not a score)", page["text"])
        self.assertNotIn("Not tested by Baseline", page["text"])

    def test_search_provider_count_and_sort_use_only_the_measured_set(self):
        puter = [self.published(p) for p in ("puter-claude-sonnet-5-5--", "puter-gpt-6.1-sol--", "puter-x-ai-grok-4.7--")]
        render = self.site([self.fixture("daily-part1.json")] + puter)
        claude = render.page("#models?q=claude")
        self.assertEqual([r["name"] for r in claude["modelRows"]], ["Claude Sonnet 5.5"])
        self.assertIn("1 of 4 tested models", claude["text"])
        google = render.page("#models?provider=Google")
        self.assertEqual([r["name"] for r in google["modelRows"]], ["gemini-3.5-flash-lite"])
        none = render.page("#models?q=chatgpt")
        self.assertEqual(none["modelRows"], [])
        self.assertIn("No tested model matches your search.", none["text"])
        names = [r["name"] for r in render.page("#models?sort=name")["modelRows"]]
        self.assertEqual(names, sorted(names, key=str.lower))
        self.assertIn("Sorted by name (A–Z).", render("#models?sort=name"))
        text = render("#models")
        for maker in ("DeepSeek", "Mistral", "Moonshot"):                       # providers come from tested models
            self.assertNotIn(maker, text)

    def test_old_links_never_substitute_another_service_or_an_app(self):
        render = self.site([self.published("puter-claude-sonnet-5-5--")])
        canonical = render.page("#model/anthropic-api.claude-sonnet-5-5")
        self.assertEqual(canonical["dailyCharts"], 0)
        self.assertIn("Baseline has no scored test of Claude Sonnet 5.5 through the Anthropic API to show.", canonical["text"])
        self.assertIn("Claude Sonnet 5.5 — Third-party host (Puter)", canonical["text"])   # an explicit link instead
        app = render.page("#model/anthropic-app.claude")
        self.assertEqual(app["dailyCharts"], 0)
        self.assertNotIn("Third-party host (Puter)", app["text"])
        hosted = render.page("#model/anthropic-api.claude-sonnet-5-5?service=puter.claude-sonnet-5-5")
        self.assertEqual(hosted["dailyCharts"], 1)
        self.assertIn("model identity not confirmed", hosted["text"])
        self.assertEqual(render.problems(), [])


@unittest.skipUnless(shutil.which("node"), "node not available")
class MeasuredReviewFixTests(unittest.TestCase):
    """Review R1 and R2 (docs/MEASURED_SITE_REVIEW_2026-10-09.md), end to end: schema-valid daily records go
    through the real import, view generation, build and page; the clock moves on the same open page."""
    site = OwnResultsPageTests.site
    NOW = "2026-10-10T06:00:00Z"

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @staticmethod
    def several(changes=None):
        return several_points(changes)

    def built(self, changes):
        render = self.site([self.several(changes)], now=self.NOW)
        rows = render.data["baseline_tests"]["entries"][GEMINI]["daily_series"][0]["rows"]
        return render, {r["date"]: r["eligible"] for r in rows}

    def test_r1_an_all_error_day_is_a_visible_failure_never_a_zero_or_a_headline(self):
        render, eligible = self.built({"2026-10-08": {"correct": 36, "incorrect": 4},
                                       "2026-10-09": {"correct": 0, "provider_error": 40}})
        self.assertTrue(eligible["2026-10-09"])                # the shared contract calls it eligible: unchanged
        home = render.page("#models")
        self.assertNotEqual(home["focus"]["kicker"], "Largest observed movement in our latest comparable tests")
        self.assertNotIn("90 percentage points", home["text"])
        self.assertIn("A later attempt on 9 Oct 2026 has no score; the graph shows it.", home["focus"]["caption"])
        page = render.page(f"#model/{GEMINI}")
        self.assertTrue(any(a.startswith("9 Oct 2026: no gradeable answer: 40 request errors") for a in page["aria"]))
        self.assertFalse([a for a in page["aria"] if a.startswith("9 Oct 2026: 0 of 40 correct")])
        self.assertIn("! a run with no gradeable answer", page["text"])
        only = self.site([dict(self.several(), records=[r for r in self.several(
            {"2026-10-02": {"correct": 0, "provider_error": 40}})["records"] if r["date"] == "2026-10-02"],
            as_of="2026-10-02T12:00:00Z")], now=self.NOW)
        alone = only.page("#models")
        self.assertEqual((alone["modelRows"], alone["focus"]), ([], None))   # an outage alone is not a measurement
        failed = only.page(f"#model/{GEMINI}")
        self.assertNotIn("Not tested by Baseline", failed["text"])         # its own page shows the failure
        self.assertTrue(any("no gradeable answer" in a for a in failed["aria"]))

    def test_r1_forty_incorrect_answers_remain_a_genuine_zero(self):
        render, _ = self.built({"2026-10-08": {"correct": 36, "incorrect": 4}, "2026-10-09": {"correct": 0, "incorrect": 40}})
        page = render.page(f"#model/{GEMINI}")
        self.assertTrue(any(a.startswith("9 Oct 2026: 0 of 40 correct on the first attempt") for a in page["aria"]))
        focus = render.page("#models")["focus"]
        self.assertTrue(focus["caption"].startswith("Down 90 percentage points: 36 of 40 correct on 8 Oct 2026"))

    def test_r1_mixed_operational_failures_stay_visible_but_are_never_promoted(self):
        render, _ = self.built({"2026-10-08": {"correct": 36, "incorrect": 4}, "2026-10-09": {"correct": 30, "timeout": 10}})
        focus = render.page("#models")["focus"]
        self.assertEqual(focus["kicker"], "Latest measurement")
        self.assertNotIn("percentage point", focus["caption"])
        page = render.page(f"#model/{GEMINI}")
        self.assertTrue(any(a.startswith("9 Oct 2026: 30 of 40 correct on the first attempt; all 40 questions attempted; "
                                         "0 refused, 10 request errors") for a in page["aria"]), page["aria"])
        self.assertIn("Latest result: 30 of 40 correct on 9 Oct 2026", page["text"])

    def test_r2_the_open_home_page_drops_an_expired_movement_without_rebuilding(self):
        render = self.site([self.several()], now=self.NOW)
        within = render.page("#models", advance="2026-10-10T23:59:00Z")     # 9 Oct 00:00 + 48 h is 11 Oct 00:00
        self.assertEqual(within["focus"]["kicker"], "Largest observed movement in our latest comparable tests")
        self.assertEqual(within["kept"]["nodes"], within["kept"]["of"])      # nothing touched inside the window
        for refresh in ("tick", "visibility"):
            with self.subTest(refresh=refresh):
                later = render.page("#models", advance="2026-10-11T00:00:01Z", refresh=refresh)
                self.assertEqual(later["focus"]["kicker"], "Latest measurement")
                self.assertNotIn("percentage point", later["focus"]["caption"])
                self.assertIn("38 of 40 correct on 9 Oct 2026", later["focus"]["caption"])
                self.assertEqual(later["kept"]["nodes"], later["kept"]["of"])   # same series: text updated in place
                self.assertEqual(later["kept"]["charts"], later["kept"]["chartsBefore"])

    def test_r2_the_open_model_page_caption_expires_and_keeps_the_selected_setup(self):
        second = json.loads((GRAPH_FIXTURES / "second-setup.json").read_text(encoding="utf-8"))
        render = self.site([self.several(), second], now=self.NOW)
        index = str([s["series_id"] for s in render.data["baseline_tests"]["entries"][GEMINI]["daily_series"]]
                    .index(self.several()["series"]["series_id"]))
        before = render.page(f"#model/{GEMINI}", setup=index)
        self.assertIn("Latest comparable movement: Down 2.5 percentage points", before["text"])
        after = render.page(f"#model/{GEMINI}", setup=index, advance="2026-10-11T00:00:01Z")
        self.assertEqual(after["selectedSetup"], index)                      # the chosen setup stays chosen
        self.assertNotIn("Latest comparable movement", after["text"])
        self.assertIn("Latest result: 38 of 40 correct on 9 Oct 2026", after["text"])
        self.assertEqual(after["kept"]["charts"], after["kept"]["chartsBefore"])   # the graph and its points stay
        self.assertGreaterEqual(after["kept"]["nodes"], after["kept"]["of"] - 4)    # only the caption is replaced


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
