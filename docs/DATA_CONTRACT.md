# Evidence registry data contract (schema_version 2)

Implements runbook section 4. Validator: `scripts/registry.py` (standard library only).

```
py -3.11 -B scripts/registry.py                                         # production registry/
py -3.11 -B scripts/registry.py tests/fixtures/registry_valid --fixtures  # synthetic fixtures
```

## Files

`registry/` holds public records: `models.json`, `routes.json`, `sources.json`,
`series.json` (each `{"schema_version": 2, "records": [...]}`) and append-oriented
`observations.jsonl`, `ingestion_runs.jsonl` and `corrections.jsonl` (one object per
line). Unknown fields are rejected, so a schema change needs a version bump rather
than silent drift. The validator accepts only the current version.

## Version history and migration

- **v1 (T01):** models, routes, sources, series and observations; UTC timestamps only.
- **v2 (T03):** reconciles the additions T02 made without a bump (`ingestion_runs.jsonl`,
  observation `source_details`, day-precision `observed_at`) and adds
  `corrections.jsonl`. Migration from v1 changed only the `schema_version` header in
  the four JSON files. No record, observation, snapshot or run-log line was edited, and
  no hash or fingerprint changed. Files still marked v1 are rejected.

| Record | Required fields (all present; `null` only where noted) |
| --- | --- |
| Model | id, provider, public_name, exact_identifier, identifier_source_url, release_date (null = unknown), release_source_url (nullable), availability |
| Route | id, model_id → Model, access_type, service, requested_model, tier (nullable), region (nullable), settings |
| Source | id, author, url, method, access_method, reuse_decision, reuse_evidence, revision (nullable), retrieved_at, expected_update_cadence (nullable), last_successful_check (nullable) |
| Series | id, route_id → Route, source_id → Source, suite, suite_version, grader, prompt_set, harness, sampling, scope, baseline_definition, fingerprint |
| Observation | id, series_id → Series, observed_at, retrieved_at, metric, exclusions, evidence_url, source_revision (nullable); optional source_details |
| Ingestion run | id, source_id, started_at, finished_at, status (succeeded/failed), source_revision, snapshot_path, snapshot_sha256 (nullable), counts, problems |
| Correction | id, target_kind (`ingestion_runs`), target_id → that record, action (`superseded`), reason, recorded_at |

Corrections annotate an earlier append-only record without editing it. The two
development runs from T02 that were replaced before the first commit are marked
`superseded`. The page lists them as history, not evidence. Correction records for
observations (with reviewers and verdicts) are still to come.

All records accept optional `notes` and `fixture`.

## Rules enforced

- Timestamps are UTC `YYYY-MM-DDTHH:MM:SS[.ffffff]Z`, real, and not in the future.
  Exception (T02): when a source states only a calendar date, `observed_at` is kept
  at day precision as `YYYY-MM-DD` rather than inventing a time. Its timezone is
  unstated, so the future and retrieval-order checks allow one day of tolerance.
  `observed_at` is the source's measurement time; `retrieved_at` is ours and may not
  precede it. A result fetched today keeps its original observation date.
- References must resolve; ids are unique per record type.
- `metric` is `{name, numerator, denominator}` (0 ≤ n ≤ d, d > 0) or `{name, value, unit}`.
  `value` must be finite: NaN, ±Infinity and overflow such as `1e309` are rejected, as are
  integers beyond the float range (for example `10**400`; review H1).
  No invented error bars: there is no interval field.
- `exclusions` counts only fallback/refusal/error/retry/missing as non-negative integers.
- `source_details` (optional) holds a flat object of source-provided scalars (verbatim
  strings for the Aider adapter), including source comments as `comment:<field>`.
- Series `fingerprint` = sha256 of canonical route_id, source_id, suite, suite_version,
  grader, prompt_set, harness and sampling, plus the resolved route (model_id,
  access_type, service, requested_model, tier, region, settings) and model (provider,
  exact_identifier). Editing any of these, including a referenced route or model,
  fails validation. A changed configuration needs a new route id and a new series;
  the old series and its observations stay untouched. Two series with the same
  configuration are rejected. Source check metadata is excluded, so routine source
  re-checks do not break series.
- The hash only checks the current snapshot against the stored value. It cannot
  prove that no earlier snapshot was rewritten; Git history is the record for that.
- One series may hold only one observation per `observed_at` instant, compared
  after parsing (so `...:00Z` and `...:00.000Z` are duplicates).
- Observations may store numbers only when their source's `reuse_decision` is
  `numeric_republication_permitted`. `link_and_summary_only` and `not_reviewed`
  sources can be registered but carry no numeric observations.
- Fixture isolation: production mode rejects any record with `fixture: true` or an id
  starting `fixture-`; fixture mode requires both on every record. Fixtures live only
  under `tests/fixtures/`.

Malformed field types (for example a list where an enum string is expected) are
reported as validation errors with CLI exit 1, not as crashes.

## Ingestion (T02)

`scripts/ingest.py` ingests only sources already registered with
`numeric_republication_permitted`. It never creates or upgrades a source's rights.

- **Evidence preservation.** `fetch` pins the ref to a commit and stores the data file
  and licence unchanged under `evidence/snapshots/<source>/<commit>/`. It also writes
  `SNAPSHOT.json` with the URLs, first retrieval time and sha256 values. Re-fetching
  the same commit keeps the first copy; different bytes for the same commit fail as
  `integrity_error`. Before a snapshot is used, its manifest must name the adapter's
  source, repository, full commit and exactly the expected data and licence files (with
  their pinned URLs), stored in `<source>/<commit>/`. Every file must match its recorded
  sha256, and the licence hash must be one listed as reviewed for that adapter. A
  changed licence fails as `rights_error` until a new reuse review is done, and is not
  stored. `.gitattributes` marks snapshots `-text` so line endings are never rewritten. Snapshots are evidence, not site assets; keep them out of bundles.
- **Dates.** `observed_at` is the source's measurement date. `retrieved_at` is the first
  snapshot retrieval and is never updated by later re-ingestion.
- **Duplicates and corrections.** Ids are deterministic. An existing record with equal
  comparison fields counts as a duplicate. If the values differ, the existing record
  is kept and both versions go into the run's `problems` as a `conflict` (CLI exit 3)
  for human review. Nothing is overwritten. New routes, series and observations that
  depend on a conflicted model, route or series are not admitted. They are listed as
  `blocked_by_conflict`, so a changed configuration never joins an existing record.
- **Failures.** Every run appends one `ingestion_runs.jsonl` record. Failure kinds:
  fetch, parse, snapshot, integrity, rights, config, registry and validation errors,
  plus `internal_error` for anything unexpected, so no failure escapes unlogged.
  Unusable rows appear as `skipped_row` with a reason. Registry files are written
  only after the merged registry validates. A failed run leaves them unchanged, and
  the source's `last_successful_check` is not advanced.
- **Series.** For each Aider row, the series id is derived from its configuration.
  Repeated runs with an identical configuration join one series; a change to the
  harness, edit format, route or settings starts a new one.

## Not yet covered

Incident records and observation-level corrections (conflicts are logged but not yet
turned into reviewed correction records), and scheduled runs (T05). Display-side
freshness is implemented in `site/freshness.js` (T03).
