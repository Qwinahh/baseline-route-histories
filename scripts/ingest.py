"""Permitted-source ingestion (T02). Standard library only.

    py -3.11 -B scripts/ingest.py fetch aider-polyglot [--ref main]    # network: pin + snapshot + ingest
    py -3.11 -B scripts/ingest.py snapshot aider-polyglot SNAPSHOT_DIR  # offline re-ingest

Rules:
- Only sources already in registry/sources.json with reuse_decision
  numeric_republication_permitted are ingested; this script never creates sources.
- A snapshot is stored under evidence/snapshots/<source>/<revision>/ with its
  licence and SNAPSHOT.json (URL, revision, retrieval time, sha256). Before use, the
  manifest must name this adapter's source/repository/revision/files and every file
  must match its hash; the licence must match a reviewed licence hash.
- Records are never overwritten. Identical re-ingestion counts as duplicate; a
  changed value is kept out and preserved as a conflict in the run log, and new
  records depending on a conflicted model/route/series are blocked.
- Every run, including fetch/parse/validation failures, is appended to
  registry/ingestion_runs.jsonl. Registry files change only if the merged registry
  validates.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parent))
import aider_polyglot  # noqa: E402
import registry  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ADAPTERS = {aider_polyglot.SOURCE_ID: aider_polyglot}
PERMITTED = "numeric_republication_permitted"
# Fields that must match for an existing record to count as a duplicate. Other
# fields (e.g. retrieved_at, evidence_url, source_revision) keep their first value.
COMPARE_FIELDS = {
    "models": ("provider", "exact_identifier"),
    "routes": registry.ROUTE_FINGERPRINT_FIELDS,
    "series": registry.FINGERPRINT_FIELDS + ("fingerprint",),
    "observations": ("series_id", "observed_at", "metric", "exclusions", "source_details"),
}
MANIFEST_KEYS = {"source_id", "repository", "revision", "requested_ref", "retrieved_at",
                 "files", "data_file", "sha256"}
USER_AGENT ="baseline-evidence-ingest/0.1 (+local, read-only)"


class IngestError(Exception):
    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def http_get(url: str, accept: str | None = None) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                                   **({"Accept": accept} if accept else {})})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def fetch_snapshot(adapter, evidence_root: Path, ref: str, now: datetime, get=http_get) -> Path:
    """Pin `ref` to a commit, download the data file and licence, store them unchanged."""
    try:
        revision = get(f"https://api.github.com/repos/{adapter.REPO}/commits/{ref}",
                       "application/vnd.github.sha").decode("ascii").strip()
    except Exception as exc:  # network, HTTP or decode failure
        raise IngestError("fetch_error", f"could not resolve {adapter.REPO}@{ref}: {exc}") from exc
    if len(revision) != 40 or any(c not in "0123456789abcdef" for c in revision):
        raise IngestError("fetch_error", f"unexpected commit id from GitHub: {revision[:60]!r}")
    files = {}
    for path in (adapter.DATA_PATH, adapter.LICENSE_PATH):
        url = f"https://raw.githubusercontent.com/{adapter.REPO}/{revision}/{path}"
        try:
            files[path] = (url, get(url))
        except Exception as exc:
            raise IngestError("fetch_error", f"could not download {url}: {exc}") from exc
    folder = evidence_root / adapter.SOURCE_ID / revision
    meta_path = folder / "SNAPSHOT.json"
    if meta_path.exists() or folder.exists() and any(folder.iterdir()):
        _, stored = verify_snapshot(folder, adapter)
        for path, (url, content) in files.items():
            if stored[Path(path).name] != content:
                raise IngestError("integrity_error", f"{folder} holds different {Path(path).name} "
                                                     "bytes for the same revision")
        return folder  # same pinned content already preserved; keep first retrieval time
    licence_hash = sha256_bytes(files[adapter.LICENSE_PATH][1])
    if licence_hash not in adapter.REVIEWED_LICENSE_SHA256:
        raise IngestError("rights_error", f"licence at {revision} (sha256 {licence_hash}) differs from the "
                                          "reviewed licence; reuse review required before ingesting")
    folder.mkdir(parents=True, exist_ok=True)
    meta = {"source_id": adapter.SOURCE_ID, "repository": adapter.REPO, "revision": revision,
            "requested_ref": ref, "retrieved_at": stamp(now), "files": {}}
    for path, (url, content) in files.items():
        name = Path(path).name
        (folder / name).write_bytes(content)
        meta["files"][name] = {"source_path": path, "url": url, "sha256": sha256_bytes(content)}
    meta["data_file"] = Path(adapter.DATA_PATH).name
    meta["sha256"] = meta["files"][meta["data_file"]]["sha256"]
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8", newline="\n")
    return folder


def read_manifest(folder: Path) -> dict:
    """Parse SNAPSHOT.json; any read/parse/shape problem is a classified failure."""
    try:
        meta = json.loads((folder / "SNAPSHOT.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise IngestError("snapshot_error", f"unreadable SNAPSHOT.json in {folder}: {exc}") from exc
    if not isinstance(meta, dict) or not isinstance(meta.get("files"), dict):
        raise IngestError("snapshot_error", f"SNAPSHOT.json in {folder} is not a manifest object with files")
    missing = sorted(MANIFEST_KEYS - set(meta))
    if missing:
        raise IngestError("snapshot_error", f"SNAPSHOT.json in {folder} is missing {missing}")
    return meta


def verify_snapshot(folder: Path, adapter) -> tuple[dict, dict]:
    """Check a stored snapshot belongs to `adapter`'s source and every file matches its hash.

    Returns (manifest, {file name: bytes}). The licence must be one the project reviewed:
    a changed licence needs a new reuse review, not the pinned decision.
    """
    folder = Path(folder)
    meta = read_manifest(folder)
    revision = meta["revision"]
    identity = {"source_id": adapter.SOURCE_ID, "repository": adapter.REPO}
    for key, expected in identity.items():
        if meta[key] != expected:
            raise IngestError("snapshot_error", f"snapshot {key} {meta[key]!r} is not {expected!r}")
    if not (isinstance(revision, str) and len(revision) == 40 and all(c in "0123456789abcdef" for c in revision)):
        raise IngestError("snapshot_error", f"snapshot revision {revision!r} is not a full commit id")
    if (folder.name, folder.parent.name) != (revision, adapter.SOURCE_ID):
        raise IngestError("snapshot_error", f"snapshot folder {folder} does not match "
                                            f"<{adapter.SOURCE_ID}>/<{revision}>")
    if not isinstance(meta["retrieved_at"], str) or not registry.UTC_RE.match(meta["retrieved_at"]):
        raise IngestError("snapshot_error", "snapshot retrieved_at is not a UTC timestamp")
    expected_files = {Path(p).name: p for p in (adapter.DATA_PATH, adapter.LICENSE_PATH)}
    if set(meta["files"]) != set(expected_files) or meta["data_file"] != Path(adapter.DATA_PATH).name:
        raise IngestError("snapshot_error", f"snapshot files {sorted(meta['files'])} do not match "
                                            f"expected {sorted(expected_files)}")
    contents = {}
    for name, path in expected_files.items():
        info = meta["files"][name]
        url = f"https://raw.githubusercontent.com/{adapter.REPO}/{revision}/{path}"
        if not isinstance(info, dict) or info.get("source_path") != path or info.get("url") != url:
            raise IngestError("snapshot_error", f"snapshot entry for {name} does not map to {url}")
        try:
            contents[name] = (folder / name).read_bytes()
        except OSError as exc:
            raise IngestError("integrity_error", f"snapshot file {name} is missing or unreadable: {exc}") from exc
        if sha256_bytes(contents[name]) != info.get("sha256"):
            raise IngestError("integrity_error", f"{name} hash does not match SNAPSHOT.json in {folder}")
    if meta["sha256"] != meta["files"][meta["data_file"]]["sha256"]:
        raise IngestError("integrity_error", "manifest sha256 does not match its data file entry")
    licence_hash = meta["files"][Path(adapter.LICENSE_PATH).name]["sha256"]
    if licence_hash not in adapter.REVIEWED_LICENSE_SHA256:
        raise IngestError("rights_error", f"snapshot licence sha256 {licence_hash} is not a reviewed licence; "
                                          "reuse review required")
    return meta, contents


def load_snapshot(folder: Path, adapter) -> tuple[dict, str]:
    meta, contents = verify_snapshot(folder, adapter)
    try:
        return meta, contents[meta["data_file"]].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise IngestError("parse_error", f"snapshot data is not UTF-8: {exc}") from exc


def merge(records: dict, candidates: dict) -> tuple[dict, list, dict]:
    """Add new records; count identical ones; keep existing on conflict."""
    new = {kind: [] for kind in candidates}
    problems, counts = [], {"new": {}, "duplicate": 0, "conflict": 0}
    for kind, items in candidates.items():
        known = {r.get("id"): r for r in records[kind] if isinstance(r, dict)}
        for item in items:
            existing = known.get(item["id"])
            if existing is None:
                known[item["id"]] = item
                new[kind].append(item)
                continue
            fields = COMPARE_FIELDS[kind]
            if all(existing.get(f) == item.get(f) for f in fields):
                if item not in new[kind]:
                    counts["duplicate"] += 1
                continue
            counts["conflict"] += 1
            problems.append({"type": "conflict", "kind": kind, "id": item["id"],
                             "kept": {f: existing.get(f) for f in fields},
                             "incoming": {f: item.get(f) for f in fields}})
        counts["new"][kind] = len(new[kind])
    return new, problems, counts


def block_conflict_dependents(new: dict, problems: list, candidates: dict, counts: dict) -> list:
    """Drop new records that depend on a conflicted model, route or series (review R1).

    A conflict means the incoming configuration differs from what an existing id means,
    so nothing built on that id may be admitted. Returns problems naming blocked ids.
    """
    conflicted = {kind: {p["id"] for p in problems if p["type"] == "conflict" and p["kind"] == kind}
                  for kind in ("models", "routes", "series")}
    bad = {"models": conflicted["models"]}
    bad["routes"] = conflicted["routes"] | {r["id"] for r in candidates["routes"]
                                            if r.get("model_id") in bad["models"]}
    bad["series"] = conflicted["series"] | {s["id"] for s in candidates["series"]
                                            if s.get("route_id") in bad["routes"]}
    bad["observations"] = {o["id"] for o in candidates["observations"] if o.get("series_id") in bad["series"]}
    blocked_problems, total = [], 0
    for kind, ids in bad.items():
        blocked = [r["id"] for r in new[kind] if r["id"] in ids]
        if blocked:
            new[kind] = [r for r in new[kind] if r["id"] not in ids]
            blocked_problems.append({"type": "blocked_by_conflict", "kind": kind, "ids": blocked,
                                     "reason": "depends on a conflicted model/route/series; existing records kept"})
            total += len(blocked)
        counts["new"][kind] = len(new[kind])
    counts["blocked"] = total
    return blocked_problems


def _write_json(path: Path, rows: list) -> None:
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"schema_version": registry.SCHEMA_VERSION, "records": rows},
                              indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def _append_jsonl(path: Path, rows: list) -> None:
    with open(path, "a", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _run_id(registry_dir: Path, source_id: str, started: datetime) -> str:
    base = f"run-{source_id}-{started.strftime('%Y%m%dt%H%M%Sz')}"
    existing, _ = registry.load_jsonl(registry_dir / "ingestion_runs.jsonl")
    taken = {r.get("id") for r in existing if isinstance(r, dict)}
    candidate, n = base, 1
    while candidate in taken:
        n += 1
        candidate = f"{base}-{n}"
    return candidate


def ingest(source_id: str, registry_dir: Path, evidence_root: Path, snapshot_dir: Path | None = None,
           ref: str = "main", now: datetime | None = None, get=http_get) -> dict:
    """Run one ingestion and append its run record. Returns the run record."""
    started = now or utc_now()
    run = {"id": _run_id(registry_dir, source_id, started), "source_id": source_id,
           "started_at": stamp(started), "finished_at": None, "status": "failed",
           "source_revision": None, "snapshot_path": None, "snapshot_sha256": None,
           "counts": {}, "problems": []}
    try:
        adapter = ADAPTERS.get(source_id)
        if adapter is None:
            raise IngestError("config_error", f"no adapter for source {source_id!r}")
        records, load_errors = registry.load_registry(registry_dir)
        if load_errors:
            raise IngestError("registry_error", "; ".join(load_errors))
        source = next((s for s in records["sources"] if s.get("id") == source_id), None)
        if source is None:
            raise IngestError("config_error", f"source {source_id!r} is not registered")
        if source.get("reuse_decision") != PERMITTED:
            raise IngestError("rights_error", f"source {source_id!r} reuse_decision is "
                                              f"{source.get('reuse_decision')!r}; ingestion refused")
        fetched = snapshot_dir is None
        if fetched:
            snapshot_dir = fetch_snapshot(adapter, evidence_root, ref, started, get)
        else:
            run["notes"] = ("Re-ingest of a stored snapshot. Upstream was not contacted, so the "
                            "source's revision and last successful check are unchanged.")
        meta, text = load_snapshot(snapshot_dir, adapter)
        run["source_revision"] = meta["revision"]
        run["snapshot_sha256"] = meta["sha256"]
        try:
            run["snapshot_path"] = Path(snapshot_dir).resolve().relative_to(ROOT).as_posix()
        except ValueError:
            run["snapshot_path"] = Path(snapshot_dir).as_posix()
        try:
            rows = adapter.parse_rows(text)
        except adapter.ParseError as exc:
            raise IngestError("parse_error", str(exc)) from exc
        candidates, row_problems, row_counts = adapter.build_records(rows, meta)
        run["problems"].extend(row_problems)
        # Fingerprint incoming series from the incoming route/model configuration, so a
        # changed configuration shows up as a series conflict rather than silently
        # matching the existing series (review R1).
        resolved = {kind: {r.get("id"): r for r in records[kind] if isinstance(r, dict)} |
                          {r["id"]: r for r in candidates[kind]}
                    for kind in ("routes", "models")}
        for series in candidates["series"]:
            series["fingerprint"] = registry.series_fingerprint(series, resolved["routes"], resolved["models"])
        new, merge_problems, merge_counts = merge(records, candidates)
        run["problems"].extend(merge_problems)
        run["problems"].extend(block_conflict_dependents(new, merge_problems, candidates, merge_counts))
        run["counts"] = {**row_counts, **merge_counts}
        merged = {kind: list(records[kind]) + new.get(kind, []) for kind in registry.FIELDS}
        if fetched:  # only a real upstream check advances the source's check record (T07)
            updated_source = dict(source, revision=meta["revision"], last_successful_check=stamp(started))
            merged["sources"] = [updated_source if s is source else s for s in records["sources"]]
        errors = registry.validate_records(merged, now=started)
        if errors:
            raise IngestError("validation_error", "; ".join(errors[:20]))
        for kind in registry.JSON_FILES:
            if kind == "sources" or new.get(kind):
                _write_json(registry_dir / f"{kind}.json", merged[kind])
        _append_jsonl(registry_dir / registry.OBSERVATIONS_FILE, new["observations"])
        run["status"] = "succeeded"
    except IngestError as exc:
        run["problems"].append({"type": exc.kind, "message": str(exc)})
    except Exception as exc:  # unexpected: still log the failed run (review R3)
        run["status"] = "failed"
        run["problems"].append({"type": "internal_error", "message": f"{type(exc).__name__}: {exc}"})
    run["finished_at"] = stamp(max(utc_now(), started) if now is None else started)
    _append_jsonl(registry_dir / "ingestion_runs.jsonl", [run])
    return run


def main(argv: list) -> int:
    if len(argv) < 2 or argv[0] not in ("fetch", "snapshot") or (argv[0] == "snapshot" and len(argv) < 3):
        print(__doc__)
        return 2
    ref = argv[argv.index("--ref") + 1] if "--ref" in argv else "main"
    snapshot = Path(argv[2]) if argv[0] == "snapshot" else None
    run = ingest(argv[1], ROOT / "registry", ROOT / "evidence" / "snapshots", snapshot, ref)
    print(json.dumps({k: run[k] for k in ("id", "status", "source_revision", "counts")}, indent=2))
    for problem in run["problems"]:
        print(f"  - {problem.get('type')}: {problem.get('message') or problem.get('reason') or problem.get('id')}")
    if run["status"] != "succeeded":
        return 1
    return 3 if any(p["type"] == "conflict" for p in run["problems"]) else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
