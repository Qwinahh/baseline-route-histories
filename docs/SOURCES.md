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

## Not researched this session

Epoch AI Benchmarking Hub, LMArena, SWE-bench and other leaderboards were not
checked; no decision is implied.
