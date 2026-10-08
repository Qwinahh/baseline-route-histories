# Baseline's own results: method, data format and admission

Baseline runs a small question set of its own through a model's API and publishes only
aggregate counts. This page describes what those counts are, the files that hold them
and how a result is admitted. The checker is `scripts/own_results.py` (standard library
only). It is used by the site build and the release check.

## Method in brief

- **Questions:** a set of short, original questions written for Baseline, grouped into
  categories. The published data gives the set's identifier, size, categories and
  sha256. The first set (`calibration-v1`) has 40 questions in four categories:
  structured extraction, constraint following, evidence-bound answers and bounded
  reasoning.
- **Settings:** each question is sent through one exact API route with pinned
  settings: temperature, thinking level, output limit and timeout. These are recorded
  with every result.
- **Grading:** answers are graded automatically against a fixed answer key (for the
  first set, `grader-v0`). The key holds an exact answer, a JSON object, a whole number
  or a choice. Grading is strict: a right answer in the wrong format is a format error.
- **First attempt counts.** Every scheduled question lands in exactly one first-attempt
  outcome:
  - correct, incorrect or format error;
  - identity mismatch or unknown;
  - refusal, truncated, empty or malformed;
  - timeout, provider error, rate limited, authentication or client error;
  - not sent.

  After a request error, one retry may be made. Answers recovered that way are counted
  separately and never added to the first-attempt score.
- **Usable day:** a daily run counts as usable only if at least 90% of its questions
  were attempted.

### Kinds of result

- **One-off setup test** (`calibration`): a single run made to check the questions and
  settings before daily testing. It is never part of the daily history and cannot show
  a change.
- **Daily test** (`daily`): at most one run per UTC date, inside a declared window and
  campaign. Missed windows can appear in three ways, and the page keeps them distinct:
  - a recorded gap;
  - a date with no record at all;
  - a run whose evidence is unavailable.

  Dates whose window had not closed when the data were prepared are *not yet due*.
  Nothing is filled in.

### Limits

- The questions were written and first run as a setup test before this description was
  published. The method was therefore not publicly preregistered.
- No formal plan for judging changes exists yet. The site shows no decline, improvement
  or stability verdict.
- Results apply only to the exact API route tested. An app, another host or another
  model version is a separate entry and is not covered.
- Prompts and raw responses stay private. Free-tier prompts are not guaranteed to stay
  out of a provider's data, so later results could move because of training exposure
  as well as model changes.
- **Provenance:** the counts come from Baseline's private run records. The publisher
  checked those records against stored sha256 hashes before export:
  - every run file against its run manifest;
  - the report against the series state;
  - the run's configuration fingerprint and question-set file;
  - a recount of the report from its own attempt records.

  The hashes identify that evidence, but visitors cannot inspect it. This is
  publisher-verified, not independently auditable.

## Files

- `own_results/review.json`: the review manifest. It lists the sha256 of every
  candidate file that a reviewer has admitted, with the review time.
- `own_results/admitted/<sha256>.json`: the exact bytes of every admitted candidate.
  These are aggregate records only, with no prompts or responses.
- `own_results/data.json`: the published dataset. Each series is stored once, with its
  route, series details, `as_of` time and records, and the dataset lists the sha256 of
  each admitted candidate. It is a merge of the admitted copies.
  - Loading re-merges those copies and requires the result to match `data.json` byte
    for byte. The `admitted/` folder must hold exactly the copies the dataset names.
  - An edited count, an added or removed record, changed settings, or a missing or
    substituted copy therefore fails the build and the release check.
  - Only `scripts/own_results.py import` changes these files.

  This catches accidental or unreviewed edits. It is not a defence against a publisher
  who deliberately rewrites the review manifest and copies too.

A candidate (a bundle) has exactly these fields:

- `format`, which is `baseline-own-results`;
- `format_version`: `1`, or `2` for a daily bundle (see below);
- `as_of`: a canonical UTC time, `YYYY-MM-DDTHH:MM:SSZ`;
- `route`: `route_id`, `maker`, `exact_identifier` and `access_kind` (`direct_api`,
  `intermediary` or `cloud_platform`);
