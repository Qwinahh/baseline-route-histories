"""T02 ingestion tests. Offline: network access is replaced by a stub `get`."""
import copy
from datetime import datetime, timezone
import hashlib
import importlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import types
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
registry = importlib.import_module("registry")
aider_polyglot = importlib.import_module("aider_polyglot")
ingest = importlib.import_module("ingest")

NOW = datetime(2026, 9, 28, 15, 0, tzinfo=timezone.utc)
LATER = datetime(2026, 12, 31, tzinfo=timezone.utc)  # validation clock after every test run
REV_A = "a" * 40
REV_B = "b" * 40
SELECTED = ("deepseek/fixture-chat",)
FIXTURE_LICENCE = b"Apache License fixture text\n"

# Synthetic rows (not real results). Model names are fixture names.
ROW_TEMPLATE = """- dirname: {dirname}
  test_cases: {cases}
  model: Fixture Chat {label}
  edit_format: diff
  commit_hash: abc1234
  pass_rate_1: 10.0
  pass_rate_2: {rate}
  pass_num_1: 10
  pass_num_2: {passed}
  total_tests: 100
  command: {command}
  date: {date}
  versions: {versions}
  total_cost: 0 # fixture comment
"""


def row(dirname, date, passed, cases=100, command="aider --model deepseek/fixture-chat", label="A",
        versions="0.1.0"):
    rate = round(100 * passed / cases, 1)
    return ROW_TEMPLATE.format(dirname=dirname, date=date, passed=passed, cases=cases,
                               rate=rate, command=command, label=label, versions=versions)


def fixture_adapter():
    """The real adapter with a synthetic model selection."""
    adapter = types.SimpleNamespace(**{k: getattr(aider_polyglot, k) for k in (
        "SOURCE_ID", "REPO", "DATA_PATH", "LICENSE_PATH", "ParseError", "parse_rows")})
    adapter.REVIEWED_LICENSE_SHA256 = frozenset({hashlib.sha256(FIXTURE_LICENCE).hexdigest()})
    adapter.build_records = lambda rows, meta: aider_polyglot.build_records(rows, meta, selected=SELECTED)
    return adapter


def source_record(reuse="numeric_republication_permitted"):
    return {"id": "aider-polyglot", "author": "Test", "url": "https://example.invalid/aider",
            "method": "synthetic", "access_method": "stub", "reuse_decision": reuse,
            "reuse_evidence": "synthetic test source", "revision": None,
            "retrieved_at": "2026-09-01T00:00:00Z", "expected_update_cadence": None,
            "last_successful_check": None}


class Workspace:
    """Temporary registry + evidence folders with a stub GitHub."""

    def __init__(self, reuse="numeric_republication_permitted"):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.registry = base / "registry"
        self.evidence = base / "evidence"
        self.registry.mkdir()
        for kind in registry.JSON_FILES:
            rows = [source_record(reuse)] if kind == "sources" else []
            (self.registry / f"{kind}.json").write_text(
                json.dumps({"schema_version": registry.SCHEMA_VERSION, "records": rows}), encoding="utf-8")
        for name in registry.JSONL_FILES.values():
            (self.registry / name).write_text("", encoding="utf-8")
        self.remote = {}  # revision -> yaml text
        self.head = None
        self.calls = []
        self.licence = FIXTURE_LICENCE

    def publish(self, revision, text):
        self.remote[revision] = text
        self.head = revision

    def get(self, url, accept=None):
        self.calls.append(url)
        if url.startswith("https://api.github.com/"):
            if self.head is None:
                raise OSError("simulated network failure")
            return self.head.encode()
        revision = url.split("/")[5]
        if url.endswith("LICENSE.txt"):
            return self.licence
        return self.remote[revision].encode("utf-8")

    def run(self, now=NOW, **kwargs):
        with unittest.mock.patch.dict(ingest.ADAPTERS, {"aider-polyglot": fixture_adapter()}):
            return ingest.ingest("aider-polyglot", self.registry, self.evidence,
                                 now=now, get=self.get, **kwargs)

    def records(self):
        records, errors = registry.load_registry(self.registry)
        assert not errors, errors
        return records

    def snapshot_bytes(self):
        return {p.name: p.read_bytes() for p in self.registry.iterdir()}

    def close(self):
        self.tmp.cleanup()


