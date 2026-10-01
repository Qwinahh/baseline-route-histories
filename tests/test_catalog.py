"""T07 catalogue: strict validation and explicit, identity-safe route joins."""
import contextlib
import copy
from datetime import datetime, timezone
import importlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock


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


def release(**changes):
    value = {"date": "2026-09-01", "precision": "day",
             "source": {"url": "https://example.invalid/changelog", "checked_at": "2026-09-30T00:00:00Z",
                        "claim": "Changelog entry dated 2026-09-01"}}
    value.update(changes)
    return value


class ReleaseDateTests(unittest.TestCase):
    """T08: release dates are optional, cited, and never later than their source check."""

    def test_cited_day_and_month_dates_validate(self):
        self.assertEqual(errors([api_entry(release=release())]), [])
        self.assertEqual(errors([api_entry(release=release(date="2025-07", precision="month"))]), [])
        self.assertEqual(errors([api_entry()]), [])                     # absent means unknown

    def test_malformed_or_uncited_dates_are_refused(self):
        bad = [release(date="2026-9-1"), release(date="2026-02-30"), release(date="2025-07"),
               release(precision="year"), release(date="2026-10-01"),     # after the source was checked
               {"date": "2026-09-01", "precision": "day"},
               release(source={"url": "http://example.invalid/", "checked_at": "2026-09-30T00:00:00Z", "claim": "x"}),
               release(source={"url": "https://example.invalid/", "checked_at": "2026-09-30T00:00:00Z", "claim": " "})]
        for value in bad:
            self.assertTrue(errors([api_entry(release=value)]), value)

    def test_wrong_types_are_reported_not_raised(self):
        """T08 R2: list, object, null, number and boolean values give problems, never a TypeError."""
        for wrong in ([], {}, None, 5, 1.5, True):
            for field in ("date", "precision", "source"):
                with self.subTest(field=field, value=wrong):
                    self.assertTrue(errors([api_entry(release=release(**{field: wrong}))]))
            for field in ("url", "checked_at", "claim"):
                source = dict(release()["source"], **{field: wrong})
                with self.subTest(source_field=field, value=wrong):
                    self.assertTrue(errors([api_entry(release=release(source=source))]))
            with self.subTest(release=wrong):
                self.assertTrue(errors([api_entry(release=wrong)]))

    def test_cli_reports_malformed_release_without_a_traceback(self):
        records, _ = registry.load_registry(ROOT / "registry")
        document = copy.deepcopy(catalog.load())
        dated = next(e for e in document["entries"] if "release" in e)
        for wrong in ([], {}):
            dated["release"]["precision"] = wrong
            out = io.StringIO()
            with self.subTest(value=wrong), mock.patch.object(catalog, "load", return_value=document), \
                    contextlib.redirect_stdout(out):
                self.assertEqual(catalog.main([]), 1)
            self.assertIn("release.precision: must be one of", out.getvalue())
            self.assertIsInstance(catalog.validate_catalog(document, records), list)

    def test_only_exact_api_or_open_weight_identities_carry_a_date(self):
        self.assertTrue(errors([fixture_entry(release=release())]))    # consumer app
        self.assertTrue(errors([api_entry(identity_kind="family", exact_identifier=None, route_ids=[],
                                          release=release())]))