- `series`: `series_id` (route, kind and fingerprint prefix), `kind`,
  `config_fingerprint`, `panel_id`, `panel_sha256`, `panel_items`, `panel_categories`,
  `grader_version`, `settings` and `schedule`:
  - a setup test has `{"type": "once"}`;
  - a daily series has `type`, `start_date`, `end_date`, `window_start_utc` and
    `window_minutes`;
- `records`: aggregate records that use the same keys and count rules as the daily
  aggregate in Baseline's measurement service.

Every record must have exactly these fields:

- `aggregate_version`, `kind`, `date`, `status` and `evidence`;
- `route_id`, `requested_model`, `settings`, `panel_id`, `panel_sha256`, `series_id` and
  `config_fingerprint`;
- `run_id` and `report_sha256`;
- `first_attempt_correct`, `scheduled_items`, `first_attempt_outcomes`,
  `retry_recovered`, `attempted_items` and `valid_day`;
- `interpretation`, which must be the fixed sentence for its kind.

Each record is also checked against its route and series, and the following rules
apply:

- Outcome counts add up to the scheduled items.
- Correct equals the `correct` outcome.
- Attempted equals scheduled minus not sent.
- `valid_day` follows the 90% rule.
- Recovered answers never exceed the operational first-attempt errors.
- Run IDs carry the record's date and the configuration's fingerprint prefix.
- A gap has no run, report or counts.
- Unavailable evidence has no counts.

The checker refuses:

- unknown or nested extra fields;
- booleans used as counts;
- non-finite numbers;
- credential-shaped text and free text;
- files over 1 MB and records later than `as_of`.

### Schedule-only daily bundles and versions (T13)

- **Version 2** of the bundle is daily-only. It adds a required `open_dates` list, and it
  may be *schedule-only*: route, series and campaign with `records: []`, so the page can
  draw the campaign's dates before the first closed run. A schedule-only bundle never
  counts as a test or a run. Calibration bundles stay version 1, so the admitted setup
  test re-exports byte for byte. Earlier version 1 daily bundles remain valid and mean
  "no open dates".
- **`open_dates`** (T13 review R2) lists scheduled dates whose run had started but not
  closed when the private record was checked:
  - the list is sorted and distinct, within the campaign, and the window had closed by
    `as_of`;
  - an open date never has a record;
  - such a date carries no score, and it is neither a gap nor a missed day;
  - `as_of` stays the true check time, so later closed records and gaps still publish.

  In the dataset, each daily series keeps `open_dates` from its newest check (a tie
  keeps the union) minus any date that now has a record. The result therefore does not
  depend on import order, and a later check that closes the date resolves it without
  changing published records.
- **Dataset version 2** (`data.json`) allows two kinds of source:
  - person-reviewed, `{sha256, reviewed_at}`;
  - policy-admitted, `{sha256, admitted_at, policy_sha256}`.

  To convert a version 1 dataset, run `py -3.11 -B scripts/own_results.py migrate`. It
  changes only the version number, and only if the admitted copies rebuild the existing
  content exactly.

### Graph data and eligibility

- Each entry has a `daily_series` list, newest schedule first. Each item holds:
  - `series_id`, `as_of`, `schedule`, `rows`, `not_yet_due`, `pending_dates` and
    `open_dates`;
  - `panel_items` (the score scale), `panel_id`, `settings`, `grader_version` and
    `config_fingerprint`.

  A changed setup is a different series and is never joined to another. `daily` is the
  first item, and the status counts come from it alone.
- Each row has a `date`, a `state` (`completed`, `stopped`, `interrupted`, `gap`, `open`
  or `no_record`), its `record` (null for `open` and `no_record`) and an `eligible` flag.
  The graph shows an `open` day as an unresolved mark (o) in the no-score lane.
- **Eligible:** only verified, completed runs in which every scheduled question was
  attempted become graph points. A stopped run that reached the 90% `valid_day` threshold
  is shown separately with its attempted count, but it is not a point.
- **No invented scores:** a recorded gap, a date with no record and unavailable evidence
  carry no score. A verified completed run with zero correct answers is a real point at
  zero.
