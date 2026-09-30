"""T07 catalogue: strict validation and explicit, identity-safe route joins."""
import copy
from datetime import datetime, timezone
import importlib
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
catalog = importlib.import_module("catalog")
registry = importlib.import_module("registry")

NOW = datetime(2026, 9, 30, tzinfo=timezone.utc)


def fixture_entry(**changes):
    entry = {"id": "fixture-app", "name": "Fixture App", "maker": "Fixture", "family": "Fixture",
             "identity_kind": "automatic", "exact_identifier": None, "service_provider": "Fixture",
             "access_kind": "consumer_app", "availability": "unknown", "route_ids": [],
             "sources": [{"url": "https://example.invalid/models", "checked_at": "2026-09-30T00:00:00Z",
                          "claim": "test fixture"}],
             "notes": "synthetic"}
    entry.update(changes)
    return entry


def fixture_records():
    return {"models": [{"id": "fixture-model", "provider": "Fixture", "exact_identifier": "fixture-1"}],
            "routes": [{"id": "fixture-api", "model_id": "fixture-model", "access_type": "direct_api",
                        "service": "Fixture API"},
                       {"id": "fixture-host", "model_id": "fixture-model", "access_type": "intermediary",
                        "service": "Fixture Host"}]}


def api_entry(**changes):
    base = fixture_entry(id="fixture-api-entry", name="fixture-1", identity_kind="exact",
                         exact_identifier="fixture-1", access_kind="direct_api", route_ids=["fixture-api"])
    base.update(changes)
    return base


def errors(entries, records=None):
    return catalog.validate_catalog({"schema_version": 1, "entries": entries},
                                    records or fixture_records(), NOW)


class CatalogValidationTests(unittest.TestCase):
    def test_app_entry_cannot_link_an_api_route(self):
        found = errors([fixture_entry(route_ids=["fixture-api"])])
        self.assertTrue(any("access" in e for e in found), found)

    def test_matching_api_entry_links_cleanly(self):
        self.assertEqual(errors([api_entry()]), [])

    def test_intermediary_needs_matching_service_and_kind(self):
        good = api_entry(id="fixture-hosted", access_kind="intermediary", service_provider="Fixture Host",
                         route_ids=["fixture-host"])
        self.assertEqual(errors([good]), [])
        wrong_service = dict(good, service_provider="Other Host")
        self.assertTrue(any("service" in e for e in errors([wrong_service])))
        self.assertTrue(any("access" in e for e in errors([api_entry(route_ids=["fixture-host"])])))

    def test_maker_and_identifier_must_match_the_linked_model(self):
        self.assertTrue(any("maker" in e for e in errors([api_entry(maker="Someone Else")])))
        self.assertTrue(any("identifier" in e for e in errors([api_entry(exact_identifier="fixture-2")])))

    def test_identity_rules(self):
        self.assertTrue(any("exact_identifier" in e for e in errors([api_entry(exact_identifier=None)])))
        self.assertTrue(any("exact_identifier" in e
                            for e in errors([fixture_entry(exact_identifier="fixture-1")])))
        self.assertTrue(any("route" in e for e in errors([fixture_entry(
            id="fixture-local", access_kind="local", identity_kind="family", route_ids=["fixture-api"])])))
        self.assertTrue(any("route" in e for e in errors([fixture_entry(
            id="fixture-family", access_kind="direct_api", identity_kind="family", route_ids=["fixture-api"])])))

    def test_structural_problems_are_reported(self):
        cases = {
            "duplicate": [fixture_entry(), fixture_entry()],
            "unknown field": [fixture_entry(score=99)],
            "missing field": [{k: v for k, v in fixture_entry().items() if k != "maker"}],
            "wrong type": [fixture_entry(route_ids="fixture-api")],
            "bad enum": [fixture_entry(access_kind="website")],
            "dangling route": [api_entry(route_ids=["no-such-route"])],
            "repeated route": [api_entry(route_ids=["fixture-api", "fixture-api"])],
            "future check": [fixture_entry(sources=[{"url": "https://example.invalid/x",
                                                     "checked_at": "2027-01-01T00:00:00Z", "claim": "x"}])],
            "unsafe url": [fixture_entry(sources=[{"url": "javascript:alert(1)",
                                                   "checked_at": "2026-09-30T00:00:00Z", "claim": "x"}])],
            "http url": [fixture_entry(sources=[{"url": "http://example.invalid/x",
                                                 "checked_at": "2026-09-30T00:00:00Z", "claim": "x"}])],
            "no sources": [fixture_entry(sources=[])],
            "bad id": [fixture_entry(id="Fixture App!")],
        }
        for label, entries in cases.items():
            with self.subTest(label=label):
                self.assertTrue(errors(entries), label)
        self.assertTrue(catalog.validate_catalog({"schema_version": 2, "entries": []}, fixture_records(), NOW))
        self.assertTrue(catalog.validate_catalog({"entries": []}, fixture_records(), NOW))

    def test_a_route_belongs_to_one_entry(self):
        found = errors([api_entry(), api_entry(id="fixture-api-entry-2")])
        self.assertTrue(any("more than one" in e for e in found), found)

    def test_unmeasured_family_joins_to_no_routes(self):
        document = {"schema_version": 1, "entries": [fixture_entry(id="fixture-family", identity_kind="family")]}
        joined = catalog.build_catalog(document, [])
        self.assertEqual(joined[0]["routes"], [])
        self.assertNotIn("observations", joined[0])
        self.assertNotIn("score", json.dumps(joined))

    def test_build_joins_only_listed_routes(self):
        routes = [{"id": "fixture-api", "observations": [1]}, {"id": "fixture-host", "observations": [2]}]
        joined = catalog.build_catalog({"schema_version": 1, "entries": [api_entry()]}, routes)
        self.assertEqual([r["id"] for r in joined[0]["routes"]], ["fixture-api"])


