"""Model catalogue: strict validation and explicit route joins (T07). Stdlib only.

    py -3.11 -B scripts/catalog.py        # validate catalog/models.json against registry/

The catalogue lists verified model identities and access routes, including ones with no
measurements. It holds no scores. A catalogue entry shows evidence only through the
registry routes it lists explicitly, and every link is checked so that an app, an API
and a hosting service never borrow each other's measurements.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import registry  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "catalog" / "models.json"
SCHEMA_VERSION = 1
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,159}$")
IDENTITY_KINDS = {"exact", "family", "automatic"}
ACCESS_KINDS = {"consumer_app", "direct_api", "intermediary", "cloud_platform", "local", "unknown"}
AVAILABILITY = {"available", "retired", "unknown"}
# Access kinds with an approved numeric registry representation.
LINKABLE = {"direct_api", "intermediary", "cloud_platform"}
FIELDS = {"id": str, "name": str, "maker": str, "family": str, "identity_kind": str,
          "exact_identifier": (str, type(None)), "service_provider": str, "access_kind": str,
          "availability": str, "route_ids": list, "sources": list, "notes": str}
SOURCE_FIELDS = {"url", "checked_at", "claim"}
# Optional, cited release date (T08). Absent means unknown; it is never inferred from a
# name suffix, a retrieval time or a benchmark run date.
OPTIONAL_FIELDS = {"release"}
RELEASE_FIELDS = {"date", "precision", "source"}
RELEASE_DATE = {"day": re.compile(r"^\d{4}-\d{2}-\d{2}$"), "month": re.compile(r"^\d{4}-\d{2}$")}


def load(path: Path = CATALOG_PATH) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _check_source(where: str, source, now: datetime) -> list:
    if not isinstance(source, dict) or set(source) != SOURCE_FIELDS:
        return [f"{where}: a source needs exactly url, checked_at and claim"]
    problems = []
    if not isinstance(source["url"], str) or not re.match(r"^https://[^\s]+$", source["url"]):
        problems.append(f"{where}.url: must be an https:// URL")
    moment = registry._instant(source["checked_at"])
    if moment is None:
        problems.append(f"{where}.checked_at: must be a UTC timestamp")
    elif moment > now:
        problems.append(f"{where}.checked_at: is in the future")
    if not isinstance(source["claim"], str) or not source["claim"].strip():
        problems.append(f"{where}.claim: must be a non-empty string")
    return problems


def _check_release(where: str, entry: dict, now: datetime) -> list:
    release = entry["release"]
    if not isinstance(release, dict) or set(release) != RELEASE_FIELDS:
        return [f"{where}.release: needs exactly date, precision and source"]
    if entry["identity_kind"] != "exact" or entry["access_kind"] not in ("direct_api", "local"):
        return [f"{where}.release: only exact API or open-weight entries carry a release date"]
    problems = _check_source(f"{where}.release.source", release["source"], now)
    precision = release["precision"]
    # Type first: a list or object would otherwise make the dictionary lookup raise (T08 R2).
    pattern = RELEASE_DATE.get(precision) if isinstance(precision, str) else None
    if pattern is None:
        return problems + [f"{where}.release.precision: must be one of {sorted(RELEASE_DATE)}"]
    date = release["date"]
    if not isinstance(date, str) or not pattern.match(date):
        return problems + [f"{where}.release.date: must be a string matching the {precision} precision"]
    try:
        datetime.strptime(date if precision == "day" else date + "-01", "%Y-%m-%d")
    except ValueError:
        return problems + [f"{where}.release.date: not a calendar date"]
    checked = release["source"].get("checked_at") if isinstance(release["source"], dict) else None
    if isinstance(checked, str) and date > checked[:len(date)]:
        problems.append(f"{where}.release.date: is after the source was checked")
    return problems


def validate_catalog(document: dict, records: dict, now: datetime | None = None) -> list:
    """Return every problem with the catalogue and its links to `records` (registry)."""
    now = now or datetime.now(timezone.utc)
    if not isinstance(document, dict) or document.get("schema_version") != SCHEMA_VERSION \
            or not isinstance(document.get("entries"), list):
        return [f"catalogue must be {{schema_version: {SCHEMA_VERSION}, entries: [...]}}"]
    routes = {r.get("id"): r for r in records.get("routes", []) if isinstance(r, dict)}
    models = {m.get("id"): m for m in records.get("models", []) if isinstance(m, dict)}
    problems, seen, linked = [], set(), {}
    for index, entry in enumerate(document["entries"]):
        where = f"entries[{index}]"
        if not isinstance(entry, dict):
            problems.append(f"{where}: must be an object")
            continue
        where = f"entries[{entry.get('id', index)}]"
        for name in sorted(set(entry) - set(FIELDS) - OPTIONAL_FIELDS):
            problems.append(f"{where}: unknown field {name!r}")
        missing = [name for name in FIELDS if name not in entry]
        for name in missing:
            problems.append(f"{where}.{name}: missing")
        wrong = [name for name, kind in FIELDS.items() if name in entry and not isinstance(entry[name], kind)]
        for name in wrong:
            problems.append(f"{where}.{name}: wrong type")
        if missing or wrong:
            continue
        if not ID_RE.match(entry["id"]):
            problems.append(f"{where}.id: must be a lowercase id")
        if entry["id"] in seen:
            problems.append(f"{where}: duplicate id")
        seen.add(entry["id"])
        for name in ("name", "maker", "family", "service_provider"):
            if not entry[name].strip():
                problems.append(f"{where}.{name}: must not be empty")
        for name, allowed in (("identity_kind", IDENTITY_KINDS), ("access_kind", ACCESS_KINDS),
                              ("availability", AVAILABILITY)):
            if entry[name] not in allowed:
                problems.append(f"{where}.{name}: must be one of {sorted(allowed)}")
        exact = entry["identity_kind"] == "exact"
        if exact != (entry["exact_identifier"] is not None) or (exact and not entry["exact_identifier"].strip()):
            problems.append(f"{where}.exact_identifier: required for exact identities and null otherwise")
        if not entry["sources"]:
            problems.append(f"{where}.sources: at least one source is required")
        for i, source in enumerate(entry["sources"]):
            problems.extend(_check_source(f"{where}.sources[{i}]", source, now))
        if "release" in entry:
            problems.extend(_check_release(where, entry, now))
        if len(set(map(str, entry["route_ids"]))) != len(entry["route_ids"]):
            problems.append(f"{where}.route_ids: repeated route")
        if entry["route_ids"] and (entry["access_kind"] not in LINKABLE or not exact):
            problems.append(f"{where}.route_ids: only exact {sorted(LINKABLE)} entries may link measured routes "
                            f"(this entry is {entry['identity_kind']} {entry['access_kind']}; access must match)")
            continue
        for route_id in entry["route_ids"]:
            route = routes.get(route_id) if isinstance(route_id, str) else None
            if route is None:
                problems.append(f"{where}.route_ids: unknown route {route_id!r}")
                continue
            if route_id in linked:
                problems.append(f"{where}: route {route_id} is linked by more than one entry ({linked[route_id]})")
            linked[route_id] = entry["id"]
            model = models.get(route.get("model_id"), {})
            if route.get("access_type") != entry["access_kind"]:
                problems.append(f"{where}: route {route_id} access {route.get('access_type')!r} "
                                f"does not match entry access {entry['access_kind']!r}")
            if model.get("provider") != entry["maker"]:
                problems.append(f"{where}: route {route_id} maker {model.get('provider')!r} is not {entry['maker']!r}")
            if model.get("exact_identifier") != entry["exact_identifier"]:
                problems.append(f"{where}: route {route_id} identifier {model.get('exact_identifier')!r} "
                                f"is not {entry['exact_identifier']!r}")
            expected_service = entry["maker"] if entry["access_kind"] == "direct_api" else route.get("service")
            if entry["service_provider"] != expected_service:
                problems.append(f"{where}: service provider {entry['service_provider']!r} does not match "
                                f"route {route_id} ({expected_service!r})")
    return problems


FEATURED_PATH = ROOT / "catalog" / "featured.json"
FEATURED_FIELDS = ("checked_at", "explanation", "groups", "schema_version")
FEATURED_GROUP_FIELDS = ("entries", "family", "reason")


def validate_featured(document, entries: list, now: datetime | None = None) -> list:
    """The editorial Featured shortlist (T14): exact fields, known catalogue ids, no duplicates.

    It holds only ids, family labels and short written reasons: no ranks, counts or scores,
    so it cannot carry an invented popularity statistic.
    """
    now = now or datetime.now(timezone.utc)
    if not isinstance(document, dict) or tuple(sorted(document)) != FEATURED_FIELDS \
            or document.get("schema_version") != 1:
        return [f"featured list must have exactly the fields {list(FEATURED_FIELDS)} (schema_version 1)"]
    problems = []
    moment = registry._instant(document["checked_at"])
    if moment is None or moment > now:
        problems.append("featured.checked_at must be a past UTC timestamp")
    if not isinstance(document["explanation"], str) or not 20 <= len(document["explanation"].strip()) <= 600:
        problems.append("featured.explanation must say in 20-600 characters how the list was chosen")
    groups = document["groups"]
    if not isinstance(groups, list) or not 1 <= len(groups) <= 10:
        return problems + ["featured.groups must be a list of 1-10 groups"]
    known = {e["id"] for e in entries if isinstance(e, dict)}
    seen = set()
    for i, group in enumerate(groups):
        where = f"featured.groups[{i}]"
        if not isinstance(group, dict) or tuple(sorted(group)) != FEATURED_GROUP_FIELDS:
            problems.append(f"{where}: must have exactly the fields {list(FEATURED_GROUP_FIELDS)}")
            continue
        if not isinstance(group["family"], str) or not 1 <= len(group["family"].strip()) <= 60:
            problems.append(f"{where}.family: must be a short label")
        if not isinstance(group["reason"], str) or not 10 <= len(group["reason"].strip()) <= 400:
            problems.append(f"{where}.reason: must give a short written reason (10-400 characters)")
        ids = group["entries"]
        if not isinstance(ids, list) or not 1 <= len(ids) <= 6:
            problems.append(f"{where}.entries: must list 1-6 catalogue ids")
            continue
        for entry_id in ids:
            if not isinstance(entry_id, str):
                problems.append(f"{where}: catalogue ids must be text, not {type(entry_id).__name__}")
                continue
            if entry_id not in known:
                problems.append(f"{where}: unknown catalogue id {entry_id!r}")
            elif entry_id in seen:
                problems.append(f"{where}: {entry_id} is featured twice")
            seen.add(entry_id)
    return problems


MAKER_KEYS = {"OpenAI": "openai", "Anthropic": "anthropic", "Google": "google", "DeepSeek": "deepseek",
              "xAI": "xai", "Mistral AI": "mistral", "Alibaba (Qwen)": "qwen", "Moonshot AI": "moonshot",
              "Cohere": "cohere", "Meta": "meta"}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9._-]+", "-", str(text).lower()).strip("-.")


class ReconcileError(Exception):
    """A registry route has no possible catalogue representation."""


def reconcile(document: dict, records: dict) -> tuple[list, list]:
    """Published catalogue = curated entries plus every registry route linked once (T07 R1).

    The curated file is never rewritten. A route not linked by the curated catalogue is
    attached to the curated exact entry with the same maker, identifier, access and
    service, or else gets an evidence-only entry (availability unknown, dated by the
    observation's real retrieval time). Returns (entries, ids of evidence-only entries).
    """
    entries = [dict(e, route_ids=list(e["route_ids"])) for e in document["entries"]]
    linked = {r for e in entries for r in e["route_ids"]}
    models = {m["id"]: m for m in records["models"]}
    series_by_route = {}
    for series in records["series"]:
        series_by_route.setdefault(series["route_id"], []).append(series["id"])
    first_obs = {}
    for obs in records["observations"]:
        first_obs.setdefault(obs["series_id"], obs)
    by_key = {(e["maker"], e["exact_identifier"], e["access_kind"], e["service_provider"]): e
              for e in entries if e["identity_kind"] == "exact" and e["access_kind"] in LINKABLE}
    ids, added = {e["id"] for e in entries}, []
    for route in records["routes"]:
        if route["id"] in linked:
            continue
        if route["access_type"] not in LINKABLE:
            raise ReconcileError(f"route {route['id']} has access {route['access_type']!r}, which has no "
                                 "reviewed catalogue representation; publication refused")
        model = models[route["model_id"]]
        maker, exact = model["provider"], model["exact_identifier"]
        service = maker if route["access_type"] == "direct_api" else route["service"]
        entry = by_key.get((maker, exact, route["access_type"], service))
        if entry is None:
            obs = next((first_obs[s] for s in series_by_route.get(route["id"], []) if s in first_obs), None)
            if obs is None:
                raise ReconcileError(f"route {route['id']} has no observation to cite; publication refused")
            kind = "api" if route["access_type"] == "direct_api" else _slug(service)
            base = f"{MAKER_KEYS.get(maker, _slug(maker))}-{kind}.{_slug(exact)}"
            entry_id, n = base, 2
            while entry_id in ids:
                entry_id, n = f"{base}-{n}", n + 1
            entry = {"id": entry_id, "name": exact, "maker": maker, "family": model.get("public_name") or exact,
                     "identity_kind": "exact", "exact_identifier": exact, "service_provider": service,
                     "access_kind": route["access_type"], "availability": "unknown", "route_ids": [],
                     "sources": [{"url": obs["evidence_url"], "checked_at": obs["retrieved_at"],
                                  "claim": f"Evidence run requested '{route['requested_model']}'"}],
                     "notes": "Added automatically from reviewed evidence; not yet in the curated catalogue. "
                              "Current availability is unknown."}
            entries.append(entry)
            ids.add(entry_id)
            added.append(entry_id)
            by_key[(maker, exact, route["access_type"], service)] = entry
        entry["route_ids"].append(route["id"])
        linked.add(route["id"])
    return entries, added


def build_catalog(document: dict, routes: list) -> list:
    """Entries with their explicitly listed routes attached. Never invents observations."""
    by_id = {r["id"]: r for r in routes}
    joined = []
    for entry in document["entries"]:
        item = {k: v for k, v in entry.items() if k != "route_ids"}
        item["routes"] = [by_id[r] for r in entry["route_ids"] if r in by_id]
        joined.append(item)
    return joined


def main(argv: list) -> int:
    if argv:
        print(__doc__)
        return 2
    records, errors = registry.load_registry(ROOT / "registry")
    errors += validate_catalog(load(), records)
    if errors:
        print(f"FAIL: {len(errors)} problem(s)")
        for error in errors[:30]:
            print(f"  - {error}")
        return 1
    document = load()
    linked = sum(len(e["route_ids"]) for e in document["entries"])
    print(f"OK: {len(document['entries'])} catalogue entries, {linked} measured routes linked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
