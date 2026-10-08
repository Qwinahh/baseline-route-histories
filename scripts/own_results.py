"""Baseline's own test results: public validator, importer and site summary (T12, T13). Stdlib only.

    py -3.11 -B scripts/own_results.py check                 # validate the production dataset
    py -3.11 -B scripts/own_results.py inspect CANDIDATE     # validate a candidate, print its sha256
    py -3.11 -B scripts/own_results.py import CANDIDATE      # admit a person-reviewed candidate
    py -3.11 -B scripts/own_results.py check-policy POLICY   # validate a publication policy, print its sha256
    py -3.11 -B scripts/own_results.py migrate               # dataset v1 -> v2 (content unchanged)

A candidate ("bundle") is an aggregate envelope written by the private exporter. It holds
counts, dates, the exact route, pinned settings and provenance hashes; never prompts,
responses, keys, account facts or local paths. Every field is on an exact allowlist.

Admission is explicit: a candidate is imported only if its file's sha256 is listed in
the separate review manifest (own_results/review.json). A bundle cannot admit itself.
This is an operational review gate, not a cryptographic guarantee against a dishonest
publisher; the hashes point to private evidence that visitors cannot inspect.

Since T13 a candidate can also be admitted automatically under a publication policy that
a person approved (own_results/policy_review.json lists its digest; policies/ keeps it).
Such sources are labelled policy-admitted, never person-reviewed, and the bundle must
match the policy exactly. The automated publisher cannot create or change a policy.

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
FORMAT_VERSION = 1                 # review manifest
BUNDLE_VERSIONS = (1, 2, 3)        # 2 (T13) also allows a schedule-only daily bundle; 3 is the Puter subset contract
BUNDLE_VERSION = 2                 # what the exporter writes now
DATA_VERSION = 2                   # 2 (T13): sources may be person-reviewed or policy-admitted
POLICY_FORMAT, POLICY_REVIEW_FORMAT = "baseline-own-results-policy", "baseline-own-results-policy-review"
POLICY_FIELDS = ("allowed_paths", "campaign", "config_fingerprint", "enabled", "format", "format_version",
                 "grader_version", "panel_items", "panel_sha256", "public_branch", "public_repository", "route",
                 "series_kind", "settings")
# The only public paths an automated publisher may write.
PUBLICATION_PATHS = ("own_results/admitted/", "own_results/data.json")
HUMAN_SOURCE = ("reviewed_at", "sha256")
POLICY_SOURCE = ("admitted_at", "policy_sha256", "sha256")
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
REPO_RE = re.compile(r"^[A-Za-z0-9-]{1,39}/[A-Za-z0-9._-]{1,100}$")
BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,99}$")
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
    """Maker API routes have exactly ROUTE_FIELDS; a hosted route (T14) also names its host as
    `service_provider`, so its results attach only to that host's catalogue entry."""
    hosted = isinstance(route, dict) and route.get("access_kind") in ("intermediary", "cloud_platform")
    _exact(route, ROUTE_FIELDS + (("service_provider",) if hosted else ()), "route")
    if not ID_RE.match(str(route["route_id"])) or not MODEL_RE.match(str(route["exact_identifier"])) \
            or not MAKER_RE.match(str(route["maker"])) or route["access_kind"] not in ACCESS_KINDS:
        raise OwnResultsError("route needs an id, maker, exact identifier and API access kind")
    if hosted and (not isinstance(route["service_provider"], str) or not MAKER_RE.match(route["service_provider"])
                   or route["service_provider"] == route["maker"]):
        raise OwnResultsError("a hosted route names its host (service_provider), which is not the maker")


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
    check_schedule(schedule)


def _record_key(record: dict) -> str:
    return record["run_id"] or "gap:" + record["date"]


BODY_FIELDS = ("as_of", "records", "route", "series")


def check_body(body: dict, now: datetime | None = None) -> None:
    """as_of, route, series and records, with every record bound to the route and series.

    A daily body may also list `open_dates` (T13 review R2): scheduled dates whose run had
    started but not closed when the private record was checked. They carry no score, are
    never records, and stay unresolved until a later check closes them.
    """
    if not isinstance(body, dict) or set(body) not in (set(BODY_FIELDS), set(BODY_FIELDS) | {"open_dates"}):
        raise OwnResultsError(f"series entry must have exactly the fields {list(BODY_FIELDS)} (+ open_dates if daily)")
    if is_puter(body):
        check_puter_body(body, now)
        return
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
    if "open_dates" in body:
        _check_open_dates(body, as_of, {r["date"] for r in records})


def _check_open_dates(body: dict, as_of: datetime, record_dates: set) -> None:
    open_dates = body["open_dates"]
    if body["series"]["kind"] != "daily":
        raise OwnResultsError("only a daily series has open dates")
    if not isinstance(open_dates, list) or len(open_dates) > MAX_RECORDS \
            or open_dates != sorted(set(open_dates)) or not all(isinstance(d, str) for d in open_dates):
        raise OwnResultsError("open_dates must be a sorted list of distinct dates")
    schedule = body["series"]["schedule"]
    for day in open_dates:
        parsed = _day(day)
        if not schedule["start_date"] <= day <= schedule["end_date"]:
            raise OwnResultsError(f"open date {day} is outside the scheduled campaign")
        if window_bounds(schedule, parsed)[1] > as_of:
            raise OwnResultsError(f"open date {day} was not yet due at as_of; it is simply pending")
        if day in record_dates:
            raise OwnResultsError(f"open date {day} already has a record")


def validate_bundle(bundle, now: datetime | None = None) -> None:
    """Raise OwnResultsError unless `bundle` is a well-formed aggregate envelope.

    Version 1 (T12) always holds records. Version 2 (T13) may also be a schedule-only
    daily bundle with no records yet: it publishes the route, series and campaign so the
    graph can exist before the first closed run, and it never counts as a test.
    """
    version = bundle.get("format_version") if isinstance(bundle, dict) else None
    if not isinstance(bundle, dict) or bundle.get("format") != BUNDLE_FORMAT or version not in BUNDLE_VERSIONS \
            or isinstance(version, bool):
        raise OwnResultsError(f"not a {BUNDLE_FORMAT} bundle of a known version {BUNDLE_VERSIONS}")
    fields = BODY_FIELDS + ("format", "format_version") + (("open_dates",) if version in (2, 3) else ())
    _exact(bundle, fields, "bundle")
    if (version == 3) != is_puter(bundle):
        raise OwnResultsError("version 3 is exactly the Puter subset contract; versions 1 and 2 never carry it")
    if version == 2 and bundle["series"]["kind"] != "daily":
        raise OwnResultsError("a version-2 bundle is a daily bundle")
    check_body(body_of(bundle), now)
    if not bundle["records"] and version == 1:
        raise OwnResultsError("only a version-2 or version-3 daily bundle may be schedule-only (no records)")