class ProductionCatalogTests(unittest.TestCase):
    def setUp(self):
        self.document = json.loads((ROOT / "catalog" / "models.json").read_text(encoding="utf-8"))
        self.records, _ = registry.load_registry(ROOT / "registry")

    def test_production_catalog_validates_against_the_registry(self):
        self.assertEqual(catalog.validate_catalog(self.document, self.records, datetime.now(timezone.utc)), [])

    def test_every_route_is_published_exactly_once(self):
        curated = [r for e in self.document["entries"] for r in e["route_ids"]]
        self.assertEqual(len(curated), len(set(curated)))  # curated file: at most once
        entries, _ = catalog.reconcile(self.document, self.records)
        linked = [r for e in entries for r in e["route_ids"]]
        self.assertEqual(sorted(linked), sorted(r["id"] for r in self.records["routes"]))

    def test_agreed_providers_and_separate_apps_are_present(self):
        makers = {e["maker"] for e in self.document["entries"]}
        for maker in ("OpenAI", "Anthropic", "Google", "DeepSeek", "xAI", "Meta", "Mistral AI",
                      "Alibaba (Qwen)", "Moonshot AI", "Cohere"):
            self.assertIn(maker, makers)
        apps = [e for e in self.document["entries"] if e["access_kind"] == "consumer_app"]
        self.assertTrue(apps)
        for app in apps:
            self.assertEqual((app["route_ids"], app["exact_identifier"]), ([], None), app["id"])
            self.assertIn(app["identity_kind"], ("automatic", "family"))

    def test_evidence_entries_do_not_claim_current_availability(self):
        listed = {s["url"] for e in self.document["entries"] for s in e["sources"]
                  if "github.com/Aider-AI" not in s["url"]}
        for entry in self.document["entries"]:
            if all("github.com/Aider-AI" in s["url"] for s in entry["sources"]):
                self.assertEqual(entry["availability"], "unknown", entry["id"])
        self.assertTrue(listed)


if __name__ == "__main__":
    unittest.main()
