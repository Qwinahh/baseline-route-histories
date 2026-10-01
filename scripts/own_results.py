"""Baseline's own test results: public validator, importer and site summary (T12). Stdlib only.

    py -3.11 -B scripts/own_results.py check                 # validate the production dataset
    py -3.11 -B scripts/own_results.py inspect CANDIDATE     # validate a candidate, print its sha256
    py -3.11 -B scripts/own_results.py import CANDIDATE      # admit a reviewed candidate

A candidate ("bundle") is an aggregate envelope written by the private exporter. It holds
counts, dates, the exact route, pinned settings and provenance hashes; never prompts,
responses, keys, account facts or local paths. Every field is on an exact allowlist.

Admission is explicit: a candidate is imported only if its file's sha256 is listed in
the separate review manifest (own_results/review.json). A bundle cannot admit itself.
This is an operational review gate, not a cryptographic guarantee against a dishonest
publisher; the hashes point to private evidence that visitors cannot inspect.

Importing is validated before anything is written, atomic and idempotent: the same
records again change nothing; a run already published with different contents is
refused (a reviewed correction would be needed, which this checkpoint does not provide).

This module never imports the private runner, reads private run folders or contacts any service.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "own_results" / "data.json"
REVIEW_PATH = ROOT / "own_results" / "review.json"
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "own_results"

BUNDLE_FORMAT, DATA_FORMAT, REVIEW_FORMAT = "baseline-own-results", "baseline-own-results-data", "baseline-own-results-review"
FORMAT_VERSION = 1
AGGREGATE_VERSION = 1
MAX_BYTES = 1_000_000
MAX_RECORDS = 400
MAX_ITEMS = 1000
MAX_ADMITTED = 1000

# The T11 daily aggregate keys and count rules (scripts/cloud_aggregate.py), kept here as a
# pure copy so the public package needs no private module; tests/test_own_results_export.py
# checks that both stay identical.
OPERATIONAL = ("timeout", "provider_error", "rate_limited", "auth_error", "client_error")
OUTCOME_KEYS = ("correct", "incorrect", "format_error", "answered_identity_mismatch", "answered_identity_unknown",
                "refusal", "truncated", "empty", "malformed") + OPERATIONAL + ("not_sent",)
RECOVERED_KEYS = ("correct", "format_error", "incorrect", "other")
SETTINGS = ("max_output_tokens", "temperature", "thinking_level", "timeout_seconds")
THINKING = ("MINIMAL", "LOW", "MEDIUM", "HIGH")
STATUSES = ("completed", "stopped", "interrupted", "gap")
EVIDENCE = ("verified", "unavailable", "none")
KINDS = ("calibration", "daily")
FIELDS = {
    "aggregate_version": int, "kind": str, "date": str, "status": str, "route_id": str, "requested_model": str,
    "settings": dict, "panel_id": str, "panel_sha256": str, "series_id": str, "config_fingerprint": str,
    "run_id": (str, type(None)), "report_sha256": (str, type(None)), "first_attempt_correct": (int, type(None)),
    "scheduled_items": (int, type(None)), "first_attempt_outcomes": (dict, type(None)),
    "retry_recovered": (dict, type(None)), "attempted_items": (int, type(None)), "valid_day": (bool, type(None)),
    "evidence": str, "interpretation": str,
}
COUNTS = ("first_attempt_correct", "scheduled_items", "first_attempt_outcomes", "retry_recovered",
          "attempted_items", "valid_day")
# Fixed wording only: no free text passes through from a private report.
INTERPRETATIONS = {
    "daily": ("Counts from Baseline's own runs on one route. Not a quality score, and not a decline, "
              "improvement or stability verdict."),
    "calibration": ("One-off setup test of one route, run once before daily testing. Not part of the daily "
                    "history, not a quality score, and not a decline, improvement or stability verdict."),
}
ACCESS_KINDS = ("direct_api", "intermediary", "cloud_platform")
ROUTE_FIELDS = ("access_kind", "exact_identifier", "maker", "route_id")
SERIES_FIELDS = ("config_fingerprint", "grader_version", "kind", "panel_categories", "panel_id", "panel_items",
                 "panel_sha256", "schedule", "series_id", "settings")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,159}$")
MODEL_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,99}$")
MAKER_RE = re.compile(r"^[A-Z][A-Za-z0-9 .&-]{0,39}$")
CATEGORY_RE = re.compile(r"^[a-z][a-z_]{0,39}$")
GRADER_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{0,39}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
RUN_ID_RE = re.compile(r"^live-(daily|calibration)-(\d{8})T(\d{6})Z-([0-9a-f]{10})$")
STAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
HHMM_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
SECRETISH = re.compile(r"AIza[0-9A-Za-z_\-]{20,}|gh[pousr]_[0-9A-Za-z]{20,}|github_pat_|sk-[A-Za-z0-9]{20,}|"
                       r"-----BEGIN|x-goog-api-key|api[_-]?key|authorization", re.I)
FIXTURE_MARK = "FIXTURE-NOT-FOR-PUBLICATION"
# Display convention: a daily series whose newest usable result is older than this is not shown as current.
STALE_DAYS = 2


class OwnResultsError(Exception):
    """A bundle, dataset or review manifest breaks the contract. Nothing is written."""


# ---------------------------------------------------------------- small checks

def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _sha(value) -> bool:
    return isinstance(value, str) and SHA_RE.match(value) is not None


def _finite(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _count(value, low=0, high=MAX_ITEMS) -> bool:
    return type(value) is int and low <= value <= high


def _day(value) -> date:
    try:
        parsed = date.fromisoformat(value) if isinstance(value, str) and len(value) == 10 else None
    except ValueError:
        parsed = None
    if parsed is None or parsed.isoformat() != value:
        raise OwnResultsError(f"{value!r} is not a real YYYY-MM-DD date")
    return parsed


def parse_stamp(value) -> datetime:
    """Canonical UTC stamp 'YYYY-MM-DDTHH:MM:SSZ' only."""
    if not isinstance(value, str) or not STAMP_RE.match(value):
        raise OwnResultsError(f"{value!r} is not a canonical UTC time (YYYY-MM-DDTHH:MM:SSZ)")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        raise OwnResultsError(f"{value!r} is not a real time") from None


def stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_started(run_id: str) -> tuple[str, datetime]:
    """(kind, start time) from a run ID; raises if it is not a real run ID."""
    match = RUN_ID_RE.match(run_id) if isinstance(run_id, str) else None
    if not match:
        raise OwnResultsError("run id is not a Baseline run id")
    try:
        started = datetime.strptime(match.group(2) + match.group(3), "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        raise OwnResultsError("run id holds an impossible start time") from None
    return match.group(1), started


def _exact(value, fields, where: str) -> None:
    if not isinstance(value, dict) or set(value) != set(fields):
        raise OwnResultsError(f"{where} must have exactly the fields {sorted(fields)}")


def check_settings(settings) -> None:
    _exact(settings, SETTINGS, "settings")
    if not _finite(settings["temperature"]) or not 0 <= settings["temperature"] <= 2 \
            or type(settings["max_output_tokens"]) is not int or not 1 <= settings["max_output_tokens"] <= 1_000_000 \
            or not _finite(settings["timeout_seconds"]) or not 0 < settings["timeout_seconds"] <= 3600 \
            or settings["thinking_level"] not in THINKING:
        raise OwnResultsError("settings must be exactly the pinned, finite execution settings")


# ---------------------------------------------------------------- one aggregate record

def validate_record(record) -> None:
    """Exact fields and types, then every count and nullability rule (the T11 rules)."""
    _exact(record, FIELDS, "a record")
    for key, kind in FIELDS.items():
        allowed = kind if isinstance(kind, tuple) else (kind,)
        if not isinstance(record[key], kind) or (isinstance(record[key], bool) and bool not in allowed):
            raise OwnResultsError(f"{key} has the wrong type")              # True is an int in Python; refuse it
    if record["aggregate_version"] != AGGREGATE_VERSION or record["kind"] not in KINDS \
            or record["status"] not in STATUSES or record["evidence"] not in EVIDENCE:
        raise OwnResultsError("unknown version, kind, status or evidence")
    if record["interpretation"] != INTERPRETATIONS[record["kind"]]:
        raise OwnResultsError("interpretation must be the fixed wording for its kind")
    _day(record["date"])
    for name, pattern in (("route_id", ID_RE), ("series_id", ID_RE), ("panel_id", ID_RE), ("requested_model", MODEL_RE)):
        if not pattern.match(record[name]):
            raise OwnResultsError(f"{name} has characters outside the allowed set")
    check_settings(record["settings"])
    for name in ("panel_sha256", "config_fingerprint"):
        if not _sha(record[name]):
            raise OwnResultsError(f"{name} must be a sha256")
    if record["report_sha256"] is not None and not _sha(record["report_sha256"]):
        raise OwnResultsError("report_sha256 must be a sha256")
    if record["status"] == "gap":
        if record["kind"] != "daily":
            raise OwnResultsError("only a daily series has gaps")
        if record["evidence"] != "none" or record["run_id"] is not None or record["report_sha256"] is not None \
                or any(record[k] is not None for k in COUNTS):
            raise OwnResultsError("a gap carries no run, report or counts")
    else:
        kind, started = run_started(record["run_id"])
        if kind != record["kind"] or started.date().isoformat() != record["date"]:
            raise OwnResultsError("run id must be a run of this kind started on the record's date")
        if not record["run_id"].endswith(record["config_fingerprint"][:10]):
            raise OwnResultsError("run id does not belong to this configuration")
        if record["evidence"] == "none":
            raise OwnResultsError("a run record needs verified or unavailable evidence")
        if record["evidence"] == "unavailable" and any(record[k] is not None for k in COUNTS):
            raise OwnResultsError("counts without verified evidence are not published")
        if record["evidence"] == "verified":
            if any(record[k] is None for k in COUNTS) or record["report_sha256"] is None:
                raise OwnResultsError("verified evidence needs every count and the report hash")
            _check_counts(record)
    if SECRETISH.search(json.dumps(record)) or FIXTURE_MARK in json.dumps(record):
        raise OwnResultsError("record contains something that looks like a credential or a fixture label")


def _check_counts(record: dict) -> None:
    scheduled, outcomes = record["scheduled_items"], record["first_attempt_outcomes"]
    if not _count(scheduled, 1):
        raise OwnResultsError("scheduled_items is out of range")
    if set(outcomes) != set(OUTCOME_KEYS) or not all(_count(v, 0, scheduled) for v in outcomes.values()):
        raise OwnResultsError("first_attempt_outcomes must hold exactly the outcome counts, each within range")
    if sum(outcomes.values()) != scheduled:
        raise OwnResultsError("outcome counts must add up to the scheduled items")
    if record["first_attempt_correct"] != outcomes["correct"]:
        raise OwnResultsError("first_attempt_correct must equal the correct outcome count")
    if record["attempted_items"] != scheduled - outcomes["not_sent"]:
        raise OwnResultsError("attempted_items must equal scheduled minus not sent")
    if record["valid_day"] != (record["attempted_items"] >= 0.9 * scheduled):
        raise OwnResultsError("valid_day must follow the 90%-attempted rule")
    recovered = record["retry_recovered"]
    operational = sum(outcomes[k] for k in OPERATIONAL)
    if set(recovered) != set(RECOVERED_KEYS) or not all(_count(v) for v in recovered.values()) \
            or sum(recovered.values()) > operational:
        raise OwnResultsError("retry_recovered must be counts no larger than the operational first attempts")


# ---------------------------------------------------------------- route, series and bundle

def check_route(route) -> None:
    _exact(route, ROUTE_FIELDS, "route")
    if not ID_RE.match(str(route["route_id"])) or not MODEL_RE.match(str(route["exact_identifier"])) \
            or not MAKER_RE.match(str(route["maker"])) or route["access_kind"] not in ACCESS_KINDS:
        raise OwnResultsError("route needs an id, maker, exact identifier and API access kind")


def check_series(series, route: dict) -> None:
    _exact(series, SERIES_FIELDS, "series")
    if series["kind"] not in KINDS or not _sha(series["config_fingerprint"]) or not _sha(series["panel_sha256"]):
        raise OwnResultsError("series needs a known kind and sha256 fingerprints")
    if series["series_id"] != f"{route['route_id']}--{series['kind']}--{series['config_fingerprint'][:12]}":
        raise OwnResultsError("series id must be route--kind--fingerprint prefix")
    if not isinstance(series["panel_id"], str) or not ID_RE.match(series["panel_id"]) \
            or not isinstance(series["grader_version"], str) or not GRADER_RE.match(series["grader_version"]) \
            or not _count(series["panel_items"], 1):
        raise OwnResultsError("series panel or grader description is invalid")
    cats = series["panel_categories"]
    if not isinstance(cats, list) or not 1 <= len(cats) <= 12 or len(set(map(str, cats))) != len(cats) \
            or not all(isinstance(c, str) and CATEGORY_RE.match(c) for c in cats):
        raise OwnResultsError("panel_categories must be 1-12 distinct lower-case names")
    check_settings(series["settings"])
    schedule = series["schedule"]
    if series["kind"] == "calibration":
        if schedule != {"type": "once"}:
            raise OwnResultsError("a calibration series is scheduled once")
        return
    _exact(schedule, ("end_date", "start_date", "type", "window_minutes", "window_start_utc"), "schedule")
    start, end = _day(schedule["start_date"]), _day(schedule["end_date"])
    if schedule["type"] != "daily" or not start <= end or (end - start).days > 366 \
            or not isinstance(schedule["window_start_utc"], str) or not HHMM_RE.match(schedule["window_start_utc"]) \
            or not _count(schedule["window_minutes"], 1, 1440):
        raise OwnResultsError("a daily schedule needs real start/end dates (at most a year) and a UTC window")


def _record_key(record: dict) -> str:
    return record["run_id"] or "gap:" + record["date"]


def check_body(body: dict, now: datetime | None = None) -> None:
    """as_of, route, series and records, with every record bound to the route and series."""
    _exact(body, ("as_of", "records", "route", "series"), "series entry")
    as_of = parse_stamp(body["as_of"])
    if now is not None and as_of > now + timedelta(minutes=5):
        raise OwnResultsError("as_of is in the future")
    route, series, records = body["route"], body["series"], body["records"]
    check_route(route)
    check_series(series, route)
    if not isinstance(records, list) or len(records) > MAX_RECORDS:
        raise OwnResultsError(f"records must be a list of at most {MAX_RECORDS}")
    keys, dates = set(), set()
    for record in records:
        validate_record(record)
        bound = {"route_id": route["route_id"], "requested_model": route["exact_identifier"],
                 "kind": series["kind"], "series_id": series["series_id"], "settings": series["settings"],
                 "config_fingerprint": series["config_fingerprint"], "panel_id": series["panel_id"],
                 "panel_sha256": series["panel_sha256"]}
        for key, value in bound.items():
            if record[key] != value:
                raise OwnResultsError(f"record {_record_key(record)} has a {key} different from its series")
        if record["scheduled_items"] is not None and record["scheduled_items"] != series["panel_items"]:
            raise OwnResultsError(f"record {_record_key(record)} schedules a different number of items")
        if record["date"] > as_of.date().isoformat() or \
                (record["run_id"] and run_started(record["run_id"])[1] > as_of):
            raise OwnResultsError(f"record {_record_key(record)} is later than as_of")
        if series["kind"] == "daily":
            sched = series["schedule"]
            if not sched["start_date"] <= record["date"] <= sched["end_date"]:
                raise OwnResultsError(f"record {_record_key(record)} is outside the scheduled campaign")
            if record["date"] in dates:
                raise OwnResultsError(f"two records for {record['date']} in one daily series")
            dates.add(record["date"])
        if _record_key(record) in keys:
            raise OwnResultsError(f"duplicate record {_record_key(record)}")
        keys.add(_record_key(record))


def validate_bundle(bundle, now: datetime | None = None) -> None:
    """Raise OwnResultsError unless `bundle` is a well-formed aggregate envelope."""
    if not isinstance(bundle, dict) or bundle.get("format") != BUNDLE_FORMAT or bundle.get("format_version") != FORMAT_VERSION:
        raise OwnResultsError(f"not a {BUNDLE_FORMAT} v{FORMAT_VERSION} bundle")
    _exact(bundle, ("as_of", "format", "format_version", "records", "route", "series"), "bundle")
    check_body({k: bundle[k] for k in ("as_of", "records", "route", "series")}, now)
    if not bundle["records"]:
        raise OwnResultsError("a bundle without records has nothing to publish")


def _reject_constant(name):
    raise OwnResultsError(f"non-finite number {name} is not allowed")


def parse_json(raw: bytes, what: str):
    if len(raw) > MAX_BYTES:
        raise OwnResultsError(f"{what} is larger than {MAX_BYTES} bytes")
    try:
        return json.loads(raw.decode("utf-8"), parse_constant=_reject_constant)
    except (UnicodeDecodeError, ValueError) as exc:
        raise OwnResultsError(f"{what} is not valid JSON: {type(exc).__name__}") from None


def dumps(value) -> bytes:
    return (json.dumps(value, indent=1, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


# ---------------------------------------------------------------- dataset and review manifest

def empty_dataset() -> dict:
    return {"format": DATA_FORMAT, "format_version": FORMAT_VERSION, "series": {}, "sources": []}


def empty_review() -> dict:
    return {"format": REVIEW_FORMAT, "format_version": FORMAT_VERSION, "admitted": []}


def _check_sources(entries, what: str) -> None:
    if not isinstance(entries, list) or len(entries) > MAX_ADMITTED:
        raise OwnResultsError(f"{what} must be a list")
    seen = set()
    for entry in entries:
        _exact(entry, ("reviewed_at", "sha256"), f"an entry of {what}")
        parse_stamp(entry["reviewed_at"])
        if not _sha(entry["sha256"]) or entry["sha256"] in seen:
            raise OwnResultsError(f"{what} needs distinct sha256 digests")
        seen.add(entry["sha256"])
    if entries != sorted(entries, key=lambda e: e["sha256"]):
        raise OwnResultsError(f"{what} must be sorted by sha256")


def validate_review(review) -> None:
    if not isinstance(review, dict) or review.get("format") != REVIEW_FORMAT or review.get("format_version") != FORMAT_VERSION:
        raise OwnResultsError(f"not a {REVIEW_FORMAT} v{FORMAT_VERSION} manifest")
    _exact(review, ("admitted", "format", "format_version"), "review manifest")
    _check_sources(review["admitted"], "review admitted list")


def validate_dataset(dataset, now: datetime | None = None) -> None:
    if not isinstance(dataset, dict) or dataset.get("format") != DATA_FORMAT or dataset.get("format_version") != FORMAT_VERSION:
        raise OwnResultsError(f"not a {DATA_FORMAT} v{FORMAT_VERSION} dataset")
    _exact(dataset, ("format", "format_version", "series", "sources"), "dataset")
    _check_sources(dataset["sources"], "dataset sources")
    if not isinstance(dataset["series"], dict):
        raise OwnResultsError("dataset series must be an object keyed by series id")
    if bool(dataset["series"]) != bool(dataset["sources"]):
        raise OwnResultsError("published series need admitted sources, and admitted sources need series")
    for sid, body in dataset["series"].items():
        check_body(body, now)
        if body["series"]["series_id"] != sid or not body["records"]:
            raise OwnResultsError(f"dataset series {sid} is misfiled or empty")
        if body["records"] != sorted(body["records"], key=lambda r: (r["date"], _record_key(r))):
            raise OwnResultsError(f"dataset series {sid} records are not in date order")


def load_json_file(path: Path, what: str):
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        raise OwnResultsError(f"cannot read {what}: {type(exc).__name__}") from None
    return parse_json(raw, what)


def load_review(path: Path = REVIEW_PATH) -> dict:
    review = load_json_file(path, "review manifest")
    validate_review(review)
    return review


def load_dataset(path: Path = DATA_PATH, now: datetime | None = None) -> dict:
    dataset = load_json_file(path, "own-results dataset")
    validate_dataset(dataset, now)
    return dataset


def admitted_dir_for(data_path: Path) -> Path:
    """Exact copies of every admitted candidate, named by sha256, beside the dataset."""
    return Path(data_path).parent / "admitted"


def rebuild(sources: list, review: dict, admitted_dir: Path, now: datetime | None = None) -> dict:
    """The dataset as merged from the admitted candidate copies named by `sources`.

    Every source must be in the review manifest with the same review time, and its kept
    copy must still have that digest and pass the bundle contract.
    """
    reviewed = {e["sha256"]: e for e in review["admitted"]}
    dataset = empty_dataset()
    for source in sorted(sources, key=lambda s: s["sha256"]):
        if reviewed.get(source["sha256"]) != source:
            raise OwnResultsError(f"dataset source {source['sha256'][:12]} was not admitted by the review manifest")
        try:
            raw = (Path(admitted_dir) / f"{source['sha256']}.json").read_bytes()
        except OSError:
            raise OwnResultsError(f"the admitted copy of {source['sha256'][:12]} is missing") from None
        if sha256_bytes(raw) != source["sha256"]:
            raise OwnResultsError(f"the admitted copy of {source['sha256'][:12]} was altered or substituted")
        bundle = parse_json(raw, "admitted copy")
        validate_bundle(bundle, now)
        dataset = merge(dataset, bundle, source)
    return dataset


def load_admitted(data_path: Path = DATA_PATH, review_path: Path = REVIEW_PATH, now: datetime | None = None) -> dict:
    """The dataset, only if it is exactly what its admitted, reviewed candidates give.

    Binding published records to reviewed content (T12 review R1): the kept candidate
    copies are re-merged and must reproduce data.json byte for byte, and the admitted
    folder holds exactly the copies the dataset names. An edited count, an added or
    removed record, changed route or settings, or a missing or substituted copy fails.
    This detects accidental or unreviewed edits; it is not a defence against a
    publisher who deliberately rewrites the review manifest and copies as well.
    """
    try:
        raw = Path(data_path).read_bytes()
    except OSError as exc:
        raise OwnResultsError(f"cannot read own-results dataset: {type(exc).__name__}") from None
    dataset = parse_json(raw, "own-results dataset")
    validate_dataset(dataset, now)
    review = load_review(review_path)
    folder = admitted_dir_for(data_path)
    present = {p.name for p in folder.iterdir()} if folder.is_dir() else set()
    named = {f"{s['sha256']}.json" for s in dataset["sources"]}
    if present != named:
        raise OwnResultsError(f"{folder.name}/ must hold exactly the admitted copies the dataset names "
                              f"(unexpected {sorted(present - named)[:3]}, missing {sorted(named - present)[:3]})")
    if dumps(rebuild(dataset["sources"], review, folder, now)) != raw:
        raise OwnResultsError("the dataset does not match a rebuild from its admitted candidates; "
                              "re-import reviewed candidates instead of editing data.json")
    return dataset


def fixture_digests(folder: Path = FIXTURE_DIR) -> set:
    """Digests of every synthetic fixture; these may never be admitted to production."""
    if not Path(folder).is_dir():
        return set()
    return {sha256_bytes(p.read_bytes()) for p in sorted(Path(folder).rglob("*")) if p.is_file()}


# ---------------------------------------------------------------- merging and importing

def merge(dataset: dict, bundle: dict, source: dict | None) -> dict:
    """A new dataset with `bundle` merged in. Identical records are no-ops; any conflict raises."""
    out = json.loads(json.dumps(dataset))
    body = {k: bundle[k] for k in ("as_of", "records", "route", "series")}
    sid = body["series"]["series_id"]
    current = out["series"].get(sid)
    if current is None:
        current = out["series"][sid] = {"as_of": body["as_of"], "route": body["route"], "series": body["series"],
                                         "records": []}
    elif current["route"] != body["route"] or current["series"] != body["series"]:
        raise OwnResultsError(f"series {sid} is already published with different route or series details; "
                              "a reviewed correction is required")
    by_key = {_record_key(r): r for r in current["records"]}
    daily = body["series"]["kind"] == "daily"
    by_date = {r["date"]: r for r in current["records"]} if daily else {}
    for record in body["records"]:
        key = _record_key(record)
        if key in by_key:
            if by_key[key] != record:
                raise OwnResultsError(f"{key} is already published with different contents; "
                                      "a reviewed correction is required (not supported in this checkpoint)")
            continue
        if record["date"] in by_date:
            raise OwnResultsError(f"{record['date']} already has a different published record in {sid}; "
                                  "a reviewed correction is required")
        by_key[key] = record
        if daily:
            by_date[record["date"]] = record
    current["records"] = sorted(by_key.values(), key=lambda r: (r["date"], _record_key(r)))
    current["as_of"] = max(current["as_of"], body["as_of"])
    if source is not None and source["sha256"] not in {s["sha256"] for s in out["sources"]}:
        out["sources"] = sorted(out["sources"] + [dict(source)], key=lambda s: s["sha256"])
    return out


def _atomic_write(path: Path, raw: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    with open(tmp, "wb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def import_bundle(input_path: Path, review_path: Path = REVIEW_PATH, output_path: Path = DATA_PATH,
                  now: datetime | None = None) -> str:
    """Admit one reviewed bundle into the dataset. Returns 'unchanged' or 'updated'.

    Order: the file's digest must be admitted; the bundle, the review manifest and the
    existing dataset (rebuilt from its admitted copies) must validate; the merge must be
    conflict-free. Then the exact candidate bytes are kept in admitted/<sha256>.json and
    the new dataset is written, each atomically. Any refusal leaves both unchanged.
    If the process stops between the two writes, the next load fails closed (an
    unexpected admitted copy); remove that copy and import again.
    """
    now = now or datetime.now(timezone.utc)
    try:
        raw = Path(input_path).read_bytes()
    except OSError as exc:
        raise OwnResultsError(f"cannot read the candidate: {type(exc).__name__}") from None
    digest = sha256_bytes(raw)
    review = load_review(review_path)
    entry = next((e for e in review["admitted"] if e["sha256"] == digest), None)
    if entry is None:
        raise OwnResultsError(f"candidate {digest} is not admitted; a reviewer must add this digest to "
                              f"{Path(review_path).name} after reviewing it")
    if digest in fixture_digests() and Path(review_path).resolve() == REVIEW_PATH.resolve():
        raise OwnResultsError("a synthetic test fixture cannot be admitted to the production dataset")
    bundle = parse_json(raw, "candidate")
    validate_bundle(bundle, now)
    output_path = Path(output_path)
    folder = admitted_dir_for(output_path)
    if output_path.exists():
        existing_raw = output_path.read_bytes()
        dataset = load_admitted(output_path, review_path, now)
    else:
        if folder.is_dir() and any(folder.iterdir()):
            raise OwnResultsError(f"{folder.name}/ holds copies but there is no dataset; review it before importing")
        existing_raw, dataset = None, empty_dataset()
    merged = merge(dataset, bundle, entry)
    validate_dataset(merged, now)
    new_raw = dumps(merged)
    if new_raw == existing_raw:
        return "unchanged"
    copy = folder / f"{digest}.json"
    if copy.exists() and copy.read_bytes() != raw:
        raise OwnResultsError(f"{copy.name} exists with different bytes; review the admitted folder")
    wrote_copy = not copy.exists()
    if wrote_copy:
        _atomic_write(copy, raw)
    try:
        if dumps(rebuild(merged["sources"], review, folder, now)) != new_raw:   # the copies reproduce it
            raise OwnResultsError("internal error: the admitted copies do not reproduce the merged dataset")
    except OwnResultsError:
        if wrote_copy:
            copy.unlink()
        raise
    _atomic_write(output_path, new_raw)
    return "updated"


# ---------------------------------------------------------------- site summary

def expected_dates(schedule: dict, as_of: datetime) -> tuple[list, int]:
    """(campaign dates whose window had closed by as_of, count of campaign dates not yet due)."""
    start, end = _day(schedule["start_date"]), _day(schedule["end_date"])
    hour, minute = map(int, schedule["window_start_utc"].split(":"))
    due, later = [], 0
    day = start
    while day <= end:
        closes = datetime(day.year, day.month, day.day, hour, minute, tzinfo=timezone.utc) \
            + timedelta(minutes=schedule["window_minutes"])
        if closes <= as_of:
            due.append(day.isoformat())
        else:
            later += 1
        day += timedelta(days=1)
    return due, later


def _usable(record: dict) -> bool:
    return record["evidence"] == "verified" and record["valid_day"] is True


def daily_rows(body: dict) -> dict:
    """Every campaign date up to as_of: a run, an explicit gap, or 'no_record' (never filled in)."""
    as_of = parse_stamp(body["as_of"])
    due, later = expected_dates(body["series"]["schedule"], as_of)
    by_date = {r["date"]: r for r in body["records"]}
    rows = [{"date": d, "state": by_date[d]["status"] if d in by_date else "no_record", "record": by_date.get(d)}
            for d in due]
    for record in body["records"]:                       # a run published although its window closed after as_of
        if record["date"] not in due:
            rows.append({"date": record["date"], "state": record["status"], "record": record})
    rows.sort(key=lambda r: r["date"])
    return {"rows": rows, "not_yet_due": later - sum(1 for r in body["records"] if r["date"] not in due)}


def map_entry(route: dict, catalog_entries: list) -> str:
    """The one catalogue entry with the same maker, exact identifier and access kind."""
    hits = [e["id"] for e in catalog_entries if e.get("identity_kind") == "exact" and e.get("maker") == route["maker"]
            and e.get("exact_identifier") == route["exact_identifier"] and e.get("access_kind") == route["access_kind"]]
    if len(hits) != 1:
        raise OwnResultsError(f"route {route['route_id']} matches {len(hits)} catalogue entries (expected exactly one "
                              "exact entry with the same maker, identifier and access)")
    return hits[0]


def site_tests(dataset: dict, catalog_entries: list) -> dict:
    """The page's baseline_tests record. Calibration and daily evidence stay separate."""
    entries, methods = {}, []
    for sid in sorted(dataset["series"]):
        body = dataset["series"][sid]
        entry_id = map_entry(body["route"], catalog_entries)
        rec = entries.setdefault(entry_id, {"route_id": body["route"]["route_id"], "runs": 0, "latest_run": None,
                                            "latest_attempt": None, "baseline_complete": False, "daily": None,
                                            "calibration": []})
        if rec["route_id"] != body["route"]["route_id"]:
            raise OwnResultsError(f"catalogue entry {entry_id} would mix two routes")
        series = body["series"]
        method = {k: series[k] for k in ("panel_id", "panel_items", "panel_categories", "grader_version", "settings")}
        if method not in methods:
            methods.append(method)
        if series["kind"] == "calibration":
            rec["calibration"] = sorted(rec["calibration"] + body["records"], key=lambda r: (r["date"], r["run_id"]))
            continue
        if rec["daily"] is not None:
            raise OwnResultsError(f"catalogue entry {entry_id} has more than one daily series; not supported yet")
        rows = daily_rows(body)
        usable = [r["record"] for r in rows["rows"] if r["record"] is not None and _usable(r["record"])]
        last = rows["rows"][-1] if rows["rows"] else None
        rec["daily"] = {"series_id": sid, "as_of": body["as_of"], "schedule": series["schedule"],
                        "rows": rows["rows"], "not_yet_due": rows["not_yet_due"]}
        rec["runs"] = len(usable)
        rec["latest_run"] = usable[-1]["date"] if usable else None
        if last is not None:
            rec["latest_attempt"] = "ok" if last["record"] is not None and _usable(last["record"]) else "failed"
    return {"runs": sum(r["runs"] for r in entries.values()),
            "calibration_runs": sum(len(r["calibration"]) for r in entries.values()),
            "entries": entries, "methods": methods}


