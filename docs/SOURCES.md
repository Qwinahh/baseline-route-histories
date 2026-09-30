# Source reuse research

Record of reuse checks for candidate sources. A decision here is a project judgment
from the evidence listed, not legal advice; the reviewer should confirm new numeric
sources. Registry `reuse_decision` values must match this file.

| Source | Checked (UTC) | Evidence | Decision |
| --- | --- | --- | --- |
| LiveNerf (ninjahawk/livenerf) | 2026-09-28, commit 5bbe255a | README "License: Not yet chosen"; no LICENSE file; GitHub licence null | `link_and_summary_only`: no numbers copied. No author contact authorised. |
| Aider polyglot leaderboard (Aider-AI/aider `aider/website/_data/polyglot_leaderboard.yml`) | 2026-09-28, commit 5dc9490b | GitHub licence Apache-2.0; root LICENSE.txt is unmodified Apache 2.0 (sha256 cfc7749b…); data file is in that repository; no separate data terms in README.md, the leaderboard page source or `_config.yml`; no root NOTICE file | `numeric_republication_permitted`, with attribution and the licence kept alongside redistributed snapshots. Benchmark exercises (Exercism) are not copied. |

Reviewer decision (docs/T02_REVIEW.md): numeric reuse accepted for pinned commit
5dc9490b only. `scripts/aider_polyglot.py` lists the reviewed licence sha256, and
ingestion refuses a snapshot with any other licence bytes until it is reviewed again.

## Aider caveats (not rights issues, but they limit interpretation)

Reviewer follow-up, 29 September 2026: Codex verified the pinned data/licence bytes
against upstream and checked the repository tree and listed terms locations.
The numeric reuse decision is accepted for revision 5dc9490b under the attribution,
licence-retention and no-exercise-copying conditions above. This is a project
inference from the repository evidence, not blanket permission for unrelated
datasets or future licence changes. See docs/T02_REVIEW.md; importer integrity
fixes are still required before T03.

- These are the Aider project's own runs, not independent measurements. The newest
  row at the checked commit is dated 2025-10-03, so none of it is current monitoring.
- Rows give a date only (no time or timezone), stored at day precision.
- Rows name an API model string, which may be an alias. `deepseek/deepseek-chat` is
  labelled by the source as V2.5, V3, V3 (0324) and V3.2-Exp across four runs;
  the aider version changes each time too, so these are four separate series.
- Five non-selected rows (o1, o3-mini ×2, chatgpt-4o-latest Feb, gpt-4.5-preview)
  state a `pass_rate_2` that does not equal `pass_num_2/test_cases`. The adapter
  would skip them as inconsistent. Two rows carry source comments (for example
  `total_cost: 0 # incorrect: 6.3174`, `dirname is misleading`), which are
  preserved in `source_details`.
- Initial selection: `deepseek/deepseek-chat` and `deepseek/deepseek-reasoner` only
  (two model/route entries; the runbook allows up to three). Other providers' rows
  either use bare model names or intermediaries/overridden API bases that the adapter
  does not map without review. Provider diversity is an open gap.

## Candidate sources checked on 30 September 2026 (T07)

None of these is imported yet. Importing numbers needs a separately reviewed adapter,
with route mapping and reuse scope checked per benchmark. Old Aider results are not
presented as live testing.

| Candidate | Reuse terms found | Dating and identity | Finding |
| --- | --- | --- | --- |
| Epoch AI Benchmarking Hub (https://epoch.ai/data/ai-benchmarking-dashboard) | The page states Epoch AI's data is free to use, distribute and reproduce with credit under the Creative Commons Attribution licence. Data from external projects keeps its original licence. | Runs are dated. Models are named by API identifier (for example `gpt-4-0613`), with API-default settings. The page was updated 30 Sep 2026. | **Strongest next candidate.** It is newer and covers more than coding. Before import, check the licence of each benchmark's underlying data and map each API route explicitly. |
| LMArena (https://arena.ai/leaderboard, redirected from lmarena.ai) | The page states no reuse terms; it links to general terms of use that were not reviewed. | The page shows no run or measurement dates. Entries are display names and settings labels. | **Not suitable yet:** no reuse terms and no dated observations. These are preference rankings, not task pass rates. |
| SWE-bench (https://www.swebench.com/) | The page shows no reuse terms in the part checked. | Not established from the page. | **Not assessed.** The results repository and its licence would need checking. |

Consumer apps remain unmeasured: none of these sources measures ChatGPT, Claude,
Gemini or similar apps. API results must not be presented as app results.