def body_of(bundle: dict) -> dict:
    """The series entry a bundle contributes; daily entries always carry open_dates (v1: none)."""
    body = {k: bundle[k] for k in BODY_FIELDS}
    if bundle["series"]["kind"] == "daily":
        body["open_dates"] = list(bundle.get("open_dates", []))
    return body


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


# ---------------------------------------------------------------- Puter subset contract (bundle v3)
#
# Four fixed questions (a subset of the parent panel) on a requested route through Puter, an
# intermediary. Responses are graded per question; the returned-model identity is a separate
# dimension and stays "unknown" whenever Puter did not report a model, however the answer
# graded. These are results for the requested Puter route, not verified maker-model results.
# The series and subset fingerprints are recomputed here from public fields, so a changed
# question, prompt, grader, route, SDK or setting cannot pose as the same history.

PUTER_CONTRACT = "puter-subset-v1"
PUTER_BUNDLE_VERSION = 3
PUTER_SERVICE = "Puter"
# The reviewed routes of the private daily Puter configuration. Labels name the intermediary.
PUTER_ROUTES = {
    "puter-claude-sonnet-5-5": {"maker": "Anthropic", "exact_identifier": "claude-sonnet-5-5",
                                "requested_provider": "claude", "label": "Claude Sonnet 5.5 via Puter"},
    "puter-gpt-6.1-sol": {"maker": "OpenAI", "exact_identifier": "gpt-6.1-sol",
                          "requested_provider": "openai-completion", "label": "GPT-6.1 Sol via Puter"},
    # Three-route daily campaign (8 October 2026): Grok through Puter's xAI driver. The route id replaces the
    # requested model's "/" so that ids stay path- and URL-safe; the requested model itself is unchanged.
    "puter-x-ai-grok-4.7": {"maker": "xAI", "exact_identifier": "x-ai/grok-4.7",
                            "requested_provider": "xai", "label": "Grok 4.7 via Puter"},
}
PUTER_ROUTE_FIELDS = ("access_kind", "exact_identifier", "label", "maker", "requested_provider", "route_id",
                      "service_provider")
PUTER_SERIES_FIELDS = ("contract", "grader_version", "kind", "parent_panel_id", "parent_panel_items",
                       "parent_panel_sha256", "planned_items", "schedule", "series_fingerprint", "series_id",
                       "settings", "subset_categories", "subset_fingerprint", "subset_item_ids",
                       "subset_item_sha256", "subset_prompt_sha256", "synthetic")
PUTER_SETTINGS = ("max_tokens", "model", "provider", "reasoning_effort", "retries", "sdk_package", "sdk_version",
                  "stream")
PUTER_ORDER = "item-major, Claude then GPT"                       # the collector's request order, part of identity
# Route-specific settings beyond PUTER_SETTINGS, exactly as the collector's series identity holds them
# (scripts/puter_daily.py route_series_id). Only the Grok route has any: the provider-enforced 1000-token
# cap, the returned-model names accepted as the requested one, the exact metering prefix, and that no
# temperature is forwarded. Claude and GPT keep exactly PUTER_SETTINGS, so their identities never change.
PUTER_ROUTE_SETTINGS = {
    "puter-x-ai-grok-4.7": {"max_tokens": 1000, "accepted_models": ["grok-4.7", "x-ai/grok-4.7"],
                            "meter_prefix": "xai:grok-4_dot_7:", "temperature_forwarded": False},
}
# The position of a route's requests in the collector's order, part of its identity. Grok is only ever
# collected daily after Claude and GPT (the reviewed three-route configuration).
PUTER_ROUTE_ORDER = {"puter-x-ai-grok-4.7": "item-major, after Claude and GPT"}
PUTER_PLANNED = 4
PUTER_STATUSES = ("completed", "stopped", "incomplete", "gap")
NOT_GRADED_KEYS = ("error", "malformed", "missing_text", "refusal", "truncated", "uncertain")
IDENTITY_KEYS = ("mismatch", "reported_match", "unknown")
PUTER_COUNTS = ("attempted", "answered", "correct", "incorrect", "format_error", "not_graded", "not_sent", "identity")
PUTER_RECORD_FIELDS = {
    "record_version": int, "date": str, "status": str, "run_id": (str, type(None)), "evidence": str,
    "evidence_sha256": (str, type(None)), "route_id": str, "series_id": str, "planned_items": int,
    "attempted": (int, type(None)), "answered": (int, type(None)), "correct": (int, type(None)),
    "incorrect": (int, type(None)), "format_error": (int, type(None)), "not_graded": (dict, type(None)),
    "not_sent": (int, type(None)), "identity": (dict, type(None)), "interpretation": str,
}
PUTER_RUN_ID_RE = re.compile(r"^puter-daily-(\d{8})T(\d{6})Z-([0-9a-f]{10})$")
PUTER_INTERPRETATION = ("Counts from Baseline's own runs of 4 fixed questions on one requested route through Puter. "
                        "Returned-model identity is counted separately; these are results for the requested Puter "
                        "route, not verified maker model performance. Not a quality score, and not a decline, "
                        "improvement or stability verdict.")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


def is_puter(body) -> bool:
    return isinstance(body, dict) and isinstance(body.get("series"), dict) and "contract" in body["series"]