- **Pending dates:** campaign dates after `as_of` are pending. `as_of` is the time up to
  which the private record was checked, not a measurement date.

### Puter four-question results (bundle version 3, prepared, not yet admitted)

**Version 3** is exactly the `puter-subset-v1` contract. Versions 1 and 2, their Gemini
records, validation, wording and admitted bytes are unchanged, and a version-3 envelope
never carries a Gemini series (or the reverse).

**Route.** One of the three reviewed intermediary routes, exactly:
- `puter-claude-sonnet-5-5`, labelled "Claude Sonnet 5.5 via Puter";
- `puter-gpt-6.1-sol`, labelled "GPT-6.1 Sol via Puter";
- `puter-x-ai-grok-4.7`, labelled "Grok 4.7 via Puter" (maker xAI, requested model
  `x-ai/grok-4.7`, Puter provider `xai`; three-route campaign from 8 October 2026). The route
  id replaces the model's `/` with `-` so ids stay path- and URL-safe.

Each route has `access_kind: "intermediary"`, `service_provider: "Puter"`, its maker, the
exact identifier and the requested Puter `provider`. It is never maker-API or
consumer-app coverage.

**Series.** A series carries:
- the parent panel (`parent_panel_id`, `parent_panel_sha256`, `parent_panel_items`, which
  must be larger than the subset);
- the ordered subset: `subset_item_ids` with each item's content hash, prompt hash and
  category, and `planned_items: 4`;
- `grader_version`;
- the actual Puter settings: SDK package and version, model, provider, `max_tokens`
  1–128, `stream: false`, `retries: 0` and `reasoning_effort` (or null). Gemini's
  temperature and thinking settings are never invented. The Grok route has exactly these
  plus its own reviewed values, and nothing else: `max_tokens: 1000` (the provider-enforced
  cap), `accepted_models: ["grok-4.7", "x-ai/grok-4.7"]` (returned names counted as the
  requested model), `meter_prefix: "xai:grok-4_dot_7:"` and `temperature_forwarded: false`,
  with `reasoning_effort: null`. Claude and GPT may not carry these fields;
- `synthetic` (true only for preview fixtures).

**Fingerprints.** The validator recomputes `subset_fingerprint` and `series_fingerprint`
from these public fields. The second is the collector's own series identity, and
`series_id` is `<route_id>--daily--<12 hex>`. A changed question, prompt, grader, route,
SDK or setting is therefore always a separate series. Claude and GPT hash exactly their
original fields (their identities did not change when Grok was added); Grok's identity also
holds its own settings and its request position ("item-major, after Claude and GPT"), which
gives the collector's `puter-x-ai-grok-4.7--daily--291df76c8060`.

**Records.** Every record has `record_version: 1`, `date`, `status` (`completed`,
`stopped`, `incomplete` or `gap`), the Puter `run_id`, `evidence` and the stored result's
`evidence_sha256`. Verified records also carry the counts:
- `attempted`, `answered`, `correct`, `incorrect`, `format_error` and `not_sent`;
- `not_graded`: refusal, truncated, missing text, malformed, error and uncertain;
- `identity`: unknown, reported match and mismatch.

The counts must add up, with the planned four as the denominator:
- attempted + not sent = 4;
- correct + incorrect + format error = answered;
- answered + not graded = attempted;
- the identity counts = attempted.

Booleans, fractions and non-finite numbers are refused, as are unknown fields at any
depth.

**Identity is separate from grading.** A correct answer with no returned model counts as
`unknown`, never as confirmed. The page shows "Model identity not confirmed" unless every
attempted response reported the requested model.

**Points.** A record is a graph point only if:
- its evidence is verified;
- all four questions were attempted and answered (gradeable);
- there is no identity mismatch.

A run stopped after this route's four questions still counts. Partial, ungradeable,
mismatched, incomplete or unavailable days appear in the table only. A complete genuine
zero is a point at zero. "3 correct of 3 sent" is never shown as 100%: it is "3 of 4
correct, 3 attempted".

