"""T12 own results: public validator, admission-gated importer and site summary. Offline.

Synthetic fixtures live in tests/fixtures/own_results/ and are never production data;
their digests are refused by the production review gate and the release check.
"""
import copy
import importlib
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
own_results = importlib.import_module("own_results")

FIXTURES = ROOT / "tests" / "fixtures" / "own_results"
GEMINI = "google-api.gemini-3.5-flash-lite"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def catalog_entries() -> list:
    return json.loads((ROOT / "catalog" / "models.json").read_text(encoding="utf-8"))["entries"]


class Workspace:
    """A temporary dataset, review manifest and candidate folder."""

    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.review = tmp / "review.json"
        self.data = tmp / "data.json"
        self.review.write_bytes(own_results.dumps(own_results.empty_review()))

    def candidate(self, name: str, value) -> Path:
        path = self.tmp / name
        path.write_bytes(value if isinstance(value, bytes) else own_results.dumps(value))
        return path

    def admit(self, path: Path, at="2026-09-28T09:00:00Z") -> None:
        review = json.loads(self.review.read_text(encoding="utf-8"))
        digest = own_results.sha256_bytes(Path(path).read_bytes())
        if any(e["sha256"] == digest for e in review["admitted"]):
            return
        review["admitted"] = sorted(review["admitted"] + [{"sha256": digest, "reviewed_at": at}], key=lambda e: e["sha256"])
        self.review.write_bytes(own_results.dumps(review))

    def run(self, path: Path) -> str:
        return own_results.import_bundle(path, self.review, self.data)


