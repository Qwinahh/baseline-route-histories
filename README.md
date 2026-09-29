# Baseline — route histories

A small, dated record of how specific AI model API routes have performed, with every
number linked to its source and every gap shown as a gap.

**Current status:** the published data consists of historical third-party results,
copied with permission. Baseline has not run its own tests on these routes, and
nothing is being monitored independently. No observation here says whether a
provider changed a model on purpose.

## What is here

- `registry/`: models, routes, sources, series, observations, ingestion runs and
  corrections. The rules are in `docs/DATA_CONTRACT.md` (schema v2).
- `evidence/snapshots/`: unchanged copies of permitted source files, each stored with
  its licence and a manifest of hashes.
- `site/`: the static page. `scripts/build_site.py` builds it into `dist/`.
- `scripts/`: the validator, source importer, refresh and publication check.
- `ops/templates/`: workflow templates. They are inactive until copied into
  `.github/workflows/`.

## Sources and licences

- Aider polyglot leaderboard (Aider-AI/aider), Apache License 2.0. Numbers are reused
  with attribution; the licence is kept beside each snapshot and bundled with the
  site. Benchmark exercises are not copied.
- LiveNerf (ninjahawk/livenerf) is linked only: no licence was chosen at the checked
  revision, so none of its numbers are reused.

Reuse decisions are recorded in `docs/SOURCES.md`.

## Check and build locally (Python 3.11, no packages needed)

```
python -B -m unittest discover -s tests
python -B scripts/registry.py
python -B scripts/release_check.py
python -B -m http.server 8123 --bind 127.0.0.1 --directory dist
```