import unittest.mock  # noqa: E402


class IngestTestCase(unittest.TestCase):
    def setUp(self):
        self.ws = Workspace()
        self.addCleanup(self.ws.close)


class FirstIngestTests(IngestTestCase):
    def test_new_records_are_dated_valid_and_logged(self):
        self.ws.publish(REV_A, row("r1", "2025-01-02", 40) + "\n" + row("r2", "2025-02-03", 50))
        run = self.ws.run()
        self.assertEqual(run["status"], "succeeded", run["problems"])
        self.assertEqual(run["counts"]["new"], {"models": 1, "routes": 1, "series": 1, "observations": 2})
        records = self.ws.records()
        self.assertEqual(registry.validate_records(records, now=LATER), [])
        obs = {o["observed_at"]: o for o in records["observations"]}
        self.assertEqual(set(obs), {"2025-01-02", "2025-02-03"})
        first = obs["2025-01-02"]
        self.assertEqual(first["retrieved_at"], "2026-09-28T15:00:00Z")
        self.assertEqual(first["metric"], {"name": "pass_rate_2", "numerator": 40, "denominator": 100})
        self.assertEqual(first["source_revision"], REV_A)
        self.assertIn(f"/blob/{REV_A}/", first["evidence_url"])
        self.assertEqual(first["source_details"]["comment:total_cost"], "fixture comment")
        source = records["sources"][0]
        self.assertEqual((source["revision"], source["last_successful_check"]), (REV_A, "2026-09-28T15:00:00Z"))
        self.assertEqual([r["status"] for r in records["ingestion_runs"]], ["succeeded"])

    def test_snapshot_and_licence_are_preserved_with_hashes(self):
        text = row("r1", "2025-01-02", 40)
        self.ws.publish(REV_A, text)
        self.ws.run()
        folder = self.ws.evidence / "aider-polyglot" / REV_A
        meta = json.loads((folder / "SNAPSHOT.json").read_text(encoding="utf-8"))
        self.assertEqual((folder / "polyglot_leaderboard.yml").read_text(encoding="utf-8"), text)
        self.assertTrue((folder / "LICENSE.txt").is_file())
        self.assertEqual(meta["sha256"], hashlib.sha256(text.encode()).hexdigest())
        self.assertEqual(meta["revision"], REV_A)

    def test_same_configuration_joins_one_series(self):
        self.ws.publish(REV_A, row("r1", "2025-01-02", 40) + row("r2", "2025-02-03", 50))
        self.ws.run()
        records = self.ws.records()
        self.assertEqual((len(records["routes"]), len(records["series"])), (1, 1))
        self.assertEqual({o["series_id"] for o in records["observations"]}, {records["series"][0]["id"]})

    def test_changed_harness_starts_a_new_series_on_the_same_route(self):
        self.ws.publish(REV_A, row("r1", "2025-01-02", 40) + row("r2", "2025-02-03", 50, versions="0.2.0"))
        self.ws.run()
        records = self.ws.records()
        self.assertEqual((len(records["routes"]), len(records["series"])), (1, 2))
        self.assertEqual(len({s["fingerprint"] for s in records["series"]}), 2)

    def test_same_series_same_day_is_a_validation_failure(self):
        self.ws.publish(REV_A, row("r1", "2025-01-02", 40) + row("r2", "2025-01-02", 50))
        run = self.ws.run()
        self.assertEqual(run["status"], "failed")
        self.assertIn("same series and observed_at", run["problems"][-1]["message"])


