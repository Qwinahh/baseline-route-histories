# Baseline — AI model tests

Baseline's own repeated tests of a small set of exact AI models: every published result with its date, test size
and full history, and the largest observed movement in our latest comparable tests (descriptive, not a verdict).

**Current status:** the site shows only models with a scored Baseline result, published after review from
`own_results/` (method and rules in `docs/OWN_RESULTS_FORMAT.md`). Any other model link says "Not tested by
Baseline" and links to the tested models. The catalogue of models and apps from ten makers and the copied
third-party results stay in this repository as evidence, but the site no longer displays third-party scores. No
result here says whether a provider changed a model on purpose.

## What is here

- `catalog/`: the model and app directory, with no scores. Apps, direct APIs,
  third-party hosts and open weights are separate entries. Cited release dates are in
  `catalog/release_dates.json`. How both were checked is in `docs/CATALOG_SOURCES.md`.
- `registry/`: models, routes, sources, series, observations, ingestion runs and
  corrections. The rules are in `docs/DATA_CONTRACT.md` (schema v2).
- `own_results/`: Baseline's own aggregate results (counts only, no prompts or
  responses), the review manifest that admits them and the exact admitted candidates
  they are rebuilt from; `scripts/own_results.py` checks and imports them.
- `evidence/snapshots/`: unchanged copies of permitted source files, each stored with
  its licence and a manifest of hashes.
- `site/`: the static home and model pages (`site/measured.js` selects the tested models and the
  highlighted comparison). `scripts/build_site.py` builds them
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