**Evidence.** Candidates come only from `scripts/export_puter_results.py`, a private,
offline exporter, in this order:
1. It checks each dated setup (a `baseline-puter-setups` file): the exact configuration
   bytes, and the hash-bound authorization that restates them, the panel, schedule and
   destination, whose id is its own hashes' id and whose campaign dates cover the setup's
   dates. Setups are in date order and never overlap.
2. It reads an explicit snapshot with the reviewed collector checks: ledger chain and
   head, create-once checkpoint, date and claim tags, and stored evidence bytes against the
   ledger hash, for every run including one-off calibration claims.
3. Only then are one-off claims (route calibrations) excluded: they own no daily date and
   are never a daily record, gap or open date, but a tampered or missing calibration
   artifact still stops the export.
4. Each daily run is bound to the setup of its date: the configuration hash, authorization
   id and series ids its reservation recorded. Another setup inside a setup's dates, or a
   listed setup's run outside its own dates, is refused.
5. It binds each run's planned item/model pairs (8 for two routes, 12 for three, in the
   configured order), item and prompt hashes and exact per-route settings (Grok's 1000-token
   cap included), and refuses duplicate or swapped rows.
6. It regrades from the verified response text with `collector.grade`.

A series shared by consecutive setups with the same identity (Claude and GPT across the
two-to-three-route change on 8 October) is one continuous series over their dates; a route
added later starts at its first authorized date (Grok: 8 October, never 7 October). A series
that would resume after a break between setups is refused.

Copied `summary.json` and series files are never read. If the response text was omitted
from bounded evidence, the record is `unavailable` with no numbers. Uncertain
(`incomplete`) runs never carry numbers. A reservation not yet settled is an open date,
and only once its window has closed. Gap lines name no setup, so a gap belongs to the setup
authorized for its date.

**What `as_of` may know (review R1).**
- The exporter uses only the ledger lines time-stamped at or before `as_of`. The ledger is
  in time order, so this is a reloaded prefix.
- A run reserved later is absent.
- A run settled, recorded incomplete or reconciled later is still unresolved in that view:
  an open date if its window had closed, otherwise pending, never a score.
- The public validator also refuses any record whose run id encodes a start time later
  than `as_of`, to the second. The existing Gemini rule is unchanged.

**Evidence origin (review R2).**
- Every stored result artifact must state its origin (`synthetic`) before its status is
  considered, whether the run settled, was recorded incomplete or was reconciled.
  Production refuses synthetic evidence, and a synthetic preview refuses genuine evidence.
- Only two collector-written notes carry no origin, because nothing provable was sent: the
  child wrote no result, or the token was absent after the reservation. Those runs are
  exported with no numbers (`incomplete` or `stopped`, `unavailable`) and make no origin
  claim.
- Unresolved reservations likewise only produce open dates. The series' `synthetic` flag
  is the export mode, which every origin-bearing artifact in it must match.

**Admission.** Puter candidates are admitted by a person-reviewed digest, or automatically
under an approved Puter policy (below), never under a Gemini-type policy. A synthetic series is refused by the exporter in production
mode, by any import into the production dataset, and by `load_admitted` for the
production `data.json`. The synthetic fixtures' digests are also on the existing fixture
refusal list.

**Catalogue entries.** `catalog/models.json` lists the three routes so `site_tests` maps
each exactly once: `puter.claude-sonnet-5-5`, `puter.gpt-6.1-sol` and `puter.x-ai-grok-4.7`.
Each is labelled "… via Puter", with `access_kind: "intermediary"`, `service_provider: "Puter"`,
the route's maker and exact requested identifier, `availability: "unknown"` and no release
date. Each cites Puter's public AI model listing (https://api.puter.com/puterai/chat/models,
checked 2026-10-07T23:58:07Z). That listing's names (`anthropic:anthropic/claude-sonnet-5-5`,
`openai:openai/gpt-6.1-sol`, `x-ai:x-ai/grok-4.7`) are Puter's catalogue names, not the SDK
provider routing names (`claude`, `openai-completion`, `xai`), and do not confirm which model
answers a request. The maker-API and app entries are separate and never matched. The Sources
page lists an intermediary's listing under that service, not under the maker. Preview builds
add preview-only stand-ins only for routes a catalogue lacks. See
docs/PUTER_RESULTS_PUBLICATION.md.