class DuplicateAndCorrectionTests(IngestTestCase):
    def test_reingesting_same_snapshot_changes_nothing_but_the_run_log(self):
        self.ws.publish(REV_A, row("r1", "2025-01-02", 40))
        self.ws.run()
        before = self.ws.snapshot_bytes()
        run = self.ws.run(now=NOW.replace(hour=16))
        self.assertEqual(run["status"], "succeeded")
        self.assertEqual(sum(run["counts"]["new"].values()), 0)
        self.assertGreater(run["counts"]["duplicate"], 0)
        after = self.ws.snapshot_bytes()
        for name in ("models.json", "routes.json", "series.json", "observations.jsonl"):
            self.assertEqual(before[name], after[name], name)
        self.assertEqual(len(self.ws.records()["ingestion_runs"]), 2)

    def test_same_values_at_new_revision_keep_first_retrieval(self):
        self.ws.publish(REV_A, row("r1", "2025-01-02", 40))
        self.ws.run()
        self.ws.publish(REV_B, row("r1", "2025-01-02", 40))
        run = self.ws.run(now=NOW.replace(day=29))
        self.assertEqual(run["counts"]["conflict"], 0)
        obs = self.ws.records()["observations"]
        self.assertEqual(len(obs), 1)
        self.assertEqual(obs[0]["retrieved_at"], "2026-09-28T15:00:00Z")
        self.assertEqual(obs[0]["source_revision"], REV_A)
        self.assertEqual(self.ws.records()["sources"][0]["revision"], REV_B)

    def test_changed_value_is_preserved_as_conflict_not_overwritten(self):
        self.ws.publish(REV_A, row("r1", "2025-01-02", 40))
        self.ws.run()
        self.ws.publish(REV_B, row("r1", "2025-01-02", 45))
        run = self.ws.run(now=NOW.replace(day=29))
        self.assertEqual(run["counts"]["conflict"], 1)
        conflict = next(p for p in run["problems"] if p["type"] == "conflict")
        self.assertEqual(conflict["kept"]["metric"]["numerator"], 40)
        self.assertEqual(conflict["incoming"]["metric"]["numerator"], 45)
        self.assertEqual(self.ws.records()["observations"][0]["metric"]["numerator"], 40)
        logged = self.ws.records()["ingestion_runs"][-1]
        self.assertEqual(logged["problems"], run["problems"])

    def test_out_of_order_observation_is_accepted(self):
        self.ws.publish(REV_A, row("r2", "2025-03-01", 50))
        self.ws.run()
        self.ws.publish(REV_B, row("r2", "2025-03-01", 50) + row("r1", "2024-12-01", 30))
        run = self.ws.run(now=NOW.replace(day=29))
        self.assertEqual(run["status"], "succeeded")
        self.assertEqual([o["observed_at"] for o in self.ws.records()["observations"]],
                         ["2025-03-01", "2024-12-01"])

    def test_duplicate_row_within_snapshot_is_skipped(self):
        self.ws.publish(REV_A, row("r1", "2025-01-02", 40) + row("r1", "2025-01-02", 41))
        run = self.ws.run()
        self.assertEqual(run["counts"]["new"]["observations"], 1)
        self.assertTrue(any(p.get("reason") == "duplicate dirname within this snapshot" for p in run["problems"]))