class ValidatorTests(unittest.TestCase):
    def test_fixtures_are_valid_bundles(self):
        for name in ("daily-part1.json", "daily-part2.json", "calibration.json"):
            with self.subTest(fixture=name):
                own_results.validate_bundle(fixture(name))

    def bad(self, label, bundle, now=None):
        with self.subTest(case=label), self.assertRaises(own_results.OwnResultsError):
            own_results.validate_bundle(bundle, now)

    def test_record_contract_violations_are_refused(self):
        good = fixture("daily-part1.json")

        def with_record(index=0, **changes):
            b = copy.deepcopy(good)
            b["records"][index].update(changes)
            return b
        rec = good["records"][0]
        outcomes = rec["first_attempt_outcomes"]
        cases = {
            "raw response text": with_record(response_text="the model said ..."),
            "prompt field": with_record(prompt="What is ..."),
            "secret-shaped run id": with_record(run_id="AIza" + "Q" * 30),
            "bool as a count": with_record(first_attempt_correct=True),
            "wrong outcome sum": with_record(first_attempt_outcomes=dict(outcomes, correct=outcomes["correct"] + 1)),
            "correct not the bucket": with_record(first_attempt_correct=rec["first_attempt_correct"] - 1),
            "unknown nested outcome": with_record(first_attempt_outcomes=dict(outcomes, surprise=0)),
            "setting smuggled in": with_record(settings=dict(rec["settings"], api_key="x")),
            "nonfinite temperature": with_record(settings=dict(rec["settings"], temperature=float("inf"))),
            "verified without counts": with_record(first_attempt_correct=None),
            "unavailable with counts": with_record(evidence="unavailable"),
            "free-text interpretation": with_record(interpretation="<b>Stable!</b> No decline."),
            "verdict-like status": with_record(status="stable"),
            "run of another configuration": with_record(run_id=rec["run_id"][:-10] + "0" * 10),
            "run started on another day": with_record(date="2026-09-23"),
            "impossible date": with_record(date="2026-02-30"),
            "record after as_of": with_record(3, date="2026-09-25",
                                              run_id=good["records"][3]["run_id"].replace("20260924", "20260925")),
            "too many recovered": with_record(retry_recovered={"correct": 5, "incorrect": 0, "format_error": 0, "other": 0}),
            "validity flag wrong": with_record(valid_day=False),
            "gap with evidence": with_record(2, evidence="verified"),
            "panel size mismatch": with_record(scheduled_items=41),
            "model differs from route": with_record(requested_model="gemini-3.5-flash"),
            "settings differ from series": with_record(settings=dict(rec["settings"], temperature=0.5)),
        }
        for label, bundle in cases.items():
            self.bad(label, bundle)

    def test_envelope_route_and_series_violations_are_refused(self):
        good = fixture("daily-part1.json")
        cal = fixture("calibration.json")

        def change(base, path, value):
            b = copy.deepcopy(base)
            target = b
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            return b
        cases = {
            "self-asserted review": dict(copy.deepcopy(good), reviewed=True),
            "unknown format": change(good, ("format",), "something-else"),
            "non-canonical as_of": change(good, ("as_of",), "2026-09-24 12:00"),
            "account detail on route": change(good, ("route", "account"), "someone"),
            "app access kind": change(good, ("route", "access_kind"), "consumer_app"),
            "html in maker": change(good, ("route", "maker"), "<script>"),
            "series notes free text": change(good, ("series", "notes"), "Looks fine"),
            "series id not bound": change(good, ("series", "series_id"), "gemini-api.x--daily--abababababab"),
            "calibration with campaign dates": change(cal, ("series", "schedule"), good["series"]["schedule"]),
            "campaign end before start": change(good, ("series", "schedule", "end_date"), "2026-09-01"),
            "duplicate date": change(good, ("records",), good["records"] + [good["records"][0]]),
            "outside campaign": change(change(good, ("series", "schedule", "start_date"), "2026-09-21"),
                                       ("series", "schedule", "end_date"), "2026-09-30"),
            "calibration gap": change(cal, ("records",), [dict(cal["records"][0], status="gap", run_id=None,
                                                               report_sha256=None, evidence="none",
                                                               **{k: None for k in own_results.COUNTS})]),
            "no records": change(good, ("records",), []),
            "too many records": change(good, ("records",), good["records"] * 101),
        }
        for label, bundle in cases.items():
            self.bad(label, bundle)
        from datetime import datetime, timezone
        self.bad("as_of in the future", good, now=datetime(2026, 9, 20, tzinfo=timezone.utc))

    def test_nonfinite_numbers_and_oversized_files_are_refused_while_parsing(self):
        for raw in (b'{"temperature": NaN}', b'{"x": Infinity}', b"\xff\xfe", b"x" * (own_results.MAX_BYTES + 1)):
            with self.subTest(raw=raw[:20]), self.assertRaises(own_results.OwnResultsError):
                own_results.parse_json(raw, "candidate")


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.ws = Workspace(Path(self.tmpdir.name))

    def tearDown(self):
        self.tmpdir.cleanup()

    def assertRefusedAndUnchanged(self, path, pattern):
        before = self.ws.data.read_bytes() if self.ws.data.exists() else None
        with self.assertRaisesRegex(own_results.OwnResultsError, pattern):
            self.ws.run(path)
        self.assertEqual(self.ws.data.read_bytes() if self.ws.data.exists() else None, before)

    def test_unadmitted_candidates_are_refused_before_anything_is_written(self):
        path = self.ws.candidate("c.json", fixture("daily-part1.json"))
        self.assertRefusedAndUnchanged(path, "not admitted")
        self.assertFalse(self.ws.data.exists())

    def test_import_is_idempotent(self):
        path = self.ws.candidate("c.json", fixture("daily-part1.json"))
        self.ws.admit(path)
        self.assertEqual(self.ws.run(path), "updated")
        first, mtime = self.ws.data.read_bytes(), os.stat(self.ws.data).st_mtime_ns
        self.assertEqual(self.ws.run(path), "unchanged")
        self.assertEqual((self.ws.data.read_bytes(), os.stat(self.ws.data).st_mtime_ns), (first, mtime))
        dataset = own_results.load_admitted(self.ws.data, self.ws.review)
        self.assertEqual(len(dataset["sources"]), 1)

    def import_both(self, order):
        paths = {n: self.ws.candidate(n, fixture(n)) for n in ("daily-part1.json", "daily-part2.json")}
        for name in order:
            self.ws.admit(paths[name])
        for name in order:
            self.ws.run(paths[name])
        return self.ws.data.read_bytes()

    def test_overlapping_and_out_of_order_imports_give_the_same_history(self):
        forward = self.import_both(["daily-part1.json", "daily-part2.json"])
        self.ws.data.unlink()
        shutil.rmtree(self.ws.tmp / "admitted")
        self.ws.review.write_bytes(own_results.dumps(own_results.empty_review()))
        backward = self.import_both(["daily-part2.json", "daily-part1.json"])
        self.assertEqual(forward, backward)
        dataset = json.loads(forward)
        (body,) = dataset["series"].values()
        self.assertEqual([r["date"] for r in body["records"]],
                         ["2026-09-20", "2026-09-21", "2026-09-22", "2026-09-24", "2026-09-25", "2026-09-26", "2026-09-27"])
        self.assertEqual(body["as_of"], "2026-09-27T12:00:00Z")

    def test_a_published_run_cannot_be_silently_revised(self):
        self.import_both(["daily-part1.json"])
        revised = fixture("daily-part2.json")
        stopped = revised["records"][0]                         # 2026-09-24 also appears in part 1
        stopped["first_attempt_outcomes"].update(correct=28, incorrect=2)
        stopped["first_attempt_correct"] = 28
        path = self.ws.candidate("revised.json", revised)
        self.ws.admit(path)
        self.assertRefusedAndUnchanged(path, "correction")

    def test_a_second_run_for_a_published_date_is_refused(self):
        self.import_both(["daily-part1.json"])
        other = fixture("daily-part1.json")
        rec = other["records"][0]
        rec["run_id"] = rec["run_id"].replace("T021700Z", "T023000Z")
        path = self.ws.candidate("other.json", other)
        self.ws.admit(path)
        self.assertRefusedAndUnchanged(path, "already has a different published record")

    def test_changed_series_details_are_refused(self):
        self.import_both(["daily-part1.json"])
        changed = fixture("daily-part2.json")
        changed["series"]["grader_version"] = "grader-v1"
        path = self.ws.candidate("changed.json", changed)
        self.ws.admit(path)
        self.assertRefusedAndUnchanged(path, "different route or series details")

    def test_invalid_admitted_bundle_and_damaged_output_keep_last_known_good(self):
        self.import_both(["daily-part1.json"])
        broken = fixture("daily-part2.json")
        broken["records"][1]["first_attempt_correct"] = 3          # unavailable evidence with a count
        path = self.ws.candidate("broken.json", broken)
        self.ws.admit(path)
        self.assertRefusedAndUnchanged(path, "counts without verified evidence")
        good = self.ws.candidate("good.json", fixture("daily-part2.json"))
        self.ws.admit(good)
        damaged = json.loads(self.ws.data.read_text(encoding="utf-8"))
        damaged["series"][next(iter(damaged["series"]))]["records"][0]["first_attempt_correct"] = 99
        self.ws.data.write_bytes(own_results.dumps(damaged))
        self.assertRefusedAndUnchanged(good, "first_attempt_correct")

    def test_import_keeps_the_exact_admitted_bytes(self):
        path = self.ws.candidate("c.json", fixture("calibration.json"))
        self.ws.admit(path)
        self.ws.run(path)
        digest = own_results.sha256_bytes(path.read_bytes())
        self.assertEqual(sorted(p.name for p in (self.ws.tmp / "admitted").iterdir()), [f"{digest}.json"])
        self.assertEqual((self.ws.tmp / "admitted" / f"{digest}.json").read_bytes(), path.read_bytes())

    def test_the_review_manifest_is_strict(self):
        path = self.ws.candidate("c.json", fixture("calibration.json"))
        digest = own_results.sha256_bytes(path.read_bytes())
        for label, review in {
            "self-approval flag": dict(own_results.empty_review(), admitted=[{"sha256": digest, "reviewed_at": "2026-09-28T09:00:00Z",
                                                                               "reviewed": True}]),
            "bad timestamp": dict(own_results.empty_review(), admitted=[{"sha256": digest, "reviewed_at": "yesterday"}]),
            "not a digest": dict(own_results.empty_review(), admitted=[{"sha256": "abc", "reviewed_at": "2026-09-28T09:00:00Z"}]),
        }.items():
            with self.subTest(case=label):
                self.ws.review.write_bytes(own_results.dumps(review))
                self.assertRefusedAndUnchanged(path, "")

    def test_dataset_sources_must_be_admitted(self):
        path = self.ws.candidate("c.json", fixture("calibration.json"))
        self.ws.admit(path)
        self.ws.run(path)
        own_results.load_admitted(self.ws.data, self.ws.review)
        self.ws.review.write_bytes(own_results.dumps(own_results.empty_review()))      # admission withdrawn
        with self.assertRaisesRegex(own_results.OwnResultsError, "not admitted"):
            own_results.load_admitted(self.ws.data, self.ws.review)

    def test_fixtures_can_never_enter_the_production_dataset(self):
        path = self.ws.candidate("c.json", fixture("calibration.json"))
        self.ws.admit(path)
        with mock.patch.object(own_results, "REVIEW_PATH", self.ws.review):
            self.assertRefusedAndUnchanged(path, "synthetic test fixture")
        self.assertTrue({own_results.sha256_bytes((FIXTURES / n).read_bytes())
                         for n in ("daily-part1.json", "daily-part2.json", "calibration.json")}
                        <= own_results.fixture_digests())


