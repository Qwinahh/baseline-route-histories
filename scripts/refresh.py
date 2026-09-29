"""Source refresh for manual or scheduled runs (T05 release candidate). Stdlib only.

    py -3.11 -B scripts/refresh.py [--ref main] [--github-output PATH]

Runs each registered source adapter once through scripts/ingest.py (which already
refuses sources without numeric reuse permission, preserves snapshots, never
overwrites records and appends every run, including failures, to the run log), then
validates the registry and reports what changed:

- evidence_changed: observations, series, routes, models or stored snapshots changed.
- publish: evidence changed, or this is the first run of the UTC day (00:00-05:59)
  and a source check succeeded, so the published "source last checked" time stays
  within about a day without redeploying four times a day.

Exit codes: 0 all sources refreshed; 1 a source failed or the registry is invalid
(the failure is already in the run log); 3 a conflicting value was kept out for
review. This script never runs the pilot collector and reads no credentials.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ingest  # noqa: E402
import registry  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_FILES = ("models.json", "routes.json", "series.json", registry.OBSERVATIONS_FILE)
DAILY_PUBLISH_BEFORE_HOUR = 6
# A plain branch, tag or commit name; it is placed in a GitHub API URL.
REF_RE = re.compile(r"^(?!.*\.\.)[A-Za-z0-9][A-Za-z0-9._/-]{0,99}$")


def _state(registry_dir: Path, evidence_root: Path) -> dict:
    files = {name: hashlib.sha256((registry_dir / name).read_bytes()).hexdigest()
             for name in EVIDENCE_FILES if (registry_dir / name).is_file()}
    snapshots = sorted(p.relative_to(evidence_root).as_posix()
                       for p in evidence_root.rglob("*") if p.is_file()) if evidence_root.is_dir() else []
    return {"files": files, "snapshots": snapshots}


def refresh(registry_dir: Path, evidence_root: Path, *, ref: str = "main", now: datetime | None = None,
            get=ingest.http_get) -> dict:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0)
    before = _state(registry_dir, evidence_root)
    runs = [ingest.ingest(source_id, registry_dir, evidence_root, ref=ref, now=now, get=get)
            for source_id in sorted(ingest.ADAPTERS)]
    errors = registry.validate_registry(registry_dir, now=now)
    after = _state(registry_dir, evidence_root)
    evidence_changed = before != after
    succeeded = [r for r in runs if r["status"] == "succeeded"]
    failed = [r["id"] for r in runs if r["status"] != "succeeded"]
    conflicts = [r["id"] for r in runs if any(p.get("type") == "conflict" for p in r["problems"])]
    daily = now.hour < DAILY_PUBLISH_BEFORE_HOUR and bool(succeeded)
    return {
        "checked_at": ingest.stamp(now), "runs": [r["id"] for r in runs], "failed_runs": failed,
        "conflict_runs": conflicts, "registry_valid": not errors, "registry_errors": errors[:10],
        "evidence_changed": evidence_changed,
        "publish": not errors and (evidence_changed or daily),
        "publish_reason": ("evidence_changed" if evidence_changed else "daily_check_refresh" if daily else "none")
        if not errors else "registry_invalid",
    }


def exit_code(result: dict) -> int:
    if result["failed_runs"] or not result["registry_valid"]:
        return 1
    return 3 if result["conflict_runs"] else 0


def main(argv: list) -> int:
    allowed = {"--ref", "--github-output"}
    flags = argv[0::2]
    if len(argv) % 2 or any(flag not in allowed for flag in flags):
        print(__doc__)
        return 2
    options = dict(zip(argv[0::2], argv[1::2]))
    if not REF_RE.match(options.get("--ref", "main")):
        print("FAIL: --ref must be a plain branch, tag or commit name")
        return 2
    result = refresh(ROOT / "registry", ROOT / "evidence" / "snapshots", ref=options.get("--ref", "main"))
    print(json.dumps(result, indent=2))
    if "--github-output" in options:
        with open(options["--github-output"], "a", encoding="utf-8") as handle:
            handle.write(f"publish={'true' if result['publish'] else 'false'}\n")
            handle.write(f"evidence_changed={'true' if result['evidence_changed'] else 'false'}\n")
            handle.write(f"publish_reason={result['publish_reason']}\n")
    return exit_code(result)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
