"""Evidence registry schema and validator (T01, extended in T02). Stdlib only, offline.

Usage:
    py -3.11 -B scripts/registry.py                      # validate ./registry (production)
    py -3.11 -B scripts/registry.py DIR --fixtures       # validate a labelled fixture set

A registry directory holds models.json, routes.json, sources.json, series.json
(each {"schema_version": 2, "records": [...]}) plus append-oriented
observations.jsonl, ingestion_runs.jsonl and corrections.jsonl (one object per line).
See docs/DATA_CONTRACT.md.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sys

# v1: T01 shapes. v2 (T03): T02 additions (ingestion_runs, source_details, day-precision
# observed_at) plus corrections.jsonl. Migration v1 -> v2 changed only file headers.
SCHEMA_VERSION = 2
JSON_FILES = ("models", "routes", "sources", "series")
OBSERVATIONS_FILE = "observations.jsonl"
JSONL_FILES = {"observations": OBSERVATIONS_FILE, "ingestion_runs": "ingestion_runs.jsonl",
               "corrections": "corrections.jsonl"}

ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

AVAILABILITY = {"announced", "available", "deprecated", "retired", "unknown"}
ACCESS_TYPES = {"direct_api", "consumer_app", "cloud_platform", "intermediary", "unknown"}
REUSE_DECISIONS = {"numeric_republication_permitted", "link_and_summary_only", "not_reviewed"}
EXCLUSION_KINDS = {"fallback", "refusal", "error", "retry", "missing"}
RUN_STATUSES = {"succeeded", "failed"}
CORRECTION_TARGETS = {"ingestion_runs"}
CORRECTION_ACTIONS = {"superseded"}
# A source that states only a calendar date (timezone unstated) may be recorded at day
# precision; comparisons with our UTC timestamps allow one day either way.
DAY_TOLERANCE = timedelta(days=1)

# Field spec: name -> (kind, required). Kinds: id, ref:<type>, str, opt_str, url,
# opt_url, utc, opt_utc, opt_date, moment (UTC timestamp or day-precision date),
# enum:<set name>, obj, opt_obj_scalars, list, bool, metric, exclusions, sha256, opt_sha256.
FIELDS = {
    "models": {
        "id": ("id", True), "fixture": ("bool", False),
        "provider": ("str", True), "public_name": ("str", True),
        "exact_identifier": ("str", True), "identifier_source_url": ("url", True),
        "release_date": ("opt_date", True), "release_source_url": ("opt_url", True),
        "availability": ("enum:AVAILABILITY", True), "notes": ("opt_str", False),
    },
    "routes": {
        "id": ("id", True), "fixture": ("bool", False),
        "model_id": ("ref:models", True), "access_type": ("enum:ACCESS_TYPES", True),
        "service": ("str", True), "requested_model": ("str", True),
        "tier": ("opt_str", True), "region": ("opt_str", True),
        "settings": ("obj", True), "notes": ("opt_str", False),
    },
    "sources": {
        "id": ("id", True), "fixture": ("bool", False),
        "author": ("str", True), "url": ("url", True), "method": ("str", True),
        "access_method": ("str", True), "reuse_decision": ("enum:REUSE_DECISIONS", True),
        "reuse_evidence": ("str", True), "revision": ("opt_str", True),
        "retrieved_at": ("utc", True), "expected_update_cadence": ("opt_str", True),
        "last_successful_check": ("opt_utc", True), "notes": ("opt_str", False),
    },
    "series": {
        "id": ("id", True), "fixture": ("bool", False),
        "route_id": ("ref:routes", True), "source_id": ("ref:sources", True),
        "suite": ("str", True), "suite_version": ("str", True), "grader": ("str", True),
        "prompt_set": ("str", True), "harness": ("str", True), "sampling": ("obj", True),
        "scope": ("str", True), "baseline_definition": ("str", True),
        "fingerprint": ("sha256", True), "notes": ("opt_str", False),
    },
    "observations": {
        "id": ("id", True), "fixture": ("bool", False),
        "series_id": ("ref:series", True), "observed_at": ("moment", True),
        "retrieved_at": ("utc", True), "metric": ("metric", True),
        "exclusions": ("exclusions", True), "evidence_url": ("url", True),
        "source_revision": ("opt_str", True), "source_details": ("opt_obj_scalars", False),
        "notes": ("opt_str", False),
    },
    "ingestion_runs": {
        "id": ("id", True), "fixture": ("bool", False),
        "source_id": ("str", True), "started_at": ("utc", True),
        "finished_at": ("utc", True), "status": ("enum:RUN_STATUSES", True),
        "source_revision": ("opt_str", True), "snapshot_path": ("opt_str", True),
        "snapshot_sha256": ("opt_sha256", True), "counts": ("obj", True),
        "problems": ("list", True), "notes": ("opt_str", False),
    },
    # Append-only annotations on earlier records; the target itself is never edited.
    "corrections": {
        "id": ("id", True), "fixture": ("bool", False),
        "target_kind": ("enum:CORRECTION_TARGETS", True), "target_id": ("str", True),
        "action": ("enum:CORRECTION_ACTIONS", True), "reason": ("str", True),
        "recorded_at": ("utc", True), "notes": ("opt_str", False),
    },
}
FINGERPRINT_FIELDS = ("route_id", "source_id", "suite", "suite_version", "grader",
                      "prompt_set", "harness", "sampling")
# Comparison-relevant configuration resolved from the referenced route and model.
ROUTE_FINGERPRINT_FIELDS = ("model_id", "access_type", "service", "requested_model",
                            "tier", "region", "settings")
MODEL_FINGERPRINT_FIELDS = ("provider", "exact_identifier")
ENUMS = {"AVAILABILITY": AVAILABILITY, "ACCESS_TYPES": ACCESS_TYPES,
         "REUSE_DECISIONS": REUSE_DECISIONS, "RUN_STATUSES": RUN_STATUSES,
         "CORRECTION_TARGETS": CORRECTION_TARGETS, "CORRECTION_ACTIONS": CORRECTION_ACTIONS}


def _key(value):
    """Hashable lookup key for an id reference; None when the value is not a string."""
    return value if isinstance(value, str) else None


def series_fingerprint(series: dict, routes: dict, models: dict) -> str:
    """sha256 of the series configuration plus its resolved route and model settings.

    `routes`/`models` map id -> record. Editing a referenced route or model therefore
    breaks the stored fingerprint; a changed configuration needs a new route (and
    series) id. This only checks the current snapshot against the stored hash;
    Git history, not the hash, shows whether a past snapshot was rewritten.
    """
    route = routes.get(_key(series.get("route_id"))) or {}
    model = models.get(_key(route.get("model_id"))) or {}
    config = {name: series.get(name) for name in FINGERPRINT_FIELDS}
    config["route"] = {name: route.get(name) for name in ROUTE_FINGERPRINT_FIELDS}
    config["model"] = {name: model.get(name) for name in MODEL_FINGERPRINT_FIELDS}
    canonical = json.dumps(config, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value[:-1]).replace(tzinfo=timezone.utc)


def _instant(value) -> datetime | None:
    """Parsed UTC instant for a valid timestamp string, else None (already reported)."""
    if not isinstance(value, str) or not UTC_RE.match(value):
        return None
    try:
        return parse_utc(value)
    except ValueError:
        return None


def _day(value) -> date | None:
    """Parsed calendar date for a valid day-precision string, else None."""
    if not isinstance(value, str) or not DATE_RE.match(value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _is_json_scalar(value) -> bool:
    if isinstance(value, float):
        return math.isfinite(value)
    return value is None or isinstance(value, (str, int, bool))


def _nonempty(value) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _check_field(kind: str, value, where: str, errors: list, now: datetime) -> None:
    def bad(message):
        errors.append(f"{where}: {message}")

    if kind == "id":
        if not isinstance(value, str) or not ID_RE.match(value):
            bad("must be a lowercase id matching [a-z0-9][a-z0-9._-]*")
    elif kind.startswith("ref:") or kind == "str":
        if not _nonempty(value):
            bad("must be a non-empty string")
    elif kind == "opt_str":
        if value is not None and not _nonempty(value):
            bad("must be null or a non-empty string")
    elif kind in ("url", "opt_url"):
        if kind == "opt_url" and value is None:
            return
        if not isinstance(value, str) or not re.match(r"^https://\S+$", value):
            bad("must be an https:// URL")
    elif kind in ("utc", "opt_utc"):
        if kind == "opt_utc" and value is None:
            return
        if not isinstance(value, str) or not UTC_RE.match(value):
            bad("must be a UTC timestamp like 2026-09-28T14:15:10Z")
            return
        try:
            moment = parse_utc(value)
        except ValueError:
            bad("is not a real date/time")
            return
        if moment > now:
            bad("is in the future")
    elif kind == "moment":
        if isinstance(value, str) and DATE_RE.match(value):
            day = _day(value)
            if day is None:
                bad("is not a real date")
            elif day > (now + DAY_TOLERANCE).date():
                bad("is in the future")
        elif not isinstance(value, str) or not UTC_RE.match(value):
            bad("must be a UTC timestamp like 2026-09-28T14:15:10Z or, "
                "when the source gives only a date, YYYY-MM-DD")
        else:
            _check_field("utc", value, where, errors, now)
    elif kind == "opt_date":
        if value is None:
            return
        if not isinstance(value, str) or not DATE_RE.match(value):
            bad("must be null (unknown) or YYYY-MM-DD")
            return
        try:
            day = date.fromisoformat(value)
        except ValueError:
            bad("is not a real date")
            return
        if day > now.date():
            bad("is in the future")
    elif kind.startswith("enum:"):
        allowed = ENUMS[kind[5:]]
        if not isinstance(value, str) or value not in allowed:
            bad(f"must be one of {sorted(allowed)}")
    elif kind == "obj":
        if not isinstance(value, dict):
            bad("must be an object")
    elif kind == "opt_obj_scalars":
        if value is None:
            return
        if not isinstance(value, dict) or not all(_is_json_scalar(v) for v in value.values()):
            bad("must be an object of strings, integers, finite numbers, booleans or nulls")
    elif kind == "list":
        if not isinstance(value, list):
            bad("must be a list")
    elif kind == "bool":
        if not isinstance(value, bool):
            bad("must be true or false")
    elif kind in ("sha256", "opt_sha256"):
        if kind == "opt_sha256" and value is None:
            return
        if not isinstance(value, str) or not re.match(r"^[0-9a-f]{64}$", value):
            bad("must be a lowercase sha256 hex digest")
    elif kind == "metric":
        _check_metric(value, where, errors)
    elif kind == "exclusions":
        if not isinstance(value, dict):
            bad("must be an object of counts (use {} only when none are reported)")
            return
        for name, count in value.items():
            if name not in EXCLUSION_KINDS:
                bad(f"unknown exclusion kind {name!r}; allowed {sorted(EXCLUSION_KINDS)}")
            elif not isinstance(count, int) or isinstance(count, bool) or count < 0:
                bad(f"exclusion {name!r} must be a non-negative integer")


def _check_metric(value, where: str, errors: list) -> None:
    if not isinstance(value, dict) or not _nonempty(value.get("name")):
        errors.append(f"{where}: must be an object with a non-empty name")
        return
    keys = set(value) - {"name"}
    if keys == {"numerator", "denominator"}:
        num, den = value["numerator"], value["denominator"]
        ints = all(isinstance(x, int) and not isinstance(x, bool) for x in (num, den))
        if not ints or den <= 0 or num < 0 or num > den:
            errors.append(f"{where}: needs integers with 0 <= numerator <= denominator, denominator > 0")
    elif keys == {"value", "unit"}:
        number = value["value"]
        if not isinstance(number, (int, float)) or isinstance(number, bool):
            errors.append(f"{where}: value must be a number")
        elif isinstance(number, float) and not math.isfinite(number):
            errors.append(f"{where}: value must be finite (not NaN, Infinity or overflow)")
        elif isinstance(number, int) and abs(number) > sys.float_info.max:
            # Exact ints are finite, but summaries use floats (review H1).
            errors.append(f"{where}: value is outside the representable number range")
        if not _nonempty(value["unit"]):
            errors.append(f"{where}: unit must be a non-empty string")
    else:
        errors.append(f"{where}: use {{name, numerator, denominator}} or {{name, value, unit}}")


def load_registry(folder: Path) -> tuple[dict, list]:
    records, errors = {}, []
    for kind in JSON_FILES:
        path = folder / f"{kind}.json"
        if not path.is_file():
            errors.append(f"{path.name}: missing")
            records[kind] = []
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            errors.append(f"{path.name}: invalid JSON ({exc})")
            records[kind] = []
            continue
        if not isinstance(data, dict) or set(data) != {"schema_version", "records"}:
            errors.append(f"{path.name}: must be {{\"schema_version\", \"records\"}}")
            records[kind] = []
            continue
        if data["schema_version"] != SCHEMA_VERSION:
            errors.append(f"{path.name}: schema_version {data['schema_version']!r} != {SCHEMA_VERSION}")
        records[kind] = data["records"] if isinstance(data["records"], list) else []
        if not isinstance(data["records"], list):
            errors.append(f"{path.name}: records must be a list")
    for kind, name in JSONL_FILES.items():
        records[kind], file_errors = load_jsonl(folder / name)
        errors.extend(file_errors)
    return records, errors


def load_jsonl(path: Path) -> tuple[list, list]:
    rows, errors = [], []
    if not path.is_file():
        return rows, [f"{path.name}: missing"]
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError as exc:
        return rows, [f"{path.name}: not UTF-8 ({exc})"]
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            errors.append(f"{path.name}:{number}: invalid JSON ({exc})")
    return rows, errors


def validate_records(records: dict, fixture_mode: bool = False,
                     now: datetime | None = None) -> list:
    now = now or datetime.now(timezone.utc)
    errors: list = []
    ids = {kind: {} for kind in FIELDS}

    for kind, spec in FIELDS.items():
        for index, record in enumerate(records.get(kind, [])):
            where = f"{kind}[{index}]"
            if not isinstance(record, dict):
                errors.append(f"{where}: must be an object")
                continue
            label = record.get("id", index)
            where = f"{kind}[{label}]"
            for name in sorted(set(record) - set(spec)):
                errors.append(f"{where}: unknown field {name!r}")
            for name, (field_kind, required) in spec.items():
                if name not in record:
                    if required:
                        errors.append(f"{where}.{name}: missing required field")
                    continue
                _check_field(field_kind, record[name], f"{where}.{name}", errors, now)
            is_fixture = record.get("fixture") is True
            if fixture_mode and not (is_fixture and str(record.get("id", "")).startswith("fixture-")):
                errors.append(f"{where}: fixture sets need fixture: true and an id starting 'fixture-'")
            if not fixture_mode and (is_fixture or str(record.get("id", "")).startswith("fixture-")):
                errors.append(f"{where}: test fixture found in production registry")
            if isinstance(record.get("id"), str):
                if record["id"] in ids[kind]:
                    errors.append(f"{where}: duplicate id")
                else:
                    ids[kind][record["id"]] = record

    for kind, spec in FIELDS.items():
        for record in ids[kind].values():
            for name, (field_kind, _) in spec.items():
                if field_kind.startswith("ref:") and _nonempty(record.get(name)):
                    target = field_kind[4:]
                    if record[name] not in ids[target]:
                        errors.append(f"{kind}[{record['id']}].{name}: unknown {target} id {record[name]!r}")

    seen_fingerprints = {}
    for series in ids["series"].values():
        expected = series_fingerprint(series, ids["routes"], ids["models"])
        if series.get("fingerprint") != expected:
            errors.append(f"series[{series['id']}].fingerprint: does not match configuration "
                          f"(expected {expected}); create a new series instead of editing one")
        if expected in seen_fingerprints:
            errors.append(f"series[{series['id']}]: same configuration as series "
                          f"{seen_fingerprints[expected]!r}")
        seen_fingerprints.setdefault(expected, series["id"])

    seen_moments = {}
    for obs in ids["observations"].values():
        where = f"observations[{obs['id']}]"
        observed = _instant(obs.get("observed_at"))
        observed_day = _day(obs.get("observed_at"))
        retrieved = _instant(obs.get("retrieved_at"))
        if retrieved and ((observed and retrieved < observed) or
                          (observed_day and (retrieved + DAY_TOLERANCE).date() < observed_day)):
            errors.append(f"{where}: retrieved_at is earlier than observed_at")
        if observed_day:
            observed = ("day", observed_day)
        series_id = _key(obs.get("series_id"))
        if series_id and observed:
            key = (series_id, observed)
            if key in seen_moments:
                errors.append(f"{where}: duplicates observation {seen_moments[key]!r} "
                              "(same series and observed_at instant)")
            seen_moments.setdefault(key, obs["id"])
        series = ids["series"].get(series_id)
        source = ids["sources"].get(_key(series.get("source_id"))) if series else None
        if source and source.get("reuse_decision") != "numeric_republication_permitted":
            errors.append(f"{where}: source {source['id']!r} reuse_decision is "
                          f"{source.get('reuse_decision')!r}; numeric metrics may not be stored")

    for run in ids["ingestion_runs"].values():
        started, finished = _instant(run.get("started_at")), _instant(run.get("finished_at"))
        if started and finished and finished < started:
            errors.append(f"ingestion_runs[{run['id']}]: finished_at is earlier than started_at")

    for correction in ids["corrections"].values():
        kind, target = correction.get("target_kind"), _key(correction.get("target_id"))
        if kind in CORRECTION_TARGETS and target and target not in ids[kind]:
            errors.append(f"corrections[{correction['id']}].target_id: unknown {kind} id {target!r}")
    return errors


def validate_registry(folder: Path, fixture_mode: bool = False,
                      now: datetime | None = None) -> list:
    records, errors = load_registry(Path(folder))
    return errors + validate_records(records, fixture_mode=fixture_mode, now=now)


def main(argv: list) -> int:
    args = [a for a in argv if a != "--fixtures"]
    fixture_mode = "--fixtures" in argv
    folder = Path(args[0]) if args else Path(__file__).resolve().parents[1] / "registry"
    errors = validate_registry(folder, fixture_mode=fixture_mode)
    mode = "fixture" if fixture_mode else "production"
    if errors:
        print(f"FAIL ({mode}) {folder}: {len(errors)} error(s)")
        for error in errors:
            print(f"  - {error}")
        return 1
    records, _ = load_registry(folder)
    counts = ", ".join(f"{kind}={len(records[kind])}" for kind in FIELDS)
    print(f"OK ({mode}) {folder}: {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
