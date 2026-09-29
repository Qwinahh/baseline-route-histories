import copy
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("registry", ROOT / "scripts" / "registry.py")
registry = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(registry)

FIXTURES = ROOT / "tests" / "fixtures" / "registry_valid"
NOW = datetime(2026, 9, 28, 15, 0, tzinfo=timezone.utc)


def fixture_records():
    records, errors = registry.load_registry(FIXTURES)
    assert not errors, errors
    return copy.deepcopy(records)


def errors_for(records):
    return registry.validate_records(records, fixture_mode=True, now=NOW)


def by_id(records, kind):
    return {record["id"]: record for record in records[kind]}


def fingerprint(records, series):
    return registry.series_fingerprint(series, by_id(records, "routes"), by_id(records, "models"))


def refingerprint(records, series):
    series["fingerprint"] = fingerprint(records, series)


class ValidRegistryTests(unittest.TestCase):
    def test_labelled_fixtures_pass_in_fixture_mode(self):
        self.assertEqual(registry.validate_registry(FIXTURES, fixture_mode=True, now=NOW), [])

    def test_production_registry_passes(self):
        # Real clock: production records carry real retrieval times.
        self.assertEqual(registry.validate_registry(ROOT / "registry"), [])

    def test_production_registry_has_no_numeric_observations_from_link_only_source(self):
        records, _ = registry.load_registry(ROOT / "registry")
        link_only = {s["id"] for s in records["sources"] if s["reuse_decision"] != "numeric_republication_permitted"}
        self.assertIn("livenerf", link_only)
        series_sources = {s["id"]: s["source_id"] for s in records["series"]}
        self.assertFalse([o["id"] for o in records["observations"]
                          if series_sources.get(o["series_id"]) in link_only])


class IsolationTests(unittest.TestCase):
    def test_fixtures_rejected_in_production_mode(self):
        errors = registry.validate_registry(FIXTURES, fixture_mode=False, now=NOW)
        self.assertTrue(errors)
        self.assertTrue(all("test fixture found in production registry" in e for e in errors))

    def test_unlabelled_record_rejected_in_fixture_set(self):
        records = fixture_records()
        del records["observations"][0]["fixture"]
        self.assertTrue(any("fixture sets need fixture: true" in e for e in errors_for(records)))

    def test_fixture_prefix_alone_rejected_in_production(self):
        records = fixture_records()
        for kind in records:
            for record in records[kind]:
                record.pop("fixture", None)
        errors = registry.validate_records(records, fixture_mode=False, now=NOW)
        self.assertTrue(any("test fixture found in production registry" in e for e in errors))


class RequiredFieldTests(unittest.TestCase):
    def test_missing_route_rejected(self):
        records = fixture_records()
        records["routes"] = []
        self.assertTrue(any("unknown routes id" in e for e in errors_for(records)))

    def test_missing_route_field_on_series_rejected(self):
        records = fixture_records()
        del records["series"][0]["route_id"]
        self.assertTrue(any("route_id: missing required field" in e for e in errors_for(records)))

    def test_missing_source_rejected(self):
        records = fixture_records()
        records["series"][0]["source_id"] = "fixture-no-such-source"
        refingerprint(records, records["series"][0])
        self.assertTrue(any("unknown sources id" in e for e in errors_for(records)))

    def test_missing_observation_date_rejected(self):
        records = fixture_records()
        del records["observations"][0]["observed_at"]
        self.assertTrue(any("observed_at: missing required field" in e for e in errors_for(records)))

    def test_missing_retrieval_date_rejected(self):
        records = fixture_records()
        del records["observations"][0]["retrieved_at"]
        self.assertTrue(any("retrieved_at: missing required field" in e for e in errors_for(records)))

    def test_missing_evidence_url_rejected(self):
        records = fixture_records()
        del records["observations"][0]["evidence_url"]
        self.assertTrue(any("evidence_url: missing required field" in e for e in errors_for(records)))

    def test_unknown_field_rejected(self):
        records = fixture_records()
        records["observations"][0]["score"] = 99
        self.assertTrue(any("unknown field 'score'" in e for e in errors_for(records)))

    def test_unknown_release_date_allowed_but_must_be_explicit(self):
        records = fixture_records()
        self.assertIsNone(records["models"][0]["release_date"])
        self.assertEqual(errors_for(records), [])
        del records["models"][0]["release_date"]
        self.assertTrue(any("release_date: missing required field" in e for e in errors_for(records)))


