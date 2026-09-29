"""Publication gate for the static site (T05 release candidate). Stdlib only, offline.

    py -3.11 -B scripts/release_check.py [--manifest PATH]

Builds dist/ with scripts/build_site.py (which refuses an invalid registry or an
unreviewed licence before touching the output), then inspects the bundle:
- exactly the page files, data.js, the builder's marker and one reviewed licence per
  numeric source; nothing else;
- no raw source rows, snapshot manifests, pilot drafts, simulated trial data or
  credential-like text;
- the data keeps dates, source licences, the independent-monitoring flag and the
  scoped missing-coverage wording.
Exit 0 only when every check passes. --manifest writes file hashes outside dist/.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_site  # noqa: E402
import ingest  # noqa: E402
import registry  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
# Text that must never be published: raw source rows, snapshot manifests, pilot and
# simulated material, and credential names or key material.
FORBIDDEN_MARKERS = (b"- dirname:", b'"data_file"', b"simulated_trial", b"draft_pending_human_review",
                     b"SIMULATED-UNASSIGNED", b"pilot-draft", b"PRIVATE KEY", b"CLOUDFLARE_API_TOKEN",
                     b"ANTHROPIC_API_KEY", b"GITHUB_TOKEN")
# Statements whose truth depends on how the site is deployed; the page must use wording
# that is true both before and after activation (review T05 R3).
DEPLOYMENT_CLAIMS = ("not published", "local preview", "no schedule", "manual checks only",
                     "being monitored now")
REQUIRED_PAGE_TEXT = ("runs no independent tests of any model", "Baseline has not run its own tests on this route.", "no recorded evidence",
                      "No observations are recorded here")


def inspect_bundle(out_dir: Path, data: dict, records: dict) -> list:
    """Return problems with a built bundle; an empty list means it may be published."""
    problems = []
    files = {p.relative_to(out_dir).as_posix(): p for p in out_dir.rglob("*") if p.is_file()}
    licences = {s["licence"]["file"]: s for s in data["sources"] if s.get("licence")}
    expected = set(build_site.SITE_FILES) | {"data.js", build_site.OWNER_MARKER} | set(licences)
    for extra in sorted(set(files) - expected):
        problems.append(f"unexpected file in bundle: {extra}")
    for missing in sorted(expected - set(files)):
        problems.append(f"missing file in bundle: {missing}")
    for path, source in licences.items():
        if path in files:
            digest = hashlib.sha256(files[path].read_bytes()).hexdigest()
            if digest not in ingest.ADAPTERS[source["id"]].REVIEWED_LICENSE_SHA256:
                problems.append(f"{path} is not the reviewed licence for {source['id']}")
    numeric = [s["id"] for s in data["sources"] if s["reuse_decision"] == "numeric_republication_permitted"]
    for source_id in numeric:
        if not any(s["id"] == source_id and s.get("licence") for s in data["sources"]):
            problems.append(f"numeric source {source_id} has no bundled licence")
    for path, file in files.items():
        content = file.read_bytes()
        for marker in FORBIDDEN_MARKERS:
            if marker in content:
                problems.append(f"{path} contains forbidden text {marker.decode()!r}")
    app = files.get("app.js").read_text(encoding="utf-8") if "app.js" in files else ""
    for text in REQUIRED_PAGE_TEXT:
        if text not in app:
            problems.append(f"page is missing required wording {text!r}")
    page = (app + (files["index.html"].read_text(encoding="utf-8") if "index.html" in files else "")).lower()
    for claim in DEPLOYMENT_CLAIMS:
        if claim in page:
            problems.append(f"page makes a deployment-dependent claim {claim!r}")
    if data.get("independent_monitoring") is not False:
        problems.append("data must state that Baseline runs no independent monitoring")
    published = {o["id"]: o for r in data["routes"] for o in r["observations"]}
    if set(published) != {o["id"] for o in records["observations"]}:
        problems.append("published observations do not match the registry")
    for obs in records["observations"]:
        shown = published.get(obs["id"])
        if shown and (shown["observed_at"], shown["retrieved_at"]) != (obs["observed_at"], obs["retrieved_at"]):
            problems.append(f"{obs['id']}: published dates differ from the registry")
    return problems


def check_release(out_dir: Path, registry_dir: Path | None = None, evidence_root: Path | None = None,
                  generated_at: str | None = None, now=None) -> dict:
    """Build and inspect. Raises build_site.BuildError if the build itself is refused."""
    registry_dir = registry_dir or ROOT / "registry"
    data = build_site.build(out_dir, registry_dir=registry_dir, evidence_root=evidence_root,
                            generated_at=generated_at, now=now)
    records, _ = registry.load_registry(registry_dir)
    out = Path(out_dir).resolve()
    problems = inspect_bundle(out, data, records)
    manifest = {p.relative_to(out).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(out.rglob("*")) if p.is_file()}
    return {"ok": not problems, "problems": problems, "files": manifest,
            "routes": len(data["routes"]), "observations": len(records["observations"]),
            "generated_at": data["generated_at"]}


def main(argv: list) -> int:
    if argv and (argv[0] != "--manifest" or len(argv) != 2):
        print(__doc__)
        return 2
    try:
        result = check_release(ROOT / "dist")
    except build_site.BuildError as exc:
        print(f"FAIL: build refused: {exc}")
        return 1
    if argv:
        manifest = Path(argv[1]).resolve()
        if ROOT.resolve() in manifest.parents and (ROOT / "dist").resolve() in manifest.parents:
            print("FAIL: write the manifest outside dist/")
            return 2
        manifest.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    status = "OK" if result["ok"] else "FAIL"
    print(f"{status}: {len(result['files'])} files, {result['routes']} routes, "
          f"{result['observations']} observations")
    for problem in result["problems"]:
        print(f"  - {problem}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
