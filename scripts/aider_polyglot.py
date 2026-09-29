"""Adapter: Aider polyglot leaderboard (Aider-AI/aider, Apache-2.0). Stdlib only.

Maps rows of aider/website/_data/polyglot_leaderboard.yml to registry records.
Each row is one run by the Aider project. Rows with identical route and harness
configuration share a series; any change (aider version/commit, edit format,
settings) starts a new series, so differently configured runs are never joined.
Only rows whose requested model is in SELECTED_MODELS are ingested (runbook: start
with at most three model-and-route entries), and only simple command forms are
accepted so no unrecorded setting (for example an API base override) is missed.
"""
from __future__ import annotations

import hashlib
import json
import re

SOURCE_ID = "aider-polyglot"
REPO = "Aider-AI/aider"
DATA_PATH = "aider/website/_data/polyglot_leaderboard.yml"
LICENSE_PATH = "LICENSE.txt"
LICENSE_NAME = "Apache License 2.0"
# Licence texts covered by the reviewed reuse decision (docs/SOURCES.md, docs/T02_REVIEW.md):
# unmodified Apache-2.0 at commit 5dc9490b. Any other licence bytes need a new review.
REVIEWED_LICENSE_SHA256 = frozenset({"cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30"})

SELECTED_MODELS = ("deepseek/deepseek-chat", "deepseek/deepseek-reasoner")
# LiteLLM provider prefix -> (provider, access_type, service). Only prefixes whose
# endpoint is fixed by the prefix are mapped; anything else is skipped, not guessed.
PROVIDER_PREFIXES = {
    "deepseek": ("DeepSeek", "direct_api",
                 "DeepSeek API, selected by the LiteLLM provider prefix 'deepseek/' in the source's aider command"),
}
REQUIRED_KEYS = ("dirname", "test_cases", "total_tests", "model", "edit_format", "commit_hash",
                 "pass_num_2", "pass_rate_2", "command", "date", "versions")
DETAIL_KEYS = ("model", "dirname", "date", "command", "versions", "commit_hash", "edit_format",
               "pass_rate_1", "pass_num_1", "pass_rate_2", "pass_num_2", "percent_cases_well_formed",
               "error_outputs", "num_malformed_responses", "num_with_malformed_responses",
               "user_asks", "lazy_comments", "syntax_errors", "indentation_errors",
               "exhausted_context_windows", "test_timeouts", "total_tests", "test_cases",
               "reasoning_effort", "thinking_tokens", "seconds_per_case", "total_cost")
COMMAND_RE = re.compile(r"^aider --model (\S+)(?: --reasoning-effort (\S+))?(?: --thinking-tokens (\S+))?$")
KEY_RE = re.compile(r"^([a-z_0-9]+): ?(.*)$")
INT_RE = re.compile(r"^\d+$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ParseError(ValueError):
    pass


def _scalar(raw: str, number: int) -> tuple[str, str | None]:
    """Return (value, trailing comment). Comments are kept: sources use them for notes."""
    raw = raw.strip()
    if raw.startswith('"'):
        if len(raw) < 2 or not raw.endswith('"') or '"' in raw[1:-1] or "\\" in raw:
            raise ParseError(f"line {number}: unsupported quoted value")
        return raw[1:-1], None
    value, marker, comment = raw.partition(" #")
    value = value.strip()
    if not value or value.startswith(("'", "[", "{", "|", ">", "&", "*", "!", "#")):
        raise ParseError(f"line {number}: unsupported YAML value syntax")
    return value, (comment.strip() or None) if marker else None


def parse_rows(text: str) -> list:
    """Parse a flat YAML list of string-scalar mappings; fail on anything else."""
    rows, current = [], None
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith("- "):
            current = {"_line": number}
            rows.append(current)
            body = line[2:]
        elif line.startswith("  ") and current is not None and not line.startswith("   "):
            body = line[2:]
        else:
            raise ParseError(f"line {number}: unsupported YAML structure")
        match = KEY_RE.match(body)
        if not match:
            raise ParseError(f"line {number}: expected 'key: value'")
        key, raw = match.groups()
        if raw.strip() == "":
            raise ParseError(f"line {number}: nested or empty value for {key!r}")
        if key in current:
            raise ParseError(f"line {number}: repeated key {key!r}")
        current[key], comment = _scalar(raw, number)
        if comment:
            current[f"comment:{key}"] = comment
    if not rows:
        raise ParseError("no rows found")
    return rows


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9._-]+", "-", text.lower()).strip("-.")[:100]


def _row_problem(row: dict) -> str | None:
    missing = [key for key in REQUIRED_KEYS if key not in row]
    if missing:
        return f"missing required keys {missing}"
    for key in ("test_cases", "total_tests", "pass_num_2"):
        if not INT_RE.match(row[key]):
            return f"{key} is not a non-negative integer"
    passed, cases, total = int(row["pass_num_2"]), int(row["test_cases"]), int(row["total_tests"])
    if not (0 < cases <= total and passed <= cases):
        return "counts are inconsistent (need pass_num_2 <= test_cases <= total_tests, test_cases > 0)"
    try:
        stated = float(row["pass_rate_2"])
    except ValueError:
        return "pass_rate_2 is not a number"
    if round(100 * passed / cases, 1) != stated:
        return f"pass_rate_2 {stated} does not equal pass_num_2/test_cases ({passed}/{cases})"
    if not DATE_RE.match(row["date"]):
        return "date is not YYYY-MM-DD"
    return None