class TimestampTests(unittest.TestCase):
    def test_non_utc_timestamp_rejected(self):
        records = fixture_records()
        records["observations"][0]["observed_at"] = "2026-01-01T12:00:00+10:00"
        self.assertTrue(any("must be a UTC timestamp" in e for e in errors_for(records)))

    def test_impossible_timestamp_rejected(self):
        records = fixture_records()
        records["observations"][0]["observed_at"] = "2026-02-30T12:00:00Z"
        self.assertTrue(any("not a real date/time" in e for e in errors_for(records)))

    def test_future_timestamp_rejected(self):
        records = fixture_records()
        records["observations"][0]["retrieved_at"] = "2027-01-01T00:00:00Z"
        self.assertTrue(any("is in the future" in e for e in errors_for(records)))

    def test_retrieved_before_observed_rejected(self):
        records = fixture_records()
        records["observations"][0]["retrieved_at"] = "2025-12-31T00:00:00Z"
        self.assertTrue(any("retrieved_at is earlier than observed_at" in e for e in errors_for(records)))

    def test_old_observation_retrieved_later_keeps_its_own_date(self):
        records = fixture_records()
        obs = records["observations"][0]
        self.assertNotEqual(obs["observed_at"], obs["retrieved_at"])
        self.assertEqual(errors_for(records), [])


class IntegrityTests(unittest.TestCase):
    def test_duplicate_id_rejected(self):
        records = fixture_records()
        records["observations"][1]["id"] = records["observations"][0]["id"]
        self.assertTrue(any("duplicate id" in e for e in errors_for(records)))

    def test_duplicate_observation_moment_rejected(self):
        records = fixture_records()
        records["observations"][1]["observed_at"] = records["observations"][0]["observed_at"]
        self.assertTrue(any("same series and observed_at" in e for e in errors_for(records)))

    def test_editing_series_configuration_breaks_fingerprint(self):
        records = fixture_records()
        records["series"][0]["suite_version"] = "2"
        self.assertTrue(any("fingerprint: does not match" in e for e in errors_for(records)))

    def test_route_change_cannot_silently_join_series(self):
        records = fixture_records()
        before = fingerprint(records, records["series"][0])
        records["series"][0]["route_id"] = "fixture-route-other"
        self.assertNotEqual(before, fingerprint(records, records["series"][0]))

    def test_duplicate_series_configuration_rejected(self):
        records = fixture_records()
        clone = copy.deepcopy(records["series"][0])
        clone["id"] = "fixture-series-b"
        records["series"].append(clone)
        self.assertTrue(any("same configuration as series" in e for e in errors_for(records)))

    def test_numeric_observation_from_link_only_source_rejected(self):
        records = fixture_records()
        records["sources"][0]["reuse_decision"] = "link_and_summary_only"
        self.assertTrue(any("numeric metrics may not be stored" in e for e in errors_for(records)))

    def test_invalid_metric_shapes_rejected(self):
        for metric in ({"name": "acc", "numerator": 41, "denominator": 40},
                       {"name": "acc", "numerator": 1, "denominator": 0},
                       {"name": "acc", "value": 0.7},
                       {"name": "acc"}):
            records = fixture_records()
            records["observations"][0]["metric"] = metric
            self.assertTrue(any(".metric:" in e for e in errors_for(records)), metric)

    def test_bad_exclusion_counts_rejected(self):
        records = fixture_records()
        records["observations"][0]["exclusions"] = {"refusal": -1, "timeout": 2}
        errors = errors_for(records)
        self.assertTrue(any("non-negative integer" in e for e in errors))
        self.assertTrue(any("unknown exclusion kind" in e for e in errors))