class FeaturedListTests(unittest.TestCase):
    """T14: the editorial Featured list holds only known ids and written reasons, no ranks or scores."""

    def setUp(self):
        self.entries = catalog.load()["entries"]
        self.doc = json.loads((ROOT / "catalog" / "featured.json").read_text(encoding="utf-8"))

    def test_production_featured_list_validates(self):
        self.assertEqual(catalog.validate_featured(self.doc, self.entries, NOW.replace(day=30, hour=23)
                                                  .replace(month=10)), [])
        families = [g["family"] for g in self.doc["groups"]]
        for family in ("OpenAI and ChatGPT", "Claude", "Gemini", "DeepSeek", "Qwen", "Llama", "Grok"):
            self.assertIn(family, families)
        self.assertIn("not a measured popularity ranking", self.doc["explanation"])
        groq = next(e for e in self.entries if e["id"] == "openai-groq.gpt-oss-120b")
        self.assertEqual((groq["access_kind"], groq["service_provider"]), ("intermediary", "Groq"))
        self.assertIn("not ChatGPT", groq["notes"])

    def test_refusals(self):
        later = datetime(2026, 10, 30, tzinfo=timezone.utc)

        def changed(mutate):
            doc = copy.deepcopy(self.doc)
            mutate(doc)
            return doc
        cases = {
            "rank field": changed(lambda d: d["groups"][0].update(rank=1)),
            "popularity number": changed(lambda d: d.update(popularity={"chatgpt": 1})),
            "unknown id": changed(lambda d: d["groups"][0]["entries"].append("openai-api.gpt-99")),
            "featured twice": changed(lambda d: d["groups"][1]["entries"].append(d["groups"][0]["entries"][0])),
            "no reason": changed(lambda d: d["groups"][0].update(reason="")),
            "too many in a group": changed(lambda d: d["groups"][0].update(entries=[e["id"] for e in self.entries[:7]])),
            "future check": changed(lambda d: d.update(checked_at="2027-01-01T00:00:00Z")),
            "no explanation": changed(lambda d: d.update(explanation="list")),
            "non-text id (review P3)": changed(lambda d: d["groups"][0].update(entries=[{}])),
            "numeric id": changed(lambda d: d["groups"][0].update(entries=[7])),
        }
        for label, doc in cases.items():
            with self.subTest(case=label):
                self.assertTrue(catalog.validate_featured(doc, self.entries, later))


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

    def test_release_dates_are_cited_and_match_the_reviewed_table(self):
        rows = json.loads((ROOT / "catalog" / "release_dates.json").read_text(encoding="utf-8"))["rows"]
        table = {(r["maker"], r["exact_identifier"]): r for r in rows}
        self.assertEqual(len(table), len(rows))                         # one row per identity
        dated = [e for e in self.document["entries"] if "release" in e]
        self.assertTrue(dated)
        for entry in dated:
            row = table[(entry["maker"], entry["exact_identifier"])]
            self.assertEqual(entry["access_kind"], "direct_api", entry["id"])
            self.assertEqual(entry["release"], {k: row[k] for k in ("date", "precision", "source")})
            self.assertTrue(entry["release"]["source"]["url"].startswith("https://"), entry["id"])
        for key in table:                                               # every reviewed row is used
            self.assertTrue(any((e["maker"], e["exact_identifier"]) == key for e in dated), key)
        # Evidence-only entries and apps never receive a date.
        for entry in self.document["entries"]:
            if entry["access_kind"] != "direct_api" or all("github.com/Aider-AI" in s["url"] for s in entry["sources"]):
                if (entry["maker"], entry["exact_identifier"]) not in table:
                    self.assertNotIn("release", entry, entry["id"])

    def test_every_maker_has_a_documented_release_date_search(self):
        """T08 R1: each maker's search is recorded; undated identities have a stated reason."""
        table = json.loads((ROOT / "catalog" / "release_dates.json").read_text(encoding="utf-8"))
        research = {r["maker"]: r for r in table["research"]}
        self.assertEqual(set(research), {e["maker"] for e in self.document["entries"]})
        for maker, record in research.items():
            self.assertTrue(record["pages"] and record["outcome"].strip(), maker)
        dated = {(r["maker"], r["exact_identifier"]) for r in table["rows"]}
        for entry in self.document["entries"]:
            if entry["maker"] in ("Cohere", "Alibaba (Qwen)", "Moonshot AI") and entry["access_kind"] == "direct_api" \
                    and (entry["maker"], entry["exact_identifier"]) not in dated:
                self.assertIn(entry["exact_identifier"], research[entry["maker"]]["unresolved"], entry["id"])
        self.assertIn(("Cohere", "command-a-plus-05-2026"), dated)

    def test_evidence_entries_do_not_claim_current_availability(self):
        listed = {s["url"] for e in self.document["entries"] for s in e["sources"]
                  if "github.com/Aider-AI" not in s["url"]}
        for entry in self.document["entries"]:
            if all("github.com/Aider-AI" in s["url"] for s in entry["sources"]):
                self.assertEqual(entry["availability"], "unknown", entry["id"])
        self.assertTrue(listed)


if __name__ == "__main__":
    unittest.main()