def build_records(rows: list, snapshot: dict, selected=SELECTED_MODELS) -> tuple[dict, list, dict]:
    """Return (candidate records by kind, problems, counts). Never raises on row content."""
    revision = snapshot["revision"]
    file_url = f"https://github.com/{REPO}/blob/{revision}/{DATA_PATH}"
    out = {"models": [], "routes": [], "series": [], "observations": []}
    problems, counts = [], {"rows": len(rows), "selected": 0, "not_selected": 0, "skipped": 0}
    seen = set()
    for row in rows:
        where = {"line": row["_line"], "dirname": row.get("dirname")}
        match = COMMAND_RE.match(row.get("command", ""))
        requested = match.group(1) if match else None
        if requested not in selected:
            if match is None and any(m in row.get("command", "") for m in selected):
                problems.append({"type": "skipped_row", **where, "reason": "unsupported command form"})
                counts["skipped"] += 1
            else:
                counts["not_selected"] += 1
            continue
        reason = _row_problem(row)
        settings = {key: row[key] for key in ("reasoning_effort", "thinking_tokens") if key in row}
        for key, flag in (("reasoning_effort", match.group(2)), ("thinking_tokens", match.group(3))):
            if flag and settings.setdefault(key, flag) != flag:
                reason = reason or f"{key} field disagrees with the command flag"
        prefix, _, model_name = requested.partition("/")
        if reason is None and prefix not in PROVIDER_PREFIXES:
            reason = f"provider prefix {prefix!r} has no reviewed route mapping"
        if reason is None and row["dirname"] in seen:
            reason = "duplicate dirname within this snapshot"
        if reason:
            problems.append({"type": "skipped_row", **where, "reason": reason})
            counts["skipped"] += 1
            continue
        seen.add(row["dirname"])
        counts["selected"] += 1
        provider, access_type, service = PROVIDER_PREFIXES[prefix]
        row_url = f"{file_url}#L{row['_line']}"
        model_id = _slug(f"{prefix}.{model_name}")
        route_id = _slug(f"{prefix}-api.{model_name}")
        if settings:
            digest = hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest()[:8]
            route_id = f"{route_id}.s{digest}"
        series = {
            "route_id": route_id, "source_id": SOURCE_ID,
            "suite": "Aider polyglot benchmark (Exercism exercises in six languages)",
            "suite_version": f"total_tests={row['total_tests']}",
            "grader": "exercise unit tests run by the aider benchmark harness; pass_rate_2 counts exercises passed by the second try",
            "prompt_set": f"aider edit_format={row['edit_format']}",
            "harness": f"aider {row['versions']} (commit {row['commit_hash']})",
            "sampling": {},
        }
        # Same configuration -> same series id, so repeated runs join one series and a
        # changed harness/route/format starts a new one.
        config_digest = hashlib.sha256(json.dumps(series, sort_keys=True).encode()).hexdigest()[:12]
        series_id = f"{SOURCE_ID}.{route_id}.c{config_digest}"
        out["models"].append({
            "id": model_id, "provider": provider, "public_name": model_name,
            "exact_identifier": model_name,
            "identifier_source_url": f"https://github.com/{REPO}/blob/{revision}/{DATA_PATH}",
            "release_date": None, "release_source_url": None, "availability": "unknown",
            "notes": "API model name as requested in the source's aider command. It may be an alias: "
                     "the source labels runs of this name as different underlying models over time "
                     "(see observation source_details.model).",
        })
        out["routes"].append({
            "id": route_id, "model_id": model_id, "access_type": access_type, "service": service,
            "requested_model": requested, "tier": None, "region": None, "settings": settings,
            "notes": "Route inferred from the provider prefix recorded by the source; tier/region not stated.",
        })
        out["series"].append({
            "id": series_id, **series,
            "scope": "leaderboard runs published by the Aider project with this exact configuration",
            "baseline_definition": "none: third-party runs, not a baseline",
            "notes": "Sampling settings are not stated in the source row.",
        })
        out["observations"].append({
            "id": _slug(f"{SOURCE_ID}.{row['dirname']}.pass-rate-2"), "series_id": series_id,
            "observed_at": row["date"], "retrieved_at": snapshot["retrieved_at"],
            "metric": {"name": "pass_rate_2", "numerator": int(row["pass_num_2"]),
                       "denominator": int(row["test_cases"])},
            "exclusions": {"missing": int(row["total_tests"]) - int(row["test_cases"])},
            "evidence_url": row_url, "source_revision": revision,
            "source_details": {key: row[key] for key in DETAIL_KEYS if key in row} |
                              {key: value for key, value in row.items() if key.startswith("comment:")},
            "notes": "observed_at is the source's date field (day precision, timezone not stated). "
                     "source_details values are verbatim strings from the source row.",
        })
    return out, problems, counts