**Display.**
- Each Puter `daily_series` item has `contract: "puter-subset-v1"`, the requested route
  and its label, the subset and settings, `synthetic`, and `panel_items: 4` as the chart
  scale.
- The page shows:
  - the route label, "Small sample: 4 questions" and "Model identity not confirmed" (unless
    every attempted answer reported the requested model);
  - a 0–4 integer axis;
  - a table with correct, attempted, not graded or errors, and model identity per day;
  - "No daily results yet" (no points) and "Not enough history to show change" (one
    point).
- Puter series are never added to the 40-question test-method list and never ranked
  against Gemini.

**Preview and release boundary.**
- `scripts/build_site.py --puter-preview OUT` builds a review copy from the synthetic
  fixtures. It sets `synthetic_preview: true` and shows a permanent "Synthetic preview —
  not real measurements" banner.
- The release check refuses any page whose `synthetic_preview` is not false.
- The public export leaves out `tests/fixtures/own_results/puter/`, the exporter and its
  tests.
- The private package includes the exporter, but not its synthetic fixtures.

### Puter 40-question reference evaluations (bundle version 4, prepared)

**Version 4** is exactly the `puter-reference-v1` contract. It is separate from the four-question quick check
(version 3) and never merged with it. Versions 1–3, their records, validation and admitted bytes are unchanged.

**Route.** One of the three reviewed Puter routes, exactly as in version 3. Results are for the requested Puter
route, never maker-API or app coverage.

