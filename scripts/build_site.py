"""Build the local model-history page (T03). Standard library only, offline.

    py -3.11 -B scripts/build_site.py            # writes dist/ (takes no arguments)
    py -3.11 -B -m http.server 8123 -d dist      # then open http://localhost:8123/
    py -3.11 -B scripts/build_site.py --own-results-preview CANDIDATE OUT_FOLDER
    py -3.11 -B scripts/build_site.py --puter-preview OUT_FOLDER

The preview form shows one unadmitted own-results candidate (T12) for review. It writes
only to a folder outside the project, marks the page as a review copy, and the release
check refuses its output. The default build reads only the admitted own_results/ dataset.

The Puter preview shows the labelled synthetic four-question fixtures
(tests/fixtures/own_results/puter/) through the same page, with preview-only catalogue
entries for the two Puter routes and a permanent "Synthetic preview" banner. It is a review
copy outside the project; nothing in catalog/ or own_results/ changes.

The builder only replaces files it wrote itself and never deletes folders
recursively; see check_output_dir for which output folders are accepted.

Copies the static page from site/ and writes dist/data.js from the validated registry.
Raw source snapshots are never copied; only the reviewed licence of each numeric
source is bundled, as its licence requires. Ages and freshness are computed in the
browser from the current time, so they keep changing without a rebuild.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import stat
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import catalog  # noqa: E402
import ingest  # noqa: E402
import own_results  # noqa: E402
import registry  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PUTER_PREVIEW = ("several-points.json", "gpt-several.json", "second-setup.json")
SITE_FILES = ("index.html", "styles.css", "app.js", "freshness.js", "directory.js", "results-chart.js")
OWNER_MARKER = ".baseline-build"
OWNED_FILES = frozenset(SITE_FILES + ("data.js", OWNER_MARKER))
# Series configuration fields whose change is shown as a configuration break.
BREAK_FIELDS = ("suite", "suite_version", "grader", "prompt_set", "harness", "sampling")


class BuildError(Exception):
    pass


def _series_letter(index: int) -> str:
    letters = ""
    index += 1
    while index:
        index, rest = divmod(index - 1, 26)
        letters = chr(65 + rest) + letters
    return letters


def build_data(records: dict, generated_at: str) -> dict:
    models = {m["id"]: m for m in records["models"]}
    series_by_id = {s["id"]: s for s in records["series"]}
    sources = {s["id"]: s for s in records["sources"]}
    superseded = {c["target_id"]: c["reason"] for c in records["corrections"]
                  if c["target_kind"] == "ingestion_runs" and c["action"] == "superseded"}

    routes = []
    for route in records["routes"]:
        observations = sorted((o for o in records["observations"]
                               if series_by_id[o["series_id"]]["route_id"] == route["id"]),
                              key=lambda o: (o["observed_at"][:10], o["observed_at"]))
        series_order = []
        for obs in observations:
            if obs["series_id"] not in series_order:
                series_order.append(obs["series_id"])
        letters = {sid: _series_letter(i) for i, sid in enumerate(series_order)}
        series_out = []
        for sid in series_order:
            s = series_by_id[sid]
            series_out.append({
                "id": sid, "letter": letters[sid], "source_id": s["source_id"],
                **{k: s[k] for k in BREAK_FIELDS}, "scope": s["scope"],
                "baseline_definition": s["baseline_definition"], "fingerprint": s["fingerprint"],
            })
        obs_out, previous = [], None
        for obs in observations:
            s = series_by_id[obs["series_id"]]
            label = (obs.get("source_details") or {}).get("model")
            breaks = []
            if previous is not None and previous["series_id"] != obs["series_id"]:
                ps = series_by_id[previous["series_id"]]
                breaks = [{"field": f, "from": ps[f], "to": s[f]} for f in BREAK_FIELDS if ps[f] != s[f]]
                previous_label = (previous.get("source_details") or {}).get("model")
                if previous_label != label:
                    breaks.append({"field": "source model label", "from": previous_label, "to": label})
            obs_out.append({
                "id": obs["id"], "series_id": obs["series_id"], "series_letter": letters[obs["series_id"]],
                "observed_at": obs["observed_at"],
                "precision": "day" if len(obs["observed_at"]) == 10 else "instant",
                "retrieved_at": obs["retrieved_at"], "metric": obs["metric"],
                "exclusions": obs["exclusions"], "evidence_url": obs["evidence_url"],
                "source_revision": obs["source_revision"], "source_label": label,
                "source_details": obs.get("source_details") or {}, "breaks": breaks,
            })
            previous = obs
        model = models[route["model_id"]]
        routes.append({
            "id": route["id"], "requested_model": route["requested_model"],
            "access_type": route["access_type"], "service": route["service"],
            "tier": route["tier"], "region": route["region"], "settings": route["settings"],
            "notes": route.get("notes"),
            "model": {k: model.get(k) for k in ("provider", "public_name", "exact_identifier",
                                                  "release_date", "availability", "notes")},
            "source_ids": sorted({s["source_id"] for s in series_out}),
            "series": series_out, "observations": obs_out,
        })
    routes.sort(key=lambda r: r["requested_model"])

    runs = [{
        "id": r["id"], "source_id": r["source_id"], "status": r["status"],
        "started_at": r["started_at"], "finished_at": r["finished_at"],
        "source_revision": r["source_revision"],
        "problem_types": sorted({p.get("type") for p in r["problems"] if isinstance(p, dict)}),
        "superseded": superseded.get(r["id"]),
    } for r in records["ingestion_runs"]]

    return {
        "generated_at": generated_at, "schema_version": registry.SCHEMA_VERSION,
        "independent_monitoring": False,
        # Baseline's own test record (T08), filled by build() from the admitted own-results
        # dataset (T12). Empty means every entry is "Not tested by Baseline".
        "baseline_tests": json.loads(json.dumps(own_results.EMPTY_TESTS)),
        "own_results_preview": False,
        "routes": routes,
        "sources": [{k: s.get(k) for k in (
            "id", "author", "url", "method", "access_method", "reuse_decision", "reuse_evidence",
            "revision", "retrieved_at", "expected_update_cadence", "last_successful_check", "notes")}
            | {"licence": _licence_info(s)} for s in sources.values()],
        "runs": runs,
    }


def _licence_info(source: dict) -> dict | None:
    adapter = ingest.ADAPTERS.get(source["id"])
    if adapter is None or source["reuse_decision"] != ingest.PERMITTED or not source.get("revision"):
        return None
    return {"name": adapter.LICENSE_NAME, "file": f"licenses/{source['id']}-LICENSE.txt",
            "upstream_url": f"https://github.com/{adapter.REPO}/blob/{source['revision']}/{adapter.LICENSE_PATH}"}


def own_tests(entries: list, data_path: Path | None = None, review_path: Path | None = None,
              preview: tuple = (), now: datetime | None = None) -> dict:
    """baseline_tests from the admitted dataset; `preview` candidates are added unadmitted (review copies only)."""
    try:
        dataset = own_results.load_admitted(data_path or own_results.DATA_PATH, review_path or own_results.REVIEW_PATH,
                                            now)
        for candidate in preview:
            bundle = own_results.parse_json(Path(candidate).read_bytes(), "preview candidate")
            own_results.validate_bundle(bundle, now)
            dataset = own_results.merge(dataset, bundle, None)
        return own_results.site_tests(dataset, entries)
    except (own_results.OwnResultsError, OSError) as exc:
        raise BuildError(f"own results: {exc}") from None


def build(out_dir: Path, registry_dir: Path | None = None, evidence_root: Path | None = None,
          generated_at: str | None = None, now: datetime | None = None, catalog_path: Path | None = None,
          own_data_path: Path | None = None, own_review_path: Path | None = None, own_preview: tuple = ()) -> dict:
    registry_dir = registry_dir or ROOT / "registry"
    evidence_root = evidence_root or ROOT / "evidence" / "snapshots"
    errors = registry.validate_registry(registry_dir, now=now)  # now: tests simulating later dates
    if errors:
        raise BuildError("registry does not validate: " + "; ".join(errors[:10]))
    records, _ = registry.load_registry(registry_dir)
    generated_at = generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    data = build_data(records, generated_at)
    # The catalogue is validated against the registry before anything is written (T07).
    try:
        document = catalog.load(catalog_path or catalog.CATALOG_PATH)
    except (OSError, ValueError) as exc:
        raise BuildError(f"catalogue unreadable: {exc}") from exc
    problems = catalog.validate_catalog(document, records, now)
    if problems:
        raise BuildError("catalogue does not validate: " + "; ".join(problems[:10]))
    # Every registry route is shown once, even one added by a refresh after the catalogue
    # was curated (T07 R1); the reconciled catalogue passes the same validation.
    try:
        entries, added = catalog.reconcile(document, records)
    except catalog.ReconcileError as exc:
        raise BuildError(str(exc)) from exc
    problems = catalog.validate_catalog({"schema_version": catalog.SCHEMA_VERSION, "entries": entries}, records, now)
    if problems:
        raise BuildError("reconciled catalogue does not validate: " + "; ".join(problems[:10]))
    preview_bundles = []
    for candidate in own_preview:
        try:
            bundle = own_results.parse_json(Path(candidate).read_bytes(), "preview candidate")
            own_results.validate_bundle(bundle, now)
        except (own_results.OwnResultsError, OSError) as exc:
            raise BuildError(f"own results: {exc}") from None
        preview_bundles.append(bundle)
    if any(own_results.is_puter(b) for b in preview_bundles):     # review copies only, never catalog/
        entries = entries + own_results.puter_preview_entries(entries)   # only routes the catalogue lacks
    data["catalog"] = entries  # routes are joined in the browser by id; no copies
    # Editorial Featured shortlist (T14): catalogue ids and written reasons only, validated.
    featured_path = (Path(catalog_path).parent if catalog_path else catalog.CATALOG_PATH.parent) / "featured.json"
    if featured_path.exists():
        try:
            featured = json.loads(featured_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise BuildError(f"featured list unreadable: {exc}") from exc
        problems = catalog.validate_featured(featured, entries, now)
        if problems:
            raise BuildError("featured list does not validate: " + "; ".join(problems[:10]))
        data["featured"] = featured
    else:
        data["featured"] = None
    data["catalog_evidence_only"] = added
    data["catalog_checked_at"] = document.get("checked_at")
    data["baseline_tests"] = own_tests(entries, own_data_path, own_review_path, tuple(own_preview), now)
    data["own_results_preview"] = bool(own_preview)
    data["synthetic_preview"] = any(own_results.is_puter(b) and b["series"]["synthetic"] for b in preview_bundles)

    # Prepare every output file in memory before touching the output folder.
    files = {name: (ROOT / "site" / name).read_bytes() for name in SITE_FILES}
    for source in data["sources"]:
        if source["licence"]:
            adapter = ingest.ADAPTERS[source["id"]]
            folder = evidence_root / source["id"] / source["revision"]
            try:
                _, contents = ingest.verify_snapshot(folder, adapter)
            except ingest.IngestError as exc:
                raise BuildError(f"cannot bundle licence for {source['id']}: {exc}") from exc
            files[source["licence"]["file"]] = contents[Path(adapter.LICENSE_PATH).name]
    payload = json.dumps(data, indent=1, sort_keys=True).replace("</", "<\\/")
    files["data.js"] = f"window.BASELINE_DATA = {payload};\n".encode("utf-8")
    files[OWNER_MARKER] = b"Generated by scripts/build_site.py; safe to delete and rebuild.\n"

    out_dir = check_output_dir(out_dir)
    _clear_owned_output(out_dir)
    (out_dir / "licenses").mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (out_dir / name).write_bytes(content)
    return data


def _is_link(path: Path) -> bool:
    """True for symlinks and Windows junctions/reparse points."""
    if os.path.islink(path):
        return True
    try:
        attributes = getattr(os.lstat(path), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _owned_entry(path: Path) -> bool:
    """Only files this builder writes (and its licenses folder of *-LICENSE.txt)."""
    if _is_link(path):
        return False
    if path.name == "licenses" and path.is_dir():
        return all(p.is_file() and not _is_link(p) and p.name.endswith("-LICENSE.txt") for p in path.iterdir())
    return path.is_file() and path.name in OWNED_FILES


def check_output_dir(out_dir: Path) -> Path:
    """Refuse any output folder whose existing contents this builder does not own (review R1).

    Allowed: the project's dist/ folder, or a folder outside the project, provided it
    is missing, empty, or holds only files this builder writes. Always refused: the
    project folder, anything inside it other than dist/, any ancestor of it, and
    symlinks or junctions. Raises BuildError before anything is written or deleted.
    """
    target = Path(os.path.abspath(out_dir))
    for path in [target, *target.parents]:
        if path.exists() and _is_link(path) and (path == target or ROOT in (path, *path.parents) or
                                                   path in ROOT.parents):
            raise BuildError(f"refusing output {target}: {path} is a symlink or junction")
    resolved = target.resolve()
    root, dist = ROOT.resolve(), (ROOT / "dist").resolve()
    if resolved == root or resolved in root.parents:
        raise BuildError(f"refusing output {resolved}: it is the project folder or contains it")
    if root in resolved.parents and resolved != dist:
        raise BuildError(f"refusing output {resolved}: inside the project, only {dist} may be written")
    if resolved.exists():
        if not resolved.is_dir():
            raise BuildError(f"refusing output {resolved}: it is not a folder")
        foreign = sorted(p.name for p in resolved.iterdir() if not _owned_entry(p))
        if foreign:
            raise BuildError(f"refusing output {resolved}: it holds files this build did not create "
                             f"({', '.join(foreign[:5])}); choose an empty or missing folder")
    return resolved


def _clear_owned_output(out_dir: Path) -> None:
    """Remove only files check_output_dir confirmed as ours; never a recursive delete."""
    if not out_dir.exists():
        return
    licences = out_dir / "licenses"
    if licences.is_dir():
        for path in licences.iterdir():
            path.unlink()
    for name in OWNED_FILES:
        if (out_dir / name).is_file():
            (out_dir / name).unlink()


def main(argv: list) -> int:
    preview = len(argv) == 3 and argv[0] == "--own-results-preview"
    puter = len(argv) == 2 and argv[0] == "--puter-preview"
    if argv and not (preview or puter):
        print("usage: py -3.11 -B scripts/build_site.py   (always writes the project's dist/ folder)")
        print("       py -3.11 -B scripts/build_site.py --own-results-preview CANDIDATE OUT_FOLDER")
        print("       py -3.11 -B scripts/build_site.py --puter-preview OUT_FOLDER")
        return 2
    out_dir = ROOT / "dist"
    try:
        if preview or puter:
            out_dir = Path(os.path.abspath(argv[-1]))
            root = ROOT.resolve()
            if out_dir.resolve() == root or root in out_dir.resolve().parents or out_dir.resolve() in root.parents:
                raise BuildError("a review copy is written outside the project, never to dist/")
            candidates = (Path(argv[1]),) if preview else tuple(
                own_results.FIXTURE_DIR / "puter" / name for name in PUTER_PREVIEW)
            data = build(out_dir, own_preview=candidates)
            if puter and not data["synthetic_preview"]:
                raise BuildError("the Puter preview must be built from the synthetic fixtures only")
        else:
            data = build(out_dir)
    except BuildError as exc:
        print(f"FAIL: {exc}")
        return 1
    count = sum(len(r["observations"]) for r in data["routes"])
    print(f"OK: wrote {out_dir} ({len(data['routes'])} routes, {count} observations, "
          f"generated {data['generated_at']})")
    if preview or puter:
        print("REVIEW COPY: includes an unadmitted own-results candidate; do not publish this folder.")
    if puter:
        print("SYNTHETIC PREVIEW: labelled test data only, not real measurements.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