class ReviewRegressionTests(unittest.TestCase):
    """T01 review R1-R4 (docs/T01_REVIEW.md)."""

    def assert_fingerprint_breaks(self, mutate):
        records = fixture_records()
        mutate(records)
        self.assertTrue(any("fingerprint: does not match" in e for e in errors_for(records)))

    def test_r1_route_settings_change_breaks_fingerprint(self):
        self.assert_fingerprint_breaks(lambda r: r["routes"][0]["settings"].update(temperature=0.99))

    def test_r1_requested_model_change_breaks_fingerprint(self):
        self.assert_fingerprint_breaks(lambda r: r["routes"][0].update(requested_model="other"))

    def test_r1_exact_identifier_change_breaks_fingerprint(self):
        self.assert_fingerprint_breaks(lambda r: r["models"][0].update(exact_identifier="other"))

    def test_r1_other_route_fields_break_fingerprint(self):
        for field, value in (("service", "other service"), ("access_type", "intermediary"),
                             ("tier", "free"), ("region", "eu")):
            with self.subTest(field=field):
                self.assert_fingerprint_breaks(lambda r: r["routes"][0].update({field: value}))

    def test_r1_new_configuration_is_a_distinct_series(self):
        records = fixture_records()
        old_series = copy.deepcopy(records["series"][0])
        route = copy.deepcopy(records["routes"][0])
        route["id"] = "fixture-route-a-api-t099"
        route["settings"] = {"temperature": 0.99}
        records["routes"].append(route)
        series = copy.deepcopy(old_series)
        series["id"] = "fixture-series-a-t099"
        series["route_id"] = route["id"]
        refingerprint(records, series)
        records["series"].append(series)
        self.assertEqual(errors_for(records), [])
        self.assertEqual(records["series"][0], old_series)
        self.assertNotEqual(series["fingerprint"], old_series["fingerprint"])

    def test_r1_source_check_metadata_does_not_break_fingerprint(self):
        records = fixture_records()
        records["sources"][0]["last_successful_check"] = "2026-09-01T00:00:00Z"
        self.assertEqual(errors_for(records), [])

    def test_r2_non_finite_metric_values_rejected(self):
        for value in (float("nan"), float("inf"), float("-inf"), json.loads("1e309")):
            with self.subTest(value=value):
                records = fixture_records()
                records["observations"][1]["metric"] = {"name": "score", "value": value, "unit": "points"}
                self.assertTrue(any("must be finite" in e for e in errors_for(records)))

    def test_r2_non_finite_metric_in_file_fails_cli_style_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "reg"
            shutil.copytree(FIXTURES, target)
            path = target / "observations.jsonl"
            path.write_text(path.read_text(encoding="utf-8").replace('"value": 1.5', '"value": 1e309'),
                            encoding="utf-8")
            errors = registry.validate_registry(target, fixture_mode=True, now=NOW)
        self.assertTrue(any("must be finite" in e for e in errors))

    def test_r2_finite_metric_still_passes(self):
        records = fixture_records()
        records["observations"][1]["metric"] = {"name": "score", "value": -2.5e10, "unit": "points"}
        self.assertEqual(errors_for(records), [])

    def test_r3_equivalent_timestamp_spellings_are_duplicates(self):
        for suffix in (".000000Z", ".000Z", ".0Z"):
            with self.subTest(suffix=suffix):
                records = fixture_records()
                clone = copy.deepcopy(records["observations"][0])
                clone["id"] = "fixture-obs-3"
                clone["observed_at"] = clone["observed_at"][:-1] + suffix
                records["observations"].append(clone)
                self.assertTrue(any("same series and observed_at" in e for e in errors_for(records)))

    def test_r3_distinct_instants_pass(self):
        records = fixture_records()
        clone = copy.deepcopy(records["observations"][0])
        clone["id"] = "fixture-obs-3"
        clone["observed_at"] = clone["observed_at"][:-1] + ".5Z"
        records["observations"].append(clone)
        self.assertEqual(errors_for(records), [])

    def test_r4_malformed_types_are_errors_not_crashes(self):
        cases = (("models", "availability"), ("sources", "reuse_decision"),
                 ("routes", "access_type"), ("routes", "model_id"),
                 ("series", "route_id"), ("series", "source_id"),
                 ("observations", "series_id"), ("observations", "observed_at"),
                 ("observations", "retrieved_at"), ("observations", "id"))
        for kind, field in cases:
            for bad in ([], {}, 7, None):
                with self.subTest(kind=kind, field=field, bad=bad):
                    records = fixture_records()
                    records[kind][0][field] = bad
                    errors = errors_for(records)
                    self.assertTrue(any(f".{field}:" in e for e in errors), errors)

    def test_r4_malformed_file_gives_cli_exit_1_without_traceback(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "reg"
            shutil.copytree(FIXTURES, target)
            path = target / "models.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data["records"][0]["availability"] = []
            path.write_text(json.dumps(data), encoding="utf-8")
            result = subprocess.run([sys.executable, "-B", str(ROOT / "scripts" / "registry.py"),
                                     str(target), "--fixtures"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("availability: must be one of", result.stdout)
        self.assertNotIn("Traceback", result.stdout + result.stderr)


class FileLoadingTests(unittest.TestCase):
    def copy_fixtures(self, folder):
        target = Path(folder) / "reg"
        shutil.copytree(FIXTURES, target)
        return target

    def test_missing_file_reported(self):
        with tempfile.TemporaryDirectory() as folder:
            target = self.copy_fixtures(folder)
            (target / "routes.json").unlink()
            errors = registry.validate_registry(target, fixture_mode=True, now=NOW)
        self.assertIn("routes.json: missing", errors)

    def test_wrong_schema_version_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            target = self.copy_fixtures(folder)
            path = target / "models.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data["schema_version"] = 1
            path.write_text(json.dumps(data), encoding="utf-8")
            errors = registry.validate_registry(target, fixture_mode=True, now=NOW)
        self.assertTrue(any("schema_version 1" in e for e in errors))

    def test_malformed_jsonl_line_reported(self):
        with tempfile.TemporaryDirectory() as folder:
            target = self.copy_fixtures(folder)
            with open(target / "observations.jsonl", "a", encoding="utf-8") as handle:
                handle.write("{not json\n")
            errors = registry.validate_registry(target, fixture_mode=True, now=NOW)
        self.assertTrue(any("observations.jsonl:3: invalid JSON" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