class FailurePreservationTests(IngestTestCase):
    def assert_failed_and_unchanged(self, run, kind, before):
        self.assertEqual(run["status"], "failed")
        self.assertEqual(run["problems"][-1]["type"], kind, run["problems"])
        after = self.ws.snapshot_bytes()
        for name in before:
            if name != "ingestion_runs.jsonl":
                self.assertEqual(before[name], after[name], name)
        logged = self.ws.records()["ingestion_runs"][-1]
        self.assertEqual((logged["id"], logged["status"]), (run["id"], "failed"))
        self.assertEqual(registry.validate_records(self.ws.records(), now=LATER), [])

    def test_network_failure_is_logged(self):
        before = self.ws.snapshot_bytes()
        run = self.ws.run()
        self.assert_failed_and_unchanged(run, "fetch_error", before)
        self.assertIsNone(self.ws.records()["sources"][0]["last_successful_check"])

    def test_unparseable_source_is_logged(self):
        self.ws.publish(REV_A, "- dirname: r1\n  nested:\n    - x\n")
        before = self.ws.snapshot_bytes()
        self.assert_failed_and_unchanged(self.ws.run(), "parse_error", before)

    def test_changed_schema_rows_are_skipped_with_reasons(self):
        missing = row("r2", "2025-02-03", 50).replace("  pass_num_2: 50\n", "")
        self.ws.publish(REV_A, row("r1", "2025-01-02", 40) + missing)
        run = self.ws.run()
        self.assertEqual(run["status"], "succeeded")
        self.assertEqual(run["counts"]["skipped"], 1)
        self.assertIn("missing required keys ['pass_num_2']", run["problems"][0]["reason"])
        self.assertEqual(len(self.ws.records()["observations"]), 1)

    def test_inconsistent_rate_is_skipped(self):
        bad = row("r2", "2025-02-03", 50).replace("pass_rate_2: 50.0", "pass_rate_2: 51.0")
        self.ws.publish(REV_A, bad)
        run = self.ws.run()
        self.assertIn("does not equal", run["problems"][0]["reason"])
        self.assertEqual(self.ws.records()["observations"], [])

    def test_unsupported_command_form_is_skipped_not_guessed(self):
        command = "OPENAI_API_BASE=https://example.invalid aider --model deepseek/fixture-chat"
        self.ws.publish(REV_A, row("r1", "2025-01-02", 40, command=command))
        run = self.ws.run()
        self.assertEqual(run["problems"][0]["reason"], "unsupported command form")
        self.assertEqual(self.ws.records()["routes"], [])

    def test_link_only_source_is_refused_before_fetching(self):
        ws = Workspace(reuse="link_and_summary_only")
        self.addCleanup(ws.close)
        ws.publish(REV_A, row("r1", "2025-01-02", 40))
        run = ws.run()
        self.assertEqual(run["problems"][-1]["type"], "rights_error")
        self.assertEqual(ws.calls, [])
        self.assertEqual(ws.records()["observations"], [])

    def test_unknown_source_failure_is_logged_and_registry_stays_valid(self):
        run = ingest.ingest("no-such-source", self.ws.registry, self.ws.evidence, now=NOW, get=self.ws.get)
        self.assertEqual(run["problems"][-1]["type"], "config_error")
        self.assertEqual(registry.validate_records(self.ws.records(), now=LATER), [])

    def test_tampered_snapshot_is_rejected(self):
        self.ws.publish(REV_A, row("r1", "2025-01-02", 40))
        self.ws.run()
        folder = self.ws.evidence / "aider-polyglot" / REV_A
        (folder / "polyglot_leaderboard.yml").write_text(row("r1", "2025-01-02", 99), encoding="utf-8")
        before = self.ws.snapshot_bytes()
        self.assert_failed_and_unchanged(self.ws.run(snapshot_dir=folder), "integrity_error", before)

    def test_same_revision_with_different_content_is_rejected(self):
        self.ws.publish(REV_A, row("r1", "2025-01-02", 40))
        self.ws.run()
        self.ws.publish(REV_A, row("r1", "2025-01-02", 41))
        before = self.ws.snapshot_bytes()
        self.assert_failed_and_unchanged(self.ws.run(now=NOW.replace(hour=16)), "integrity_error", before)

    def test_validation_failure_writes_nothing(self):
        self.ws.publish(REV_A, row("r1", "2030-01-02", 40))  # future date
        before = self.ws.snapshot_bytes()
        self.assert_failed_and_unchanged(self.ws.run(), "validation_error", before)