def _canonical_sha(value) -> str:
    return sha256_bytes(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def puter_route_id(model) -> str:
    """The public route id of a requested Puter model (the collector's series-id prefix)."""
    return f"puter-{str(model).replace('/', '-')}"


def puter_series_fingerprint(series: dict) -> str:
    """The private collector's series identity, recomputed from public fields (same canonical JSON).

    Claude and GPT hash exactly their original fields; a route with its own settings (Grok) adds them and its
    request position, as the collector does, so no route can pose as another's history."""
    s = series["settings"]
    identity = {"panel_sha256": series["parent_panel_sha256"], "item_ids": series["subset_item_ids"],
                "prompt_sha256": series["subset_prompt_sha256"], "grader_version": series["grader_version"],
                "model": s["model"], "provider": s["provider"], "reasoning_effort": s["reasoning_effort"],
                "max_tokens": s["max_tokens"], "stream": s["stream"], "sdk_version": s["sdk_version"],
                "order": PUTER_ORDER}
    route_id = puter_route_id(s["model"])
    if route_id in PUTER_ROUTE_SETTINGS:
        identity.update({k: s.get(k) for k in PUTER_ROUTE_SETTINGS[route_id] if k != "max_tokens"},
                        order=PUTER_ROUTE_ORDER[route_id])
    return _canonical_sha(identity)


def puter_subset_fingerprint(series: dict) -> str:
    """Binds the ordered item ids to each item's content hash and prompt hash, within the parent panel."""
    return _canonical_sha({"parent_panel_sha256": series["parent_panel_sha256"], "item_ids": series["subset_item_ids"],
                           "item_sha256": series["subset_item_sha256"], "prompt_sha256": series["subset_prompt_sha256"]})


def puter_run_started(run_id) -> datetime:
    """The UTC start time encoded in a Puter daily run id; raises if it is not one."""
    match = PUTER_RUN_ID_RE.match(run_id) if isinstance(run_id, str) else None
    if not match:
        raise OwnResultsError("a Puter run record needs a Puter daily run id")
    try:
        return datetime.strptime(match.group(1) + match.group(2), "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        raise OwnResultsError("run id holds an impossible start time") from None


def check_puter_route(route) -> None:
    _exact(route, PUTER_ROUTE_FIELDS, "Puter route")
    reviewed = PUTER_ROUTES.get(route.get("route_id"))
    if reviewed is None or {k: route[k] for k in reviewed} != reviewed or route["access_kind"] != "intermediary" \
            or route["service_provider"] != PUTER_SERVICE:
        raise OwnResultsError("a Puter route must be one of the reviewed intermediary routes, exactly")


def check_puter_settings(settings, route: dict) -> None:
    extra = PUTER_ROUTE_SETTINGS.get(route["route_id"])
    _exact(settings, tuple(sorted(set(PUTER_SETTINGS) | set(extra or ()))), "Puter settings")
    if extra is None:
        cap_ok = type(settings["max_tokens"]) is int and 1 <= settings["max_tokens"] <= 128
    else:                                         # every route-specific value exactly, types included
        cap_ok = all(type(settings[k]) is type(v) and settings[k] == v for k, v in extra.items()) \
            and settings["reasoning_effort"] is None
    if settings["sdk_package"] != "@heyputer/puter.js" or not isinstance(settings["sdk_version"], str) \
            or not SEMVER_RE.match(settings["sdk_version"]) or settings["model"] != route["exact_identifier"] \
            or settings["provider"] != route["requested_provider"] or not cap_ok \
            or settings["stream"] is not False or settings["retries"] != 0 \
            or type(settings["retries"]) is not int or settings["reasoning_effort"] not in (None, "low", "medium", "high"):
        raise OwnResultsError("Puter settings must be the pinned SDK, the route's model and provider, its reviewed "
                              "token cap (1-128, or the route's own reviewed settings exactly), no streaming, no "
                              "retries and a known reasoning setting")


def check_puter_series(series, route: dict) -> None:
    _exact(series, PUTER_SERIES_FIELDS, "Puter series")
    if series["contract"] != PUTER_CONTRACT or series["kind"] != "daily" or not isinstance(series["synthetic"], bool):
        raise OwnResultsError("a Puter series is a daily series of the puter-subset-v1 contract")
    if not isinstance(series["parent_panel_id"], str) or not ID_RE.match(series["parent_panel_id"]) \
            or not _sha(series["parent_panel_sha256"]) or not _count(series["parent_panel_items"], PUTER_PLANNED) \
            or not isinstance(series["grader_version"], str) or not GRADER_RE.match(series["grader_version"]):
        raise OwnResultsError("Puter series parent panel or grader description is invalid")
    if type(series["planned_items"]) is not int or series["planned_items"] != PUTER_PLANNED:
        raise OwnResultsError(f"a Puter series plans exactly {PUTER_PLANNED} questions")
    if series["parent_panel_items"] <= series["planned_items"]:
        raise OwnResultsError("the subset must be strictly smaller than its parent panel (never the panel shown as four)")
    ids, items, prompts, cats = (series[k] for k in ("subset_item_ids", "subset_item_sha256", "subset_prompt_sha256",
                                                     "subset_categories"))
    if not all(isinstance(x, list) and len(x) == PUTER_PLANNED for x in (ids, items, prompts, cats)) \
            or len(set(map(str, ids))) != PUTER_PLANNED or not all(isinstance(i, str) and ID_RE.match(i) for i in ids) \
            or not all(_sha(h) for h in items + prompts) \
            or not all(isinstance(c, str) and CATEGORY_RE.match(c) for c in cats):
        raise OwnResultsError("the subset must list 4 distinct item ids with their item and prompt hashes and categories")
    check_puter_settings(series["settings"], route)
    if series["subset_fingerprint"] != puter_subset_fingerprint(series):
        raise OwnResultsError("subset_fingerprint does not match the listed items and prompts")
    if series["series_fingerprint"] != puter_series_fingerprint(series):
        raise OwnResultsError("series_fingerprint does not match the subset, grader, route and settings")
    if series["series_id"] != f"{route['route_id']}--daily--{series['series_fingerprint'][:12]}":
        raise OwnResultsError("Puter series id must be route--daily--fingerprint prefix")
    check_schedule(series["schedule"])


def validate_puter_record(record, route: dict, series: dict) -> None:
    _exact(record, PUTER_RECORD_FIELDS, "a Puter record")
    for key, kind in PUTER_RECORD_FIELDS.items():
        allowed = kind if isinstance(kind, tuple) else (kind,)
        if not isinstance(record[key], allowed) or isinstance(record[key], bool):
            raise OwnResultsError(f"{key} has the wrong type")              # booleans are never counts
    if record["record_version"] != 1 or record["status"] not in PUTER_STATUSES or record["evidence"] not in EVIDENCE \
            or record["interpretation"] != PUTER_INTERPRETATION:
        raise OwnResultsError("unknown Puter record version, status, evidence or interpretation")
    if record["route_id"] != route["route_id"] or record["series_id"] != series["series_id"] \
            or record["planned_items"] != series["planned_items"]:
        raise OwnResultsError(f"Puter record for {record['date']} is bound to another route, series or plan")
    _day(record["date"])
    counts_present = [record[k] is not None for k in PUTER_COUNTS]
    if record["status"] == "gap":
        if record["evidence"] != "none" or record["run_id"] is not None or record["evidence_sha256"] is not None \
                or any(counts_present):
            raise OwnResultsError("a gap carries no run, evidence or counts")
        return
    started = puter_run_started(record["run_id"])
    if started.date().isoformat() != record["date"]:
        raise OwnResultsError("run id must be a run started on the record's date")
    if record["evidence_sha256"] is not None and not _sha(record["evidence_sha256"]):
        raise OwnResultsError("evidence_sha256 must be a sha256")
    if record["evidence"] == "none":
        raise OwnResultsError("a run record needs verified or unavailable evidence")
    if record["evidence"] == "unavailable":
        if any(counts_present):
            raise OwnResultsError("counts without verified evidence are not published")
        return
    if record["status"] not in ("completed", "stopped") or record["evidence_sha256"] is None or not all(counts_present):
        raise OwnResultsError("verified evidence needs a closed run, its evidence hash and every count")
    planned = record["planned_items"]
    ng, ident = record["not_graded"], record["identity"]
    if set(ng) != set(NOT_GRADED_KEYS) or set(ident) != set(IDENTITY_KEYS):
        raise OwnResultsError("not_graded and identity must hold exactly their count keys")
    scalars = [record[k] for k in ("attempted", "answered", "correct", "incorrect", "format_error", "not_sent")]
    if not all(_count(v, 0, planned) for v in scalars + list(ng.values()) + list(ident.values())):
        raise OwnResultsError("every Puter count is a whole number within the planned questions")
    if record["attempted"] + record["not_sent"] != planned \
            or record["correct"] + record["incorrect"] + record["format_error"] != record["answered"] \
            or record["answered"] + sum(ng.values()) != record["attempted"] \
            or sum(ident.values()) != record["attempted"]:
        raise OwnResultsError("Puter counts must add up: attempted + not sent = planned; graded = answered; "
                              "answered + not graded = attempted; identity counts = attempted")
    if SECRETISH.search(json.dumps(record)) or FIXTURE_MARK in json.dumps(record):
        raise OwnResultsError("record contains something that looks like a credential or a fixture label")


def check_puter_body(body: dict, now: datetime | None = None) -> None:
    as_of = parse_stamp(body["as_of"])
    if now is not None and as_of > now + timedelta(minutes=5):
        raise OwnResultsError("as_of is in the future")
    route, series, records = body["route"], body["series"], body["records"]
    check_puter_route(route)
    check_puter_series(series, route)
    if not isinstance(records, list) or len(records) > MAX_RECORDS:
        raise OwnResultsError(f"records must be a list of at most {MAX_RECORDS}")
    keys, dates, schedule = set(), set(), series["schedule"]
    for record in records:
        validate_puter_record(record, route, series)
        key = _record_key(record)
        if record["date"] > as_of.date().isoformat() or not schedule["start_date"] <= record["date"] <= schedule["end_date"]:
            raise OwnResultsError(f"record {key} is later than as_of or outside the scheduled campaign")
        if record["run_id"] is not None and puter_run_started(record["run_id"]) > as_of:
            raise OwnResultsError(f"record {key} started after as_of; a snapshot cannot report a later run")
        if record["date"] in dates or key in keys:
            raise OwnResultsError(f"two records for {record['date']} in one daily series")
        dates.add(record["date"])
        keys.add(key)
    if "open_dates" in body:
        _check_open_dates(body, as_of, dates)


def puter_eligible(record: dict) -> bool:
    """A graph point: verified, every planned question attempted and gradeable, and no identity mismatch.

    A run stopped after this route's four questions is still a complete four-question run;
    a partial or ungradeable run never gets a smaller denominator or a point."""
    return record["evidence"] == "verified" and record["status"] in ("completed", "stopped") \
        and record["attempted"] == record["planned_items"] and record["answered"] == record["planned_items"] \
        and record["identity"]["mismatch"] == 0


def puter_preview_entries(existing=()) -> list:
    """Catalogue entries for the reviewed Puter routes, used only by preview builds (never written to catalog/).

    Routes the catalogue already lists (catalog/models.json holds the three reviewed Puter entries since
    8 October 2026) are skipped, so a route never maps to two entries; a test catalogue without them still
    gets the preview-only stand-ins."""
    present = {e.get("id") for e in existing}
    # Ids come from the safe route id (Grok's requested model holds a "/"); the two original ids are unchanged.
    return [{"id": "puter." + route_id[len("puter-"):], "name": r["label"], "maker": r["maker"],
             "family": r["label"].split(" via ")[0].rsplit(" ", 1)[0], "identity_kind": "exact",
             "exact_identifier": r["exact_identifier"], "service_provider": PUTER_SERVICE, "access_kind": "intermediary",
             "availability": "unknown", "route_ids": [], "sources": [],
             "notes": "Preview-only entry: the requested route through Puter. Not part of the published catalogue."}
            for route_id, r in PUTER_ROUTES.items() if "puter." + route_id[len("puter-"):] not in present]


# ---------------------------------------------------------------- publication policy (T13)

def validate_policy(policy, require_enabled: bool = True) -> None:
    """A publication policy: exactly which daily series an automated publisher may admit, and where.

    The policy itself is reviewed by a person (its digest goes in policy_review.json); an
    automated publisher can only use an approved policy, never create or change one.
    A disabled template may leave the panel, grader and item count unresolved (null).
    """
    if not isinstance(policy, dict) or policy.get("format") != POLICY_FORMAT or policy.get("format_version") != 1:
        raise OwnResultsError(f"not a {POLICY_FORMAT} v1 policy")
    _exact(policy, POLICY_FIELDS, "policy")
    if not isinstance(policy["enabled"], bool):
        raise OwnResultsError("policy enabled must be true or false")
    if require_enabled and policy["enabled"] is not True:
        raise OwnResultsError("the publication policy is disabled")
    check_route(policy["route"])
    if policy["series_kind"] != "daily" or not _sha(policy["config_fingerprint"]):
        raise OwnResultsError("a policy covers one daily series, bound by its full configuration fingerprint")
    unresolved = [k for k in ("panel_sha256", "panel_items", "grader_version") if policy[k] is None]
    if unresolved and policy["enabled"]:
        raise OwnResultsError(f"an enabled policy must resolve {unresolved} from the reviewed configuration")
    if policy["panel_sha256"] is not None and not _sha(policy["panel_sha256"]):
        raise OwnResultsError("policy panel_sha256 must be a sha256")
    if policy["panel_items"] is not None and not _count(policy["panel_items"], 1):
        raise OwnResultsError("policy panel_items must be a count")
    if policy["grader_version"] is not None and not (isinstance(policy["grader_version"], str)
                                                     and GRADER_RE.match(policy["grader_version"])):
        raise OwnResultsError("policy grader_version is invalid")
    check_settings(policy["settings"])
    check_schedule(policy["campaign"])
    if not isinstance(policy["public_repository"], str) or not REPO_RE.match(policy["public_repository"]) \
            or not isinstance(policy["public_branch"], str) or not BRANCH_RE.match(policy["public_branch"]):
        raise OwnResultsError("policy needs the public repository (owner/name) and branch")
    if policy["allowed_paths"] != list(PUBLICATION_PATHS):
        raise OwnResultsError(f"policy allowed_paths must be exactly {list(PUBLICATION_PATHS)}")
    if SECRETISH.search(json.dumps(policy)):
        raise OwnResultsError("policy contains something that looks like a credential")


def policy_binding_problem(bundle: dict, policy: dict) -> str | None:
    """Why a bundle falls outside an approved policy, or None when it is exactly covered."""
    series = bundle["series"]
    expected = {"route": policy["route"], "kind": policy["series_kind"],
                "config_fingerprint": policy["config_fingerprint"], "panel_sha256": policy["panel_sha256"],
                "panel_items": policy["panel_items"], "grader_version": policy["grader_version"],
                "settings": policy["settings"], "schedule": policy["campaign"]}
    actual = dict({k: series[k] for k in expected if k != "route"}, route=bundle["route"])
    for key in sorted(expected):
        if actual[key] != expected[key]:
            return f"{key} differs from the approved policy"
    return None


def check_schedule(schedule) -> None:
    _exact(schedule, ("end_date", "start_date", "type", "window_minutes", "window_start_utc"), "schedule")
    start, end = _day(schedule["start_date"]), _day(schedule["end_date"])
    if schedule["type"] != "daily" or not start <= end or (end - start).days > 366 \
            or not isinstance(schedule["window_start_utc"], str) or not HHMM_RE.match(schedule["window_start_utc"]) \
            or not _count(schedule["window_minutes"], 1, 1440):
        raise OwnResultsError("a daily schedule needs real start/end dates (at most a year) and a UTC window")


# ---------------------------------------------------------------- dataset, review manifests and policies

def empty_dataset() -> dict:
    return {"format": DATA_FORMAT, "format_version": DATA_VERSION, "series": {}, "sources": []}


def empty_review() -> dict:
    return {"format": REVIEW_FORMAT, "format_version": FORMAT_VERSION, "admitted": []}


def empty_policy_review() -> dict:
    return {"format": POLICY_REVIEW_FORMAT, "format_version": 1, "approved": []}


def _check_sources(entries, what: str, shapes=(HUMAN_SOURCE,)) -> None:
    if not isinstance(entries, list) or len(entries) > MAX_ADMITTED:
        raise OwnResultsError(f"{what} must be a list")
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict) or tuple(sorted(entry)) not in shapes:
            raise OwnResultsError(f"an entry of {what} must have exactly one of the fields {list(shapes)}")
        parse_stamp(entry.get("reviewed_at") or entry.get("admitted_at"))
        if "policy_sha256" in entry and not _sha(entry["policy_sha256"]):
            raise OwnResultsError(f"{what} policy digest must be a sha256")
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


def validate_policy_review(review) -> None:
    if not isinstance(review, dict) or review.get("format") != POLICY_REVIEW_FORMAT or review.get("format_version") != 1:
        raise OwnResultsError(f"not a {POLICY_REVIEW_FORMAT} v1 manifest")
    _exact(review, ("approved", "format", "format_version"), "policy review manifest")
    _check_sources(review["approved"], "approved policy list")


def validate_dataset(dataset, now: datetime | None = None, version: int = DATA_VERSION) -> None:
    if not isinstance(dataset, dict) or dataset.get("format") != DATA_FORMAT or dataset.get("format_version") != version:
        raise OwnResultsError(f"not a {DATA_FORMAT} v{version} dataset (run `own_results.py migrate` for v1)")
    _exact(dataset, ("format", "format_version", "series", "sources"), "dataset")
    _check_sources(dataset["sources"], "dataset sources", (HUMAN_SOURCE, POLICY_SOURCE))
    if not isinstance(dataset["series"], dict):
        raise OwnResultsError("dataset series must be an object keyed by series id")
    if bool(dataset["series"]) != bool(dataset["sources"]):
        raise OwnResultsError("published series need admitted sources, and admitted sources need series")
    for sid, body in dataset["series"].items():
        check_body(body, now)
        if ("open_dates" in body) != (body["series"]["kind"] == "daily"):
            raise OwnResultsError(f"dataset series {sid}: a daily entry lists open_dates, a calibration entry does not")
        if body["series"]["series_id"] != sid or (not body["records"] and body["series"]["kind"] != "daily"):
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


def load_policies(data_path: Path) -> dict:
    """{policy sha256: (policy, approval entry)} for every person-approved policy kept beside the dataset.

    policy_review.json (person-maintained) lists approved policy digests; policies/ must
    hold exactly those policies, each still matching its digest. Both are optional: with
    neither there are no approved policies.
    """
    folder = Path(data_path).parent
    review_path, policy_dir = folder / "policy_review.json", folder / "policies"
    if review_path.exists():
        review = load_json_file(review_path, "policy review manifest")
        validate_policy_review(review)
    else:
        review = empty_policy_review()
    present = {p.name for p in policy_dir.iterdir()} if policy_dir.is_dir() else set()
    named = {f"{e['sha256']}.json" for e in review["approved"]}
    if present != named:
        raise OwnResultsError(f"policies/ must hold exactly the approved policies (unexpected "
                              f"{sorted(present - named)[:3]}, missing {sorted(named - present)[:3]})")
    out = {}
    for entry in review["approved"]:
        raw = (policy_dir / f"{entry['sha256']}.json").read_bytes()
        if sha256_bytes(raw) != entry["sha256"]:
            raise OwnResultsError(f"approved policy {entry['sha256'][:12]} was altered or substituted")
        policy = parse_json(raw, "approved policy")
        validate_policy(policy)
        out[entry["sha256"]] = (policy, entry)
    return out


def _admitted_copy(admitted_dir: Path, digest: str) -> bytes:
    try:
        raw = (Path(admitted_dir) / f"{digest}.json").read_bytes()
    except OSError:
        raise OwnResultsError(f"the admitted copy of {digest[:12]} is missing") from None
    if sha256_bytes(raw) != digest:
        raise OwnResultsError(f"the admitted copy of {digest[:12]} was altered or substituted")
    return raw


def check_source(source: dict, bundle: dict, review: dict, policies: dict) -> None:
    """A person reviewed this exact digest, or an approved policy covers this exact bundle."""
    digest = source["sha256"]
    if "reviewed_at" in source:
        if {e["sha256"]: e for e in review["admitted"]}.get(digest) != source:
            raise OwnResultsError(f"dataset source {digest[:12]} was not admitted by the review manifest")
        return
    if is_puter(bundle):
        raise OwnResultsError("automatic policy admission of Puter results is not supported; a person reviews them")
    approved = policies.get(source["policy_sha256"])
    if approved is None:
        raise OwnResultsError(f"dataset source {digest[:12]} names a policy that is not approved")
    policy, approval = approved
    problem = policy_binding_problem(bundle, policy)
    if problem:
        raise OwnResultsError(f"dataset source {digest[:12]} is outside its policy: {problem}")
    if not (approval["reviewed_at"] <= source["admitted_at"] and bundle["as_of"] <= source["admitted_at"]):
        raise OwnResultsError(f"dataset source {digest[:12]} was admitted before its policy approval or its own as_of")


def rebuild(sources: list, review: dict, admitted_dir: Path, now: datetime | None = None,
            policies: dict | None = None) -> dict:
    """The dataset as merged from the admitted candidate copies named by `sources`.

    Each source is either person-reviewed (its digest and time are in the review manifest)
    or policy-admitted (an approved policy covers the bundle exactly). Its kept copy must
    still have that digest and pass the bundle contract.
    """
    dataset = empty_dataset()
    for source in sorted(sources, key=lambda s: s["sha256"]):
        bundle = parse_json(_admitted_copy(admitted_dir, source["sha256"]), "admitted copy")
        validate_bundle(bundle, now)
        check_source(source, bundle, review, policies or {})
        dataset = merge(dataset, bundle, source)
    return dataset


def load_admitted(data_path: Path = DATA_PATH, review_path: Path = REVIEW_PATH, now: datetime | None = None) -> dict:
    """The dataset, only if it is exactly what its admitted candidates give.

    Binding published records to admitted content (T12 review R1): the kept candidate
    copies are re-merged and must reproduce data.json byte for byte, and the admitted
    folder holds exactly the copies the dataset names. An edited count, an added or
    removed record, changed route or settings, or a missing or substituted copy fails;
    so does a policy-admitted copy outside its approved policy (T13). This detects
    accidental or unreviewed edits; it is not a defence against a publisher who
    deliberately rewrites the review manifests and copies as well.
    """
    try:
        raw = Path(data_path).read_bytes()
    except OSError as exc:
        raise OwnResultsError(f"cannot read own-results dataset: {type(exc).__name__}") from None
    dataset = parse_json(raw, "own-results dataset")
    validate_dataset(dataset, now)
    review = load_review(review_path)
    policies = load_policies(data_path)
    folder = admitted_dir_for(data_path)
    present = {p.name for p in folder.iterdir()} if folder.is_dir() else set()
    named = {f"{s['sha256']}.json" for s in dataset["sources"]}
    if present != named:
        raise OwnResultsError(f"{folder.name}/ must hold exactly the admitted copies the dataset names "
                              f"(unexpected {sorted(present - named)[:3]}, missing {sorted(named - present)[:3]})")
    if dumps(rebuild(dataset["sources"], review, folder, now, policies)) != raw:
        raise OwnResultsError("the dataset does not match a rebuild from its admitted candidates; "
                              "re-import admitted candidates instead of editing data.json")
    _refuse_synthetic_in_production(dataset, data_path)
    return dataset


def _refuse_synthetic_in_production(dataset: dict, data_path: Path) -> None:
    """A synthetic preview series (Puter fixtures) can never be part of the production dataset."""
    if Path(data_path).resolve() == DATA_PATH.resolve() and any(
            is_puter(body) and body["series"]["synthetic"] is not False for body in dataset["series"].values()):
        raise OwnResultsError("the production dataset holds a synthetic preview series; synthetic results are "
                              "never published")


def fixture_digests(folder: Path = FIXTURE_DIR) -> set:
    """Digests of every synthetic fixture; these may never be admitted to production."""
    if not Path(folder).is_dir():
        return set()
    return {sha256_bytes(p.read_bytes()) for p in sorted(Path(folder).rglob("*")) if p.is_file()}


def migrate(data_path: Path = DATA_PATH, review_path: Path = REVIEW_PATH) -> str:
    """Dataset v1 (T12) to v2 (T13). Only the version number changes, and only if the admitted
    copies rebuild exactly the v1 content. Returns 'unchanged' or 'migrated'."""
    data_path = Path(data_path)
    old = parse_json(data_path.read_bytes(), "own-results dataset")
    if isinstance(old, dict) and old.get("format_version") == DATA_VERSION:
        load_admitted(data_path, review_path)
        return "unchanged"
    validate_dataset(old, version=1)
    new = dict(old, format_version=DATA_VERSION)
    review = load_review(review_path)
    folder = admitted_dir_for(data_path)
    present = {p.name for p in folder.iterdir()} if folder.is_dir() else set()
    if present != {f"{s['sha256']}.json" for s in old["sources"]}:
        raise OwnResultsError("admitted/ does not hold exactly the copies the v1 dataset names; not migrated")
    if dumps(rebuild(old["sources"], review, folder, None, load_policies(data_path))) != dumps(new):
        raise OwnResultsError("the v1 dataset does not match its admitted copies; not migrated")
    _atomic_write(data_path, dumps(new))
    return "migrated"


# ---------------------------------------------------------------- merging and importing

def merge(dataset: dict, bundle: dict, source: dict | None) -> dict:
    """A new dataset with `bundle` merged in. Identical records are no-ops; any conflict raises."""
    out = json.loads(json.dumps(dataset))
    body = body_of(bundle)
    sid = body["series"]["series_id"]
    current = out["series"].get(sid)
    if current is None:
        current = out["series"][sid] = {"as_of": body["as_of"], "route": body["route"], "series": body["series"],
                                         "records": []}
        if "open_dates" in body:
            current["open_dates"] = []
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
    if daily:
        # Open dates come from the newest check only (ties: union), and a date with a record is never open,
        # so the result does not depend on import order and a later closure resolves the date.
        if body["as_of"] > current["as_of"]:
            open_dates = set(body["open_dates"])
        elif body["as_of"] == current["as_of"]:
            open_dates = set(current["open_dates"]) | set(body["open_dates"])
        else:
            open_dates = set(current["open_dates"])
        current["open_dates"] = sorted(open_dates - {r["date"] for r in current["records"]})
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


def _admit(raw: bytes, source: dict, review_path: Path, output_path: Path, now: datetime) -> str:
    """Shared admission: validate everything, keep the exact bytes, then write the dataset."""
    digest = sha256_bytes(raw)
    bundle = parse_json(raw, "candidate")
    validate_bundle(bundle, now)
    review = load_review(review_path)
    output_path = Path(output_path)
    policies = load_policies(output_path)
    check_source(source, bundle, review, policies)
    folder = admitted_dir_for(output_path)
    if output_path.exists():
        existing_raw = output_path.read_bytes()
        dataset = load_admitted(output_path, review_path, now)
    else:
        if folder.is_dir() and any(folder.iterdir()):
            raise OwnResultsError(f"{folder.name}/ holds copies but there is no dataset; review it before importing")
        existing_raw, dataset = None, empty_dataset()
    if digest in {s["sha256"] for s in dataset["sources"]}:
        return "unchanged"                                   # this exact candidate is already published
    merged = merge(dataset, bundle, source)
    validate_dataset(merged, now)
    _refuse_synthetic_in_production(merged, output_path)
    new_raw = dumps(merged)
    copy = folder / f"{digest}.json"
    if copy.exists() and copy.read_bytes() != raw:
        raise OwnResultsError(f"{copy.name} exists with different bytes; review the admitted folder")
    wrote_copy = not copy.exists()
    if wrote_copy:
        _atomic_write(copy, raw)
    try:
        if dumps(rebuild(merged["sources"], review, folder, now, policies)) != new_raw:   # the copies reproduce it
            raise OwnResultsError("internal error: the admitted copies do not reproduce the merged dataset")
    except OwnResultsError:
        if wrote_copy:
            copy.unlink()
        raise
    if new_raw == existing_raw:
        return "unchanged"
    _atomic_write(output_path, new_raw)
    return "updated"


def import_bundle(input_path: Path, review_path: Path = REVIEW_PATH, output_path: Path = DATA_PATH,
                  now: datetime | None = None) -> str:
    """Admit one person-reviewed bundle into the dataset. Returns 'unchanged' or 'updated'.

    Order: the file's digest must be in the review manifest; the bundle, the manifest and
    the existing dataset (rebuilt from its admitted copies) must validate; the merge must
    be conflict-free. Then the exact candidate bytes are kept in admitted/<sha256>.json and
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
    return _admit(raw, dict(entry), review_path, output_path, now)


def admit_by_policy(raw: bytes, policy_sha256: str, admitted_at: str, review_path: Path = REVIEW_PATH,
                    output_path: Path = DATA_PATH, now: datetime | None = None) -> str:
    """Admit one candidate under an approved publication policy (automated, not person-reviewed).

    The policy must already be approved in policy_review.json and kept in policies/; this
    never creates or changes either. The bundle must match the policy exactly.
    """
    now = now or datetime.now(timezone.utc)
    if parse_stamp(admitted_at) > now + timedelta(minutes=5):
        raise OwnResultsError("admitted_at is in the future")
    if sha256_bytes(raw) in fixture_digests() and Path(review_path).resolve() == REVIEW_PATH.resolve():
        raise OwnResultsError("a synthetic test fixture cannot be admitted to the production dataset")
    source = {"admitted_at": admitted_at, "policy_sha256": policy_sha256, "sha256": sha256_bytes(raw)}
    return _admit(raw, source, review_path, output_path, now)


# ---------------------------------------------------------------- site summary

def window_bounds(schedule: dict, day: date) -> tuple[datetime, datetime]:
    hour, minute = map(int, schedule["window_start_utc"].split(":"))
    opens = datetime(day.year, day.month, day.day, hour, minute, tzinfo=timezone.utc)
    return opens, opens + timedelta(minutes=schedule["window_minutes"])


def campaign_days(schedule: dict) -> list:
    start, end = _day(schedule["start_date"]), _day(schedule["end_date"])
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def expected_dates(schedule: dict, as_of: datetime) -> tuple[list, int]:
    """(campaign dates whose window had closed by as_of, count of campaign dates not yet due)."""
    due = [d.isoformat() for d in campaign_days(schedule) if window_bounds(schedule, d)[1] <= as_of]
    return due, len(campaign_days(schedule)) - len(due)


def _usable(record: dict) -> bool:
    """A graphable daily score: verified, completed, and every scheduled question attempted.

    T12's 90% `valid_day` threshold is not enough: a partial run is shown, but separately.
    """
    return record["evidence"] == "verified" and record["status"] == "completed" \
        and record["attempted_items"] == record["scheduled_items"]


def daily_rows(body: dict) -> dict:
    """Every campaign date up to as_of: a run, an explicit gap, or 'no_record' (never filled in).

    Dates after as_of are pending (not yet due, or not yet checked); they are listed, not scored.
    An open date (run started, not closed when checked) is the row state "open": unresolved,
    no score, and never a missed day (T13 review R2).
    """
    as_of = parse_stamp(body["as_of"])
    due, later = expected_dates(body["series"]["schedule"], as_of)
    by_date = {r["date"]: r for r in body["records"]}
    open_dates = set(body.get("open_dates", []))
    rows = [{"date": d, "state": by_date[d]["status"] if d in by_date else "open" if d in open_dates else "no_record",
             "record": by_date.get(d)} for d in due]
    for record in body["records"]:                       # a run published although its window closed after as_of
        if record["date"] not in due:
            rows.append({"date": record["date"], "state": record["status"], "record": record})
    rows.sort(key=lambda r: r["date"])
    for row in rows:
        row["eligible"] = row["record"] is not None and (
            puter_eligible(row["record"]) if is_puter(body) else _usable(row["record"]))
    shown = {r["date"] for r in rows}
    pending = [d.isoformat() for d in campaign_days(body["series"]["schedule"]) if d.isoformat() not in shown]
    return {"rows": rows, "not_yet_due": len(pending), "pending_dates": pending}


def map_entry(route: dict, catalog_entries: list) -> str:
    """The one catalogue entry with the same maker, exact identifier, access kind and service provider
    (the maker itself for its own API, the named host otherwise)."""
    service = route.get("service_provider", route["maker"])
    hits = [e["id"] for e in catalog_entries if e.get("identity_kind") == "exact" and e.get("maker") == route["maker"]
            and e.get("exact_identifier") == route["exact_identifier"] and e.get("access_kind") == route["access_kind"]
            and e.get("service_provider") == service]
    if len(hits) != 1:
        raise OwnResultsError(f"route {route['route_id']} matches {len(hits)} catalogue entries (expected exactly one "
                              "exact entry with the same maker, identifier and access)")
    return hits[0]


def daily_view(sid: str, body: dict) -> dict:
    """One daily series as the page draws it. Counts are never combined across series."""
    series = body["series"]
    rows = daily_rows(body)
    return {"series_id": sid, "as_of": body["as_of"], "schedule": series["schedule"], "rows": rows["rows"],
            "not_yet_due": rows["not_yet_due"], "pending_dates": rows["pending_dates"],
            "open_dates": list(body.get("open_dates", [])),
            "panel_items": series["panel_items"], "panel_id": series["panel_id"], "settings": series["settings"],
            "grader_version": series["grader_version"], "config_fingerprint": series["config_fingerprint"]}


def puter_view(sid: str, body: dict) -> dict:
    """One Puter series as the page draws it: 0-4 scale, requested route, sample size and identity, never merged."""
    series, route = body["series"], body["route"]
    rows = daily_rows(body)
    return {"contract": PUTER_CONTRACT, "series_id": sid, "as_of": body["as_of"], "schedule": series["schedule"],
            "rows": rows["rows"], "not_yet_due": rows["not_yet_due"], "pending_dates": rows["pending_dates"],
            "open_dates": list(body.get("open_dates", [])), "panel_items": series["planned_items"],
            "planned_items": series["planned_items"], "parent_panel_id": series["parent_panel_id"],
            "parent_panel_items": series["parent_panel_items"], "subset_item_ids": series["subset_item_ids"],
            "subset_categories": series["subset_categories"], "grader_version": series["grader_version"],
            "settings": series["settings"], "series_fingerprint": series["series_fingerprint"],
            "subset_fingerprint": series["subset_fingerprint"], "synthetic": series["synthetic"],
            "route": {k: route[k] for k in ("label", "maker", "exact_identifier", "requested_provider",
                                            "service_provider")}}


def site_tests(dataset: dict, catalog_entries: list) -> dict:
    """The page's baseline_tests record. Calibration and daily evidence stay separate.

    Each entry's `daily_series` lists its daily series, newest schedule first; a changed
    setup is a separate series and is never joined to another. `daily` is the first of
    them (kept for older consumers), and the status counts come from it alone.
    """
    entries, methods = {}, []
    for sid in sorted(dataset["series"]):
        body = dataset["series"][sid]
        entry_id = map_entry(body["route"], catalog_entries)
        rec = entries.setdefault(entry_id, {"route_id": body["route"]["route_id"], "runs": 0, "latest_run": None,
                                            "latest_attempt": None, "baseline_complete": False, "daily": None,
                                            "daily_series": [], "calibration": []})
        if rec["route_id"] != body["route"]["route_id"]:
            raise OwnResultsError(f"catalogue entry {entry_id} would mix two routes")
        series = body["series"]
        if is_puter(body):                       # its own method text; never mixed into the 40-question methods
            rec["daily_series"].append(puter_view(sid, body))
            continue
        method = {k: series[k] for k in ("panel_id", "panel_items", "panel_categories", "grader_version", "settings")}
        if method not in methods:
            methods.append(method)
        if series["kind"] == "calibration":
            rec["calibration"] = sorted(rec["calibration"] + body["records"], key=lambda r: (r["date"], r["run_id"]))
            continue
        rec["daily_series"].append(daily_view(sid, body))
    for rec in entries.values():
        rec["daily_series"].sort(key=lambda s: (s["schedule"]["start_date"], s["schedule"]["end_date"], s["series_id"]),
                                 reverse=True)
        if not rec["daily_series"]:
            continue
        latest = rec["daily"] = rec["daily_series"][0]
        usable = [r["record"] for r in latest["rows"] if r["eligible"]]
        rec["runs"] = len(usable)
        rec["latest_run"] = usable[-1]["date"] if usable else None
        if latest["rows"]:
            rec["latest_attempt"] = "ok" if latest["rows"][-1]["eligible"] else "failed"
    return {"runs": sum(r["runs"] for r in entries.values()),
            "calibration_runs": sum(len(r["calibration"]) for r in entries.values()),
            "entries": entries, "methods": methods}


EMPTY_TESTS = {"runs": 0, "calibration_runs": 0, "entries": {}, "methods": []}


# ---------------------------------------------------------------- command line

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command", choices=("check", "inspect", "import", "migrate", "check-policy"))
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
        if args.command == "migrate":
            print(migrate(Path(args.data), Path(args.review)))
            return 0
        if not args.candidate:
            parser.error("a candidate file is required")
        raw = Path(args.candidate).read_bytes()
        if args.command == "check-policy":
            policy = parse_json(raw, "policy")
            validate_policy(policy, require_enabled=False)
            print(f"{'enabled' if policy['enabled'] else 'DISABLED'} policy sha256 {sha256_bytes(raw)}")
            return 0
        if args.command == "inspect":
            bundle = parse_json(raw, "candidate")
            validate_bundle(bundle, datetime.now(timezone.utc))
            print(f"valid candidate sha256 {sha256_bytes(raw)}")
            print(f"series {bundle['series']['series_id']} ({bundle['series']['kind']}), as of {bundle['as_of']}")
            if not bundle["records"]:
                print("  schedule only: no closed runs yet")
            if is_puter(bundle):
                print(f"  {bundle['route']['label']}; small sample: {PUTER_PLANNED} questions"
                      + ("; SYNTHETIC PREVIEW, never publishable" if bundle["series"]["synthetic"] else ""))
            for r in sorted(bundle["records"], key=lambda r: (r["date"], _record_key(r))):
                if is_puter(bundle):
                    score = (f"{r['correct']} of {r['planned_items']} correct, {r['attempted']} attempted, identity "
                             f"{'confirmed' if r['identity']['reported_match'] == r['attempted'] else 'not confirmed'}"
                             if r["evidence"] == "verified" else "no counts")
                else:
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
