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

    def test_directory_lists_every_entry_honestly(self):
        page = self.render("#models")
        self.assertIn(f"{len(self.data['catalog'])} entries", page["text"])
        self.assertIn("Baseline's own recurring tests have not started yet.", page["text"])
        self.assertIn("API results are never shown as app results", page["text"])
        self.assertEqual(page["text"].count("Not tested by Baseline"), len(self.data["catalog"]))
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
                    self.assertIn("Not tested by Baseline", page["text"])
                    self.assertIn("No Baseline test history yet.", page["text"])
                    self.assertIn("Aider coding results", page["text"])
                    charts = [a for a in page["aria"] if a.startswith("Pass rate for ")]
                    self.assertEqual(len(charts), 1)
                    self.assertIn("Points are not connected.", charts[0])
                    self.assertIn(f"Hatched band: no observations recorded here after {latest}.", charts[0])
                    for obs in route["observations"]:
                        self.assertIn(obs["observed_at"] + (" (date only)" if obs["precision"] == "day" else ""),
                                      page["text"])

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
                self.assertIn("No other published results are recorded here for this app", page["text"])
                self.assertIn("never shown as app results", page["text"])
                self.assertIn("Not tested by Baseline", page["text"])
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
        render.folder = folder / "dist"
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
                self.assertIn("Baseline's own recurring tests have not started yet.", directory)
                self.assertIn("Other published tests available", directory)
                fresh = render(f"#model/{fresh_entry['id']}")
                old = render(f"#model/{old_entry['id']}")
                self.assertIn("These results come from Aider project", fresh)  # from the source record
                # The directory shows each entry's latest outside test date, never an age verdict.
                self.assertNotIn("Recent measurements", directory)
                self.assertNotIn("Historical evidence only", directory)
                if label == "all old":
                    self.assertIn("more than 30 days old", fresh)
                    self.assertIn("latest test 2 Jan 2025", directory)
                else:
                    self.assertIn("The newest measurement is from the last 7 days.", fresh)
                    self.assertNotIn("more than 30 days old", fresh)
                if label == "mixed":
                    self.assertIn("more than 30 days old", old)
                    self.assertIn("latest test 2 Jan 2025", directory)
                if label == "fresh only":
                    self.assertNotIn("latest test 2 Jan 2025", directory)
                for page in (fresh, old):
                    self.assertIn("No Baseline test history yet.", page)
                    self.assertIn("Not tested by Baseline", page)
                    self.assertIn("each lettered setup is a separate configuration", page)

        def no_measurements(data):
            data["routes"] = []
            for entry in data["catalog"]:
                entry["route_ids"] = []
        render = self.variant(no_measurements)
        directory = render("#models")
        self.assertNotIn("Other published tests available", directory)
        self.assertGreaterEqual(directory.count("None recorded"), len(self.data["catalog"]))  # plus the filter option
        detail = render(f"#model/{fresh_entry['id']}")
        self.assertIn("No other published results are recorded here.", detail)
        self.assertNotIn("Pass rate", detail)

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
        about = self.render("#about")["text"]          # the first release's About link still works
        self.assertEqual(about, self.render("#how-we-test")["text"])
        self.assertIn("How we test", about)
        self.assertIn("missing evidence, not a score of zero", about)
        self.assertIn("Baseline's own recurring tests have not started yet.", about)

    # ---------------------------------------------------------------- T08 monitoring-first
    def test_zero_baseline_runs_never_show_a_trend(self):
        """With no Baseline runs every page says "Not tested by Baseline" and nothing more."""
        self.assertEqual(self.data["baseline_tests"], own_results.EMPTY_TESTS)
        hashes = ["#models", "#model/openai-app.chatgpt", f"#model/{self.measured_entries()[0]['id']}",
                  "#model/anthropic-api.claude-opus-5-5"]
        judged = ("Collecting baseline", "Not enough evidence to judge", "Lower on our tests", "Higher on our tests",
                  "No meaningful change detected", "Test unavailable", "% change", "0%")
        for hash_ in hashes:
            with self.subTest(view=hash_):
                text = self.render(hash_)["text"]
                self.assertIn("Not tested by Baseline", text)
                if hash_ != "#models":
                    self.assertIn("We don't yet have our own repeated tests for this model.", text)
                    self.assertIn("No Baseline test history yet.", text)
                for phrase in judged:
                    if phrase == "0%" and hash_ == f"#model/{self.measured_entries()[0]['id']}":
                        continue                            # the outside results' chart axis starts at 0%
                    self.assertNotIn(phrase, text)
        unmeasured = self.render("#model/anthropic-api.claude-opus-5-5")
        self.assertFalse([a for a in unmeasured["aria"] if a.startswith("Pass rate for ")])  # no empty plot

    def test_release_dates_order_the_directory_and_unknowns_say_so(self):
        dated = sorted((e for e in self.data["catalog"] if e.get("release")),
                       key=lambda e: e["release"]["date"], reverse=True)
        undated = [e for e in self.data["catalog"] if not e.get("release")]
        self.assertTrue(dated and undated)
        text = self.render("#models")["text"]
        newest = self.render(f"#model/{dated[0]['id']}")["text"]
        self.assertIn("release source", newest)
        self.assertIn(dated[0]["release"]["source"]["claim"], newest)
        first_unknown = text.index("No verified date")
        self.assertLess(text.index(dated[0]["name"]), text.index(dated[-1]["name"]))
        self.assertLess(text.index(dated[-1]["name"]), first_unknown)
        unknown = self.render(f"#model/{undated[0]['id']}")["text"]
        self.assertIn("No verified release date recorded", unknown)
        self.assertNotIn("No release date was found", unknown)       # no claim of a search not documented
        self.assertIn("Sorted by newest release", text)
        by_name = self.render("#models?sort=name")["text"]
        self.assertIn("Sorted by name (A–Z).", by_name)
        self.assertNotIn("Sorted by newest release", by_name)          # the note follows the selected order
        names = sorted((e["name"].lower(), e["id"]) for e in self.data["catalog"])
        self.assertLess(by_name.index(self.data_name(names[0][1])), by_name.index(self.data_name(names[-1][1])))

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
        self.assertIn("Released 20 May 2026", page)

    def data_name(self, entry_id):
        return next(e["name"] for e in self.data["catalog"] if e["id"] == entry_id)

    def test_status_states_render_only_from_labelled_fixtures_and_never_ship(self):
        """Fixture data reaches every non-default state; the release gate refuses it."""
        target = self.measured_entries()[0]["id"]
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
                    data["baseline_tests"] = {"runs": rec["runs"], "label": release_check.FIXTURE_LABEL,
                                              "entries": {target: rec}}
                render = self.variant(mutate)
                detail = render(f"#model/{target}")
                self.assertIn(label, detail)
                self.assertNotIn("Not tested by Baseline", detail)
                self.assertIn("Not tested by Baseline", render("#models"))   # other entries unchanged
                folder = render.folder
                data = json.loads((folder / "data.js").read_text(encoding="utf-8")[len("window.BASELINE_DATA = "):]
                                  .rstrip().rstrip(";"))
                problems = release_check.inspect_bundle(folder.resolve(), data, records, **self.own)
                self.assertTrue(any("do not match the admitted own-results dataset" in p for p in problems), problems)
                self.assertTrue(any("FIXTURE-NOT-FOR-PUBLICATION" in p for p in problems), problems)


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

    def site(self, bundles, preview=()):
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

        def page(hash_):
            result = subprocess.run(["node", str(ROOT / "tests" / "render_page.js"), str(out), hash_],
                                    capture_output=True, text=True, timeout=60, encoding="utf-8")
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)

        def render(hash_):
            return page(hash_)["text"]
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
        self.assertIn("One-off setup test", directory)
        self.assertIn("31 of 40 correct on this test, 18 Sep 2026", directory)
        self.assertIn("Baseline has published a one-off setup test of its own", directory)
        self.assertNotIn("Baseline's own recurring tests have not started yet.", directory)
        self.assertEqual(directory.count("Not tested by Baseline"), len(render.data["catalog"]) - 1)
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
        for text in ("Daily test scores", "Daily results by date", "rows are not joined into a trend",
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
        self.assertIn("latest daily test 27 Sep 2026", directory)
        self.assertIn("Baseline publishes results from its own repeated tests for some models", directory)

    def test_own_and_outside_results_stay_in_separate_sections(self):
        build = self.site([])
        measured = next(e for e in build.data["catalog"] if e["route_ids"] and e["identity_kind"] == "exact"
                        and e["access_kind"] == "direct_api")
        render = self.site([retarget(self.fixture("calibration.json"), measured)])
        page = render(f"#model/{measured['id']}")
        section = page.index("31 of 40 correct on this test · measured")
        self.assertLess(page.index("Our tests"), section)
        self.assertLess(section, page.index("Other published tests"))
        self.assertIn("Aider coding results", page)
        self.assertIn("not run by Baseline", page)

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
        for phrase in ("Daily test scores", "Correct answers out of 40 (first attempts), by test date (UTC)",
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
        ours = text[text.index("Our tests"):text.index("Other published tests")].lower()   # catalogue notes excluded
        for word in ("stable", "nerf", "significan", "confidence interval", "declin", "improv"):
            self.assertNotIn(word, ours)

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

    def test_two_setups_are_separate_histories_newest_first(self):
        render = self.site([self.graph("several-points.json"), self.graph("second-setup.json")])
        text = render(f"#model/{GEMINI}")
        self.assertIn("each setup has its own history below, newest first", text)
        current = text.index("Current setup: temperature 1, thinking level LOW")
        earlier = text.index("Earlier setup: temperature 1, thinking level MINIMAL")
        self.assertLess(current, earlier)
        self.assertEqual(text.count("Correct answers out of 40 (first attempts)"), 2)

    def test_calibration_and_daily_stay_apart_and_entries_without_results_unchanged(self):
        render = self.site([self.fixture("calibration.json"), self.graph("several-points.json")])
        text = render(f"#model/{GEMINI}")
        self.assertLess(text.index("Daily test scores"), text.index("One-off setup test"))
        self.assertIn("31 of 40 correct on this test", text)
        self.assertNotIn("31 of 40", text[text.index("Daily test scores"):text.index("One-off setup test")])
        other = render("#model/google-app.gemini")
        self.assertNotIn("Daily test scores", other)
        self.assertIn("No Baseline test history yet.", other)

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
                for series in rec["daily_series"]:
                    points = sum(1 for row in series["rows"] if row["eligible"])
                    message = {0: "Waiting for daily results.", 1: "One daily test; more days are needed to show a pattern."}
                    if points in message:
                        self.assertIn(message[points], text)
                    if any(row["state"] == "open" for row in series["rows"]):
                        self.assertIn("Still open", text)
                    if any(row["state"] == "gap" for row in series["rows"]):
                        self.assertIn("Missed (recorded gap)", text)
                self.assertIn("Daily test scores", text)


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
