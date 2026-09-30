# Baseline — model histories

A directory of AI models across providers, with dated, traceable performance history
where reusable evidence exists, and every gap shown as a gap.

**Current status:** the directory lists models and apps from ten makers, taken from their
official model listings. The measurements are third-party results, copied with
permission and shown with their measurement dates. Baseline has not run its own tests on any model. Nothing is
independently monitored. No observation here says whether a provider changed a model
on purpose.

## What is here

- `catalog/`: the model and app directory, with no scores. Apps, direct APIs,
  third-party hosts and open weights are separate entries. How it was checked is in
  `docs/CATALOG_SOURCES.md`.
- `registry/`: models, routes, sources, series, observations, ingestion runs and
  corrections. The rules are in `docs/DATA_CONTRACT.md` (schema v2).
- `evidence/snapshots/`: unchanged copies of permitted source files, each stored with
  its licence and a manifest of hashes.
- `site/`: the static directory and model pages. `scripts/build_site.py` builds them
  into `dist/`.
- `scripts/`: the validators, source importer, reviewed route mappings, refresh and
  publication check.
- `ops/templates/`: workflow templates. They take effect only when copied into
  `.github/workflows/`.

## Sources and licences

- **Aider polyglot leaderboard** (Aider-AI/aider), Apache License 2.0. Numbers are
  reused with attribution, and the licence is kept beside each snapshot and bundled
  with the site. Benchmark exercises are not copied.
  - 50 of its 69 rows are mapped to exact API routes. Every decision is in
    `docs/AIDER_ROUTE_REVIEW.md`.
  - These are API measurements, never app measurements.
- **LiveNerf** (ninjahawk/livenerf) is linked only: no licence was chosen at the
  checked revision, so none of its numbers are reused.

Reuse decisions and candidate sources are recorded in `docs/SOURCES.md`.

## Check and build locally (Python 3.11 and Node, no packages needed)

```
python -B -m unittest discover -s tests
python -B scripts/registry.py
python -B scripts/catalog.py
python -B scripts/release_check.py
python -B -m http.server 8123 --bind 127.0.0.1 --directory dist
```