class T02ReviewRegressionTests(IngestTestCase):
    """docs/T02_REVIEW.md R1-R3."""

    assert_failed_and_unchanged = FailurePreservationTests.assert_failed_and_unchanged

    def mapping(self, provider="DeepSeek", service="fixture service A"):
        return unittest.mock.patch.dict(aider_polyglot.PROVIDER_PREFIXES,
                                        {"deepseek": (provider, "direct_api", service)})

    def first_ingest(self):
        with self.mapping():
            self.ws.publish(REV_A, row("r1", "2025-01-02", 40))
            self.assertEqual(self.ws.run()["status"], "succeeded")
        return self.ws.snapshot_bytes()

    def assert_blocked(self, run, before, kinds):
        self.assertGreater(run["counts"]["conflict"], 0)
        self.assertEqual(sum(run["counts"]["new"].values()), 0, run["counts"])
        blocked = {p["kind"] for p in run["problems"] if p["type"] == "blocked_by_conflict"}
        self.assertTrue(set(kinds) <= blocked, run["problems"])
        after = self.ws.snapshot_bytes()
        for name in ("models.json", "routes.json", "series.json", "observations.jsonl"):
            self.assertEqual(before[name], after[name], name)

    # R1: conflicts must not admit dependent records.
    def test_r1_route_conflict_blocks_observation_for_existing_series(self):
        before = self.first_ingest()
        with self.mapping(service="fixture service B"):
            self.ws.publish(REV_B, row("r1", "2025-01-02", 40) + row("r1b", "2025-02-03", 50))
            run = self.ws.run(now=NOW.replace(day=29))
        self.assert_blocked(run, before, {"observations"})
        self.assertTrue(any(p["type"] == "conflict" and p["kind"] == "routes" for p in run["problems"]))

    def test_r1_route_conflict_blocks_newly_proposed_series(self):
        before = self.first_ingest()
        with self.mapping(service="fixture service B"):
            self.ws.publish(REV_B, row("r2", "2025-02-03", 50, versions="0.2.0"))
            run = self.ws.run(now=NOW.replace(day=29))
        self.assert_blocked(run, before, {"series", "observations"})

    def test_r1_model_conflict_blocks_dependents(self):
        before = self.first_ingest()
        with self.mapping(provider="Other Provider"):
            self.ws.publish(REV_B, row("r2", "2025-02-03", 50, versions="0.2.0"))
            run = self.ws.run(now=NOW.replace(day=29))
        self.assertTrue(any(p["type"] == "conflict" and p["kind"] == "models" for p in run["problems"]))
        self.assert_blocked(run, before, {"series", "observations"})

    def test_r1_intentional_distinct_route_is_admitted(self):
        self.first_ingest()
        with self.mapping():
            command = "aider --model deepseek/fixture-chat --reasoning-effort high"
            self.ws.publish(REV_B, row("r1", "2025-01-02", 40) + row("r2", "2025-02-03", 50, command=command))
            run = self.ws.run(now=NOW.replace(day=29))
        self.assertEqual((run["counts"]["conflict"], run["counts"]["blocked"]), (0, 0))
        self.assertEqual(run["counts"]["new"], {"models": 0, "routes": 1, "series": 1, "observations": 1})

    # R2: snapshot identity and licence integrity.
    def stored_snapshot(self):
        self.ws.publish(REV_A, row("r1", "2025-01-02", 40))
        self.ws.run()
        folder = self.ws.evidence / "aider-polyglot" / REV_A
        return folder, json.loads((folder / "SNAPSHOT.json").read_text(encoding="utf-8"))

    def rerun(self, folder, kind):
        before = self.ws.snapshot_bytes()
        self.assert_failed_and_unchanged(self.ws.run(snapshot_dir=folder, now=NOW.replace(hour=16)), kind, before)

    def edit_manifest(self, folder, meta, **changes):
        meta.update(changes)
        (folder / "SNAPSHOT.json").write_text(json.dumps(meta), encoding="utf-8")

    def test_r2_wrong_source_or_repository_rejected(self):
        for key, value in (("source_id", "unreviewed-source"), ("repository", "other/repo")):
            with self.subTest(key=key):
                self.setUp()
                folder, meta = self.stored_snapshot()
                self.edit_manifest(folder, meta, **{key: value})
                self.rerun(folder, "snapshot_error")

    def test_r2_missing_licence_rejected(self):
        folder, _ = self.stored_snapshot()
        (folder / "LICENSE.txt").unlink()
        self.rerun(folder, "integrity_error")

    def test_r2_altered_licence_rejected(self):
        folder, _ = self.stored_snapshot()
        (folder / "LICENSE.txt").write_bytes(b"Some other licence\n")
        self.rerun(folder, "integrity_error")

    def test_r2_altered_licence_with_matching_manifest_needs_rights_review(self):
        folder, meta = self.stored_snapshot()
        altered = b"Some other licence\n"
        (folder / "LICENSE.txt").write_bytes(altered)
        meta["files"]["LICENSE.txt"]["sha256"] = hashlib.sha256(altered).hexdigest()
        self.edit_manifest(folder, meta)
        self.rerun(folder, "rights_error")

    def test_r2_manifest_data_hash_mismatch_rejected(self):
        folder, meta = self.stored_snapshot()
        self.edit_manifest(folder, meta, sha256="0" * 64)
        self.rerun(folder, "integrity_error")

    def test_r2_invalid_file_mapping_rejected(self):
        cases = {
            "extra file": lambda m: m["files"].update({"other.txt": m["files"]["LICENSE.txt"]}),
            "wrong url": lambda m: m["files"]["LICENSE.txt"].update(url="https://example.invalid/LICENSE.txt"),
            "wrong data file": lambda m: m.update(data_file="LICENSE.txt"),
            "short revision": lambda m: m.update(revision="abc"),
        }
        for label, change in cases.items():
            with self.subTest(label=label):
                self.setUp()
                folder, meta = self.stored_snapshot()
                change(meta)
                self.edit_manifest(folder, meta)
                self.rerun(folder, "snapshot_error")

    def test_r2_snapshot_outside_source_folder_rejected(self):
        folder, _ = self.stored_snapshot()
        moved = self.ws.evidence / "other-source" / REV_A
        shutil.copytree(folder, moved)
        self.rerun(moved, "snapshot_error")

    def test_r2_new_revision_with_changed_licence_needs_review_and_is_not_stored(self):
        self.stored_snapshot()
        self.ws.licence = b"Changed licence terms\n"
        self.ws.publish(REV_B, row("r2", "2025-02-03", 50))
        before = self.ws.snapshot_bytes()
        self.assert_failed_and_unchanged(self.ws.run(now=NOW.replace(day=29)), "rights_error", before)
        self.assertFalse((self.ws.evidence / "aider-polyglot" / REV_B).exists())

    def test_r2_committed_authentic_snapshot_reimports_idempotently(self):
        records, _ = registry.load_registry(ROOT / "registry")
        revision = next(s["revision"] for s in records["sources"] if s["id"] == "aider-polyglot")
        tmp_registry = Path(self.ws.tmp.name) / "prod-registry"
        shutil.copytree(ROOT / "registry", tmp_registry)
        folder = Path(self.ws.tmp.name) / "evidence" / "aider-polyglot" / revision
        shutil.copytree(ROOT / "evidence" / "snapshots" / "aider-polyglot" / revision, folder)
        run = ingest.ingest("aider-polyglot", tmp_registry, folder.parents[1], snapshot_dir=folder, now=LATER)
        self.assertEqual(run["status"], "succeeded", run["problems"])
        self.assertEqual((sum(run["counts"]["new"].values()), run["counts"]["conflict"]), (0, 0))
        for name in ("models.json", "routes.json", "series.json", "observations.jsonl"):
            self.assertEqual((ROOT / "registry" / name).read_bytes(), (tmp_registry / name).read_bytes(), name)

    # R3: cached manifest failures are logged, not raised.
    def fetch_again(self, kind):
        before = self.ws.snapshot_bytes()
        self.assert_failed_and_unchanged(self.ws.run(now=NOW.replace(hour=16)), kind, before)

    def test_r3_malformed_cached_manifest_logged(self):
        folder, _ = self.stored_snapshot()
        (folder / "SNAPSHOT.json").write_text("{", encoding="utf-8")
        self.fetch_again("snapshot_error")

    def test_r3_manifest_missing_keys_logged(self):
        folder, meta = self.stored_snapshot()
        del meta["retrieved_at"], meta["data_file"]
        (folder / "SNAPSHOT.json").write_text(json.dumps(meta), encoding="utf-8")
        self.fetch_again("snapshot_error")

    def test_r3_unreadable_cached_manifest_logged(self):
        folder, _ = self.stored_snapshot()
        (folder / "SNAPSHOT.json").unlink()
        (folder / "SNAPSHOT.json").mkdir()  # a directory cannot be read as a file
        self.fetch_again("snapshot_error")

    def test_r3_repeated_fetch_keeps_first_retrieval(self):
        folder, meta = self.stored_snapshot()
        run = self.ws.run(now=NOW.replace(hour=18))
        self.assertEqual(run["status"], "succeeded", run["problems"])
        again = json.loads((folder / "SNAPSHOT.json").read_text(encoding="utf-8"))
        self.assertEqual(again["retrieved_at"], meta["retrieved_at"])

    def test_r3_unexpected_exception_still_logs_failed_run(self):
        self.ws.publish(REV_A, row("r1", "2025-01-02", 40))
        before = self.ws.snapshot_bytes()
        broken = fixture_adapter()
        broken.build_records = unittest.mock.Mock(side_effect=RuntimeError("boom"))
        with unittest.mock.patch.dict(ingest.ADAPTERS, {"aider-polyglot": broken}):
            run = ingest.ingest("aider-polyglot", self.ws.registry, self.ws.evidence, now=NOW, get=self.ws.get)
        self.assert_failed_and_unchanged(run, "internal_error", before)
        self.assertIn("RuntimeError: boom", run["problems"][-1]["message"])