EMPTY_TESTS = {"runs": 0, "calibration_runs": 0, "entries": {}, "methods": []}


# ---------------------------------------------------------------- command line

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command", choices=("check", "inspect", "import"))
    parser.add_argument("candidate", nargs="?")
    parser.add_argument("--data", default=str(DATA_PATH))
    parser.add_argument("--review", default=str(REVIEW_PATH))
    args = parser.parse_args(argv)
    try:
        if args.command == "check":
            dataset = load_admitted(Path(args.data), Path(args.review), datetime.now(timezone.utc))
            count = sum(len(b["records"]) for b in dataset["series"].values())
            print(f"OK: {len(dataset['series'])} series, {count} records, {len(dataset['sources'])} admitted sources")
            return 0
        if not args.candidate:
            parser.error("a candidate file is required")
        if args.command == "inspect":
            raw = Path(args.candidate).read_bytes()
            bundle = parse_json(raw, "candidate")
            validate_bundle(bundle, datetime.now(timezone.utc))
            print(f"valid candidate sha256 {sha256_bytes(raw)}")
            print(f"series {bundle['series']['series_id']} ({bundle['series']['kind']}), as of {bundle['as_of']}")
            for r in sorted(bundle["records"], key=lambda r: (r["date"], _record_key(r))):
                score = (f"{r['first_attempt_correct']} of {r['scheduled_items']} first attempts correct"
                         if r["evidence"] == "verified" else "no counts")
                print(f"  {r['date']} {r['status']} evidence={r['evidence']}: {score}")
            return 0
        print(import_bundle(Path(args.candidate), Path(args.review), Path(args.data)))
        return 0
    except (OwnResultsError, OSError) as exc:
        print(f"FAIL: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
