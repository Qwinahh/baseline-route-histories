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
- `format_version`, which is `1`;
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