class ParserTests(unittest.TestCase):
    def test_quoted_and_commented_values(self):
        rows = aider_polyglot.parse_rows('- a: "x # y"\n  b: 1 # note\n')
        self.assertEqual(rows[0]["a"], "x # y")
        self.assertEqual((rows[0]["b"], rows[0]["comment:b"]), ("1", "note"))

    def test_unsupported_structures_fail(self):
        for text in ("- a: [1, 2]\n", "- a: |\n", "a: 1\n", "- a: 1\n  a: 2\n", "", "- a: 'x'\n"):
            with self.subTest(text=text), self.assertRaises(aider_polyglot.ParseError):
                aider_polyglot.parse_rows(text)


class ProductionEvidenceTests(unittest.TestCase):
    """The public registry must be reproducible from the preserved snapshot."""

    def test_production_observations_rebuild_from_committed_snapshot(self):
        """Every observation is rebuilt from its own referenced snapshot (review T05 R2)."""
        records, errors = registry.load_registry(ROOT / "registry")
        self.assertEqual(errors, [])
        production = [o for o in records["observations"]
                      if o["series_id"].startswith("aider-polyglot.")]
        if not production:
            self.skipTest("no aider observations in production registry")
        rebuilt_by_revision = {}
        for obs in production:
            revision = obs["source_revision"]
            if revision not in rebuilt_by_revision:
                folder = ROOT / "evidence" / "snapshots" / "aider-polyglot" / revision
                meta, text = ingest.load_snapshot(folder, aider_polyglot)
                rebuilt, _, _ = aider_polyglot.build_records(aider_polyglot.parse_rows(text), meta)
                rebuilt_by_revision[revision] = {o["id"]: o for o in rebuilt["observations"]}
            fresh = rebuilt_by_revision[revision].get(obs["id"])
            self.assertIsNotNone(fresh, f"{obs['id']} is not in its snapshot {revision}")
            for field in ingest.COMPARE_FIELDS["observations"] + ("evidence_url", "source_revision"):
                self.assertEqual(obs[field], fresh[field], (obs["id"], field))

    def test_licence_is_kept_with_every_snapshot(self):
        for meta_path in (ROOT / "evidence" / "snapshots").glob("*/*/SNAPSHOT.json"):
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            for name, info in meta["files"].items():
                data = (meta_path.parent / name).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(), info["sha256"], meta_path)
            self.assertIn("LICENSE.txt", meta["files"])