class ReviewR1BindingTests(unittest.TestCase):
    """T12 review R1: published records must be exactly what admitted, reviewed candidates give."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.ws = Workspace(Path(self.tmpdir.name))
        self.paths = [self.ws.candidate(n, fixture(n)) for n in ("calibration.json", "daily-part1.json")]
        for path in self.paths:
            self.ws.admit(path)
        for path in self.paths:
            self.ws.run(path)
        self.good = self.ws.data.read_bytes()
        self.admitted = self.ws.tmp / "admitted"

    def tearDown(self):
        self.tmpdir.cleanup()

    def edit(self, change):
        data = json.loads(self.good)
        change(data)
        self.ws.data.write_bytes(own_results.dumps(data))

    def assertRefused(self, pattern=""):
        with self.assertRaisesRegex(own_results.OwnResultsError, pattern):
            own_results.load_admitted(self.ws.data, self.ws.review)
        release_check = importlib.import_module("release_check")
        page = {"catalog": catalog_entries(), "own_results_preview": False, "baseline_tests": {}}
        problems = release_check.inspect_own_results(page, self.ws.data, self.ws.review)
        self.assertTrue(any("not publishable" in p for p in problems), problems)
        # A further import is refused too and leaves the edited state for review.
        before = self.ws.data.read_bytes()
        extra = self.ws.candidate("part2.json", fixture("daily-part2.json"))
        self.ws.admit(extra)
        with self.assertRaises(own_results.OwnResultsError):
            self.ws.run(extra)
        self.assertEqual(self.ws.data.read_bytes(), before)

    def calibration(self, data):
        return next(b for b in data["series"].values() if b["series"]["kind"] == "calibration")

    def test_the_review_reproduction_an_internally_consistent_edited_score(self):
        def lower(data):
            rec = self.calibration(data)["records"][0]
            rec["first_attempt_correct"] -= 1                               # 31 -> 30
            rec["first_attempt_outcomes"]["correct"] -= 1
            rec["first_attempt_outcomes"]["incorrect"] += 1
        self.edit(lower)
        own_results.validate_dataset(json.loads(self.ws.data.read_bytes()))  # still well formed on its own
        self.assertRefused("does not match a rebuild")

    def test_added_unreviewed_records_are_refused(self):
        def add(data):
            daily = next(b for b in data["series"].values() if b["series"]["kind"] == "daily")
            daily["records"].append(fixture("daily-part2.json")["records"][3])
            daily["as_of"] = "2026-09-27T12:00:00Z"
        self.edit(add)
        self.assertRefused("does not match a rebuild")

    def test_changed_route_or_settings_are_refused(self):
        def settings(data):
            body = self.calibration(data)
            body["series"]["settings"]["temperature"] = 0.5
            for r in body["records"]:
                r["settings"]["temperature"] = 0.5
        self.edit(settings)
        self.assertRefused("does not match a rebuild")
        self.ws.data.write_bytes(self.good)
        own_results.load_admitted(self.ws.data, self.ws.review)               # the original still loads

    def test_removed_substituted_or_extra_admitted_copies_are_refused(self):
        copy_path = self.admitted / f"{own_results.sha256_bytes(self.paths[0].read_bytes())}.json"
        original = copy_path.read_bytes()
        copy_path.unlink()
        self.assertRefused("missing")
        substitute = fixture("calibration.json")
        substitute["records"][0]["first_attempt_outcomes"].update(correct=30, incorrect=6)
        substitute["records"][0]["first_attempt_correct"] = 30
        copy_path.write_bytes(own_results.dumps(substitute))
        self.assertRefused("altered or substituted")
        copy_path.write_bytes(original)
        (self.admitted / ("0" * 64 + ".json")).write_bytes(original)
        self.assertRefused("unexpected")
        (self.admitted / ("0" * 64 + ".json")).unlink()
        own_results.load_admitted(self.ws.data, self.ws.review)

    def test_removing_a_source_with_its_records_is_refused(self):
        def drop(data):
            sid = next(k for k, b in data["series"].items() if b["series"]["kind"] == "calibration")
            digest = own_results.sha256_bytes(self.paths[0].read_bytes())
            del data["series"][sid]
            data["sources"] = [s for s in data["sources"] if s["sha256"] != digest]
        self.edit(drop)
        self.assertRefused("unexpected")

    def test_valid_history_still_imports_and_rebuilds(self):
        extra = self.ws.candidate("part2.json", fixture("daily-part2.json"))
        self.ws.admit(extra)
        self.assertEqual(self.ws.run(extra), "updated")
        self.assertEqual(self.ws.run(extra), "unchanged")
        self.assertEqual(self.ws.run(self.paths[0]), "unchanged")
        own_results.load_admitted(self.ws.data, self.ws.review)


class SiteSummaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entries = catalog_entries()

    def dataset(self, *names):
        dataset = own_results.empty_dataset()
        for name in names:
            dataset = own_results.merge(dataset, fixture(name), {"sha256": own_results.sha256_bytes((FIXTURES / name).read_bytes()),
                                                                "reviewed_at": "2026-09-28T09:00:00Z"})
        own_results.validate_dataset(dataset)
        return dataset

    def test_daily_rows_keep_gaps_missing_dates_and_failures_distinct(self):
        tests = own_results.site_tests(self.dataset("daily-part1.json", "daily-part2.json", "calibration.json"), self.entries)
        rec = tests["entries"][GEMINI]
        rows = rec["daily"]["rows"]
        self.assertEqual([(r["date"], r["state"]) for r in rows], [
            ("2026-09-20", "completed"), ("2026-09-21", "completed"), ("2026-09-22", "gap"), ("2026-09-23", "no_record"),
            ("2026-09-24", "stopped"), ("2026-09-25", "interrupted"), ("2026-09-26", "completed"), ("2026-09-27", "completed")])
        self.assertIsNone(rows[3]["record"])                                       # never filled in
        self.assertEqual(rows[5]["record"]["evidence"], "unavailable")
        self.assertEqual(rec["daily"]["not_yet_due"], 3)                           # 28-30 Sep after as_of
        self.assertEqual((rec["runs"], rec["latest_run"], rec["latest_attempt"]), (4, "2026-09-27", "ok"))
        self.assertEqual(rec["baseline_complete"], False)

    def test_calibration_stays_separate_from_daily_counts(self):
        tests = own_results.site_tests(self.dataset("calibration.json"), self.entries)
        rec = tests["entries"][GEMINI]
        self.assertEqual((tests["runs"], tests["calibration_runs"], rec["runs"], rec["daily"], rec["latest_attempt"]),
                         (0, 1, 0, None, None))
        self.assertEqual(rec["calibration"][0]["kind"], "calibration")
        both = own_results.site_tests(self.dataset("daily-part1.json", "calibration.json"), self.entries)
        self.assertEqual(both["entries"][GEMINI]["runs"], 2)                    # calibration not added
        self.assertEqual(len(both["methods"]), 1)                                # same question set and settings, one method

    def test_a_failed_latest_date_is_not_reported_as_ok(self):
        part = fixture("daily-part2.json")
        part["records"] = part["records"][:2]                                   # up to the interrupted 25 Sep
        part["as_of"] = "2026-09-25T12:00:00Z"
        dataset = own_results.merge(own_results.empty_dataset(), part, None)
        rec = own_results.site_tests(dataset, self.entries)["entries"][GEMINI]
        self.assertEqual((rec["latest_attempt"], rec["runs"]), ("failed", 0))  # stopped day invalid, interrupted unavailable
        part["as_of"] = "2026-09-26T12:00:00Z"                                 # 26 Sep due but nothing recorded
        part["records"] = part["records"][:1] + [fixture("daily-part2.json")["records"][1]]
        rec = own_results.site_tests(own_results.merge(own_results.empty_dataset(), part, None), self.entries)["entries"][GEMINI]
        self.assertEqual(rec["daily"]["rows"][-1]["state"], "no_record")
        self.assertEqual(rec["latest_attempt"], "failed")

    def test_window_not_yet_closed_is_not_due(self):
        schedule = fixture("daily-part1.json")["series"]["schedule"]
        due, later = own_results.expected_dates(schedule, own_results.parse_stamp("2026-09-21T02:59:00Z"))
        self.assertEqual((due, later), (["2026-09-20"], 10))
        due, later = own_results.expected_dates(schedule, own_results.parse_stamp("2026-09-21T03:00:00Z"))
        self.assertEqual((due, later), (["2026-09-20", "2026-09-21"], 9))

    def test_results_attach_only_to_the_exact_api_entry(self):
        tests = own_results.site_tests(self.dataset("daily-part1.json", "calibration.json"), self.entries)
        self.assertEqual(list(tests["entries"]), [GEMINI])
        others = [e for e in self.entries if e["maker"] == "Google" and e["id"] != GEMINI]
        self.assertTrue(any(e["access_kind"] == "consumer_app" for e in others))       # the app exists but gets nothing
        unknown = fixture("calibration.json")
        unknown["route"]["exact_identifier"] = "gemini-9-ultra"
        for r in unknown["records"]:
            r["requested_model"] = "gemini-9-ultra"
        with self.assertRaisesRegex(own_results.OwnResultsError, "matches 0 catalogue entries"):
            own_results.site_tests(own_results.merge(own_results.empty_dataset(), unknown, None), self.entries)
        family = [dict(e, identity_kind="family") if e["id"] == GEMINI else e for e in self.entries]
        with self.assertRaises(own_results.OwnResultsError):
            own_results.site_tests(self.dataset("calibration.json"), family)


class ProductionDatasetTests(unittest.TestCase):
    def test_production_dataset_is_admitted_and_fixture_free(self):
        dataset = own_results.load_admitted()
        review = own_results.load_review()
        self.assertFalse(own_results.fixture_digests() & {e["sha256"] for e in review["admitted"]})
        blob = json.dumps(dataset)
        for fingerprint in ("ab" * 32, "cd" * 32, "0f" * 32):                   # the fixtures' synthetic hashes
            self.assertNotIn(fingerprint, blob)
        own_results.site_tests(dataset, catalog_entries())

    def test_public_module_needs_no_private_runner(self):
        code = ("import sys; sys.path.insert(0, 'scripts'); import own_results, build_site, release_check; "
                "print(sorted(m for m in ('cloud_pilot', 'cloud_aggregate', 'daily_pilot', 'gemini_pilot', "
                "'gemini_adapter', 'pilot_ledger', 'collector', 'export_own_results') if m in sys.modules))")
        result = subprocess.run([sys.executable, "-B", "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "[]")
        source = (ROOT / "scripts" / "own_results.py").read_text(encoding="utf-8")
        self.assertNotIn("pilot/", source)


class CliTests(unittest.TestCase):
    def test_check_inspect_and_import_commands(self):
        import contextlib
        import io
        with tempfile.TemporaryDirectory() as folder:
            ws = Workspace(Path(folder))
            path = ws.candidate("c.json", fixture("calibration.json"))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(own_results.main(["inspect", str(path)]), 0)
                self.assertEqual(own_results.main(["import", str(path), "--review", str(ws.review), "--data", str(ws.data)]), 1)
                ws.admit(path)
                self.assertEqual(own_results.main(["import", str(path), "--review", str(ws.review), "--data", str(ws.data)]), 0)
                self.assertEqual(own_results.main(["check", "--review", str(ws.review), "--data", str(ws.data)]), 0)
            text = out.getvalue()
            self.assertIn(own_results.sha256_bytes(path.read_bytes()), text)
            self.assertIn("31 of 40 first attempts correct", text)
            self.assertIn("not admitted", text)


if __name__ == "__main__":
    unittest.main()