**Series.** Exact fields:
- `contract` (`puter-reference-v1`), `kind` (`reference`) and `synthetic`;
- the panel (`parent_panel_id`, `parent_panel_sha256`), `grader_version` and `planned_items: 40`;
- all 40 `item_ids` in panel order, with each item's `item_sha256`, `prompt_sha256` and category (`categories`);
- the actual route `settings` (the version-3 settings rules, Grok's own values included);
- `batch_plan`, the planned batch sizes (1–16 each, 40 in total);
- `series_fingerprint`, recomputed from the panel, items, prompts, grader, settings and batch plan, and
  `series_id` = `<route_id>--reference--<12 hex>`.

**Records.** One per finished evaluation. Exact fields:
- `record_version: 1`, `evaluation_id` (the cycle), and `status`: `complete`, `partial`, `stopped` or `expired`;
- `started_at` (the first batch's reservation) and `finished_at` (the last batch's settlement), real timestamps;
  `date` is the finish date. An evaluation that spans UTC dates shows its interval, never a single day;
- `batches` and one `batch_evidence_sha256` per batch (1–18);
- the version-3 counts out of 40: `attempted`, `answered`, `correct`, `incorrect`, `format_error`,
  `not_graded` (including `uncertain`), `not_sent` and `identity`, adding up exactly as in version 3;
- `route_id`, `series_id`, `planned_items` and the fixed `interpretation` text.

Questions in a batch whose outcome is uncertain (an interrupted or unverifiable batch) count as attempted and
`uncertain`, never as answers. Questions never sent count as `not_sent`. A `complete` evaluation has nothing
unsent and nothing uncertain. Only evaluations that have finished are published: a running evaluation is never
published, and a published record never changes.

**Graph point.** A complete evaluation with all 40 questions answered (gradeable) and no identity mismatch.
Partial, stopped and expired evaluations stay visible in the table with their real counts.

**Evidence and admission.** Candidates come only from `export_puter_results.build_reference_candidates`, after
the whole shared ledger, tags and evidence hashes are verified. Every batch must have been reserved under the
reviewed configuration and authorization, and is regraded with `collector.grade`. Admission is by a person-reviewed
digest or a Puter policy whose `series` is the exact reference series.

## Policy admission (automated publication, T13)

An automated publisher may admit daily candidates without a person reviewing each one,
but only under a **publication policy that a person approved**.

- `own_results/policy_review.json` is person-maintained. Its format is
  `baseline-own-results-policy-review` v1, with `approved: [{sha256, reviewed_at}]`.
- `own_results/policies/<sha256>.json` keeps the exact bytes of each approved policy.
- **A policy names** (format `baseline-own-results-policy` v1, exact fields):
  - `enabled` and `route`;
  - `series_kind` (`daily`) and the full `config_fingerprint`;
  - `panel_sha256`, `panel_items`, `grader_version` and `settings`;
  - the `campaign` schedule;
  - `public_repository` and `public_branch`;
  - `allowed_paths`, which must be exactly `own_results/admitted/` and
    `own_results/data.json`.
- **Admission:** a policy-admitted source must name an approved, enabled policy, and its
  bundle's route, fingerprint, panel, grader, settings and schedule must equal the
  policy's. The admission time (`admitted_at`) must not be before the policy's approval
  or before the bundle's `as_of`.
- **Labelling:** such sources are policy-verified, not individually person-reviewed. The
  review manifest is never changed by them.
- **Failing closed:** removing an approval, altering a kept policy, or keeping an
  unapproved policy file fails the build and the release check.
- **Limits:** the publisher can write only the two allowed paths. It cannot create or
  change a policy, and it cannot touch `review.json`.

**Puter policies** (format `baseline-own-results-puter-policy` v1, automatic Puter
publication, 8 October 2026) cover exactly one genuine four-question series. Exact fields:
- `format`, `format_version` (1) and `enabled` (a boolean; an approved policy must be enabled);
- `route`: the complete public Puter route object (one of the three reviewed routes);
- `series`: the complete public series object, checked by the bundle-v3 rules (contract,
  parent panel, ordered subset with item and prompt hashes and categories, grader, actual
  settings, recomputed subset and series fingerprints, series id and the fixed schedule),
  with `synthetic: false`;
- `public_repository`, `public_branch` and `allowed_paths` as above.

A Puter source is admitted only if its bundle's `route` and `series` equal the policy's
exactly, and the timing rules above hold. A Gemini-type policy never covers a Puter bundle
and a Puter policy never covers a Gemini bundle. Existing Gemini policies and every
person-reviewed source load unchanged.

## Admission and import

1. A reviewer inspects a candidate:

   ```
   py -3.11 -B scripts/own_results.py inspect CANDIDATE
   ```

   This validates the candidate and prints its sha256 with a summary.
2. If it is correct, the reviewer adds `{"sha256": ..., "reviewed_at": ...}` to
   `own_results/review.json`. A bundle can never admit itself: any `reviewed` field
   inside a bundle is refused.
3. Import the candidate:

   ```
   py -3.11 -B scripts/own_results.py import CANDIDATE
   ```

   The import checks the admission, the bundle, the review manifest and the existing
   dataset (rebuilt from its admitted copies). It then keeps the exact candidate bytes in
   `own_results/admitted/` and writes the dataset, each atomically:
   - importing the same records again changes nothing;
   - overlapping or out-of-order candidates merge to the same history;
   - a run already published with different contents is refused, as is a second run
     for a published date. Either needs a reviewed correction, which this version does
     not provide.

   Any failure leaves the dataset byte for byte unchanged.
4. Check and release:

   ```
   py -3.11 -B scripts/own_results.py check
   py -3.11 -B scripts/release_check.py
   ```

   The release check rebuilds the site and re-derives every own-result entry from the
   admitted dataset. It refuses:
   - review copies;
   - unadmitted sources;
   - hand-edited results;
   - any synthetic test fixture digest (`tests/fixtures/own_results/`).

To look at an unadmitted candidate before deciding, build a review copy outside the
project:

```
py -3.11 -B scripts/build_site.py --own-results-preview CANDIDATE OUT_FOLDER
```

The page is marked as a review copy, and the release check refuses it.

## Site wording

The directory and model page share one status derivation (`site/directory.js`):

- **Not tested by Baseline:** there is no own result for this exact entry.
- **One-off setup test:** only a setup test, shown with its score and date and "Not
  enough repeated tests to judge a change".
- **Collecting baseline:** daily results, with the newest usable day at most two days
  old.
- **No recent test:** daily results exist but none is recent. This is a display
  convention, not a health check of the collector.
- **Test unavailable:** the latest scheduled date has no usable result, whether it was
  missed, interrupted, unavailable or below 90% attempted.

Change verdicts appear only from a reviewed analysis, and none exists.