class ContractExtensionTests(unittest.TestCase):
    """H1 and the T02 contract additions (day-precision dates, source_details, run log)."""

    def setUp(self):
        self.records, errors = registry.load_registry(ROOT / "tests" / "fixtures" / "registry_valid")
        assert not errors

    def errors(self, records):
        return registry.validate_records(records, fixture_mode=True, now=NOW)

    def with_obs(self, **changes):
        records = copy.deepcopy(self.records)
        records["observations"][1].update(changes)
        return records

    def test_h1_huge_integer_metric_is_an_error_not_a_crash(self):
        records = self.with_obs(metric={"name": "score", "value": 10 ** 400, "unit": "points"})
        self.assertTrue(any("outside the representable number range" in e for e in self.errors(records)))

    def test_h1_large_representable_integer_still_passes(self):
        records = self.with_obs(metric={"name": "score", "value": 10 ** 300, "unit": "points"})
        self.assertEqual(self.errors(records), [])

    def test_h1_via_file_and_cli_has_no_traceback(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "reg"
            shutil.copytree(ROOT / "tests" / "fixtures" / "registry_valid", target)
            path = target / "observations.jsonl"
            path.write_text(path.read_text(encoding="utf-8").replace('"value": 1.5', '"value": 1' + "0" * 400),
                            encoding="utf-8")
            errors = registry.validate_registry(target, fixture_mode=True, now=NOW)
        self.assertTrue(any("outside the representable number range" in e for e in errors))

    def test_day_precision_observed_at(self):
        self.assertEqual(self.errors(self.with_obs(observed_at="2026-01-02")), [])
        cases = {"2026-02-30": "not a real date", "2026-10-01": "in the future",
                 "2026-9-01": "must be a UTC timestamp"}
        for value, message in cases.items():
            with self.subTest(value=value):
                self.assertTrue(any(message in e for e in self.errors(self.with_obs(observed_at=value))))

    def test_day_precision_retrieval_tolerance(self):
        ok = self.with_obs(observed_at="2026-01-03", retrieved_at="2026-01-02T12:00:00Z")
        self.assertEqual(self.errors(ok), [])
        bad = self.with_obs(observed_at="2026-01-05", retrieved_at="2026-01-02T12:00:00Z")
        self.assertTrue(any("retrieved_at is earlier" in e for e in self.errors(bad)))

    def test_day_precision_duplicate_rejected(self):
        records = self.with_obs(observed_at="2026-01-02")
        clone = copy.deepcopy(records["observations"][1])
        clone["id"] = "fixture-obs-3"
        records["observations"].append(clone)
        self.assertTrue(any("same series and observed_at" in e for e in self.errors(records)))

    def test_source_details_must_be_flat_finite_scalars(self):
        self.assertEqual(self.errors(self.with_obs(source_details={"a": "1", "b": 2, "c": None})), [])
        for bad in ({"a": [1]}, {"a": {"b": 1}}, {"a": float("nan")}, "text"):
            with self.subTest(bad=bad):
                self.assertTrue(any("source_details" in e for e in self.errors(self.with_obs(source_details=bad))))

    def test_run_log_timing_and_status_checked(self):
        records = copy.deepcopy(self.records)
        run = {"id": "fixture-run-1", "fixture": True, "source_id": "fixture-source-a",
               "started_at": "2026-01-02T00:00:00Z", "finished_at": "2026-01-01T00:00:00Z",
               "status": "maybe", "source_revision": None, "snapshot_path": None,
               "snapshot_sha256": None, "counts": {}, "problems": []}
        records["ingestion_runs"].append(run)
        errors = self.errors(records)
        self.assertTrue(any("finished_at is earlier" in e for e in errors))
        self.assertTrue(any(".status: must be one of" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
