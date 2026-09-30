# Catalogue sources

`catalog/models.json` lists model identities and access routes. It holds no scores.
It is built by `catalog/build_catalog_data.py` and validated by `scripts/catalog.py`.
At publication (`scripts/build_site.py`), every registry route is linked once: a route
added by a later refresh attaches to the matching curated entry or gets an
evidence-only entry. The curated file is never rewritten by that step.

**Method.**
- Each maker's official model listing was downloaded and read, together with the
  linked detail pages where the listing did not give an identifier. Every identifier
  was confirmed verbatim in the downloaded page; identifiers were not taken from
  memory.
- **Check times:** first pass completed by 2026-09-30T08:07:11Z. Complete OpenAI and
  Mistral inventories and the Anthropic detail pages were completed by
  2026-09-30T09:01:11Z. Each entry records its own `checked_at`.
- **In scope:** text, chat, reasoning and coding models, including search, computer-use
  and deep-research model IDs where the maker lists them as models.
- **Not catalogued:**
  - embedding, speech, transcription, text-to-speech, image, video, music,
    moderation, OCR and rerank models;
  - realtime or live audio models;
  - agent products;
  - third-party models resold on a maker's platform (for example Z.ai GLM on Mistral).
- **Lifecycle rule (every maker):**
  - `available` only where the page says current, stable, live or still available,
    or lists a future retirement date;
  - `retired` only where it lists a retirement date that has passed;
  - `unknown` otherwise. Being listed is not a status claim.
- **Not exhaustive:** a maker may offer models its pages do not show.

## Counts at this checkpoint

208 entries from 10 makers:
- **Direct API, exact:** 187. Of these, 165 come from official listings and 22 are
  evidence-only historical routes.
- **Direct API, family-level:** 1 (Meta Muse Spark).
- **Consumer apps:** 9.
- **Third-party hosted routes:** 8.
- **Open weights / local:** 3 (gpt-oss-120b, gpt-oss-20b, Llama 4).

**Availability:** 52 available, 36 retired, 120 unknown. All 45 registry routes are linked
exactly once.

**Display names (T08):** 56 direct-API entries show the maker's own display name
(Anthropic's models overview and model pages; Mistral's deprecation table and model
pages), with the API identifier shown beside it and still searchable. Other entries
show the identifier.

| Maker | Official pages used | Result |
| --- | --- | --- |
| OpenAI | https://developers.openai.com/api/docs/models/all (complete list) and the models overview | 62 in-scope API IDs from the all-models page, plus `gpt-rosalind-research` from the overview. `gpt-oss-120b` and `gpt-oss-20b` are open-weight entries. Audio, realtime, image, TTS, transcription, embedding and moderation models excluded. The pages give no lifecycle status, so all are `unknown`. |
| Anthropic | https://platform.claude.com/docs/en/models/overview and the Opus 4.5 and Sonnet 4.5 model pages | 4 current and 9 legacy (still available). Opus 4.5 and Sonnet 4.5 use their dated IDs (`claude-opus-4-5-20251101`, `claude-sonnet-4-5-20250929`) from their own pages. |
| Google | https://ai.google.dev/gemini-api/docs/models | Stable and preview models are `available`. Three listed models with no stated status are `unknown`. |
| DeepSeek | https://api-docs.deepseek.com/quick_start/pricing/ | `deepseek-flash` is current; `deepseek-v4-pro` has no stated status; `deepseek-v4-flash` is listed as retired. |
| xAI | https://docs.x.ai/developers/models | 8 language models; status not stated. |
| Mistral AI | https://docs.mistral.ai/models and 7 current model pages under https://docs.mistral.ai/models/ | 7 current models with the dated API name from each model's page; each `-latest` alias is recorded in its notes. All 36 in-scope rows of the deprecation table, with status from the listed retirement date: `labs-leanstral-1-5` retires on the check date and is `unknown`. |
| Alibaba (Qwen) | https://www.alibabacloud.com/help/en/model-studio/models | 3 text-generation models; status not stated. |
| Moonshot AI | https://platform.kimi.ai/docs/pricing/chat | 4 chat models; status not stated. |
| Cohere | https://docs.cohere.com/docs/models | 12 live; 5 deprecated since 15 Sep 2025 with no retirement date (`unknown`). `command-a-03-2025-quality` does not appear. |
| Meta | https://dev.meta.ai/docs/models | Muse Spark versions 1.1–1.3 are named without an API identifier, so it is a family entry. Llama 4 is open weights (https://dev.meta.ai/llama/docs/model-cards-and-prompt-formats). |

## Release dates (T08)

117 of 208 entries carry a cited release date (`release`: date, precision, source); the
other 91 have no verified release date recorded and sort last. The reviewed table is
`catalog/release_dates.json`: `rows` holds the dates, and `research` records, for every
maker, the pages checked, the outcome and each undated identifier with its reason. The
generator copies each row onto the direct-API entry with the same maker and identifier,
and `scripts/catalog.py` validates the field. The site says "No verified release date
recorded" for undated entries; it does not claim that a search found nothing.

**Rules.**
- A date is used only when an official maker page states it for that exact identifier:
  a changelog or release-notes entry announcing the identifier, or a model page's
  "Released" field. Each claim quotes the page (whitespace from stripped markup removed).
- Dates are never inferred from a name suffix (for example `-2512` or `-20250929`), from
  when a page was checked, or from a benchmark run date.
- Preview, deprecation, fine-tuning or pricing notes are not releases. Moving aliases
  (`*-latest`, `chat-latest`, `deepseek-chat`, `deepseek-reasoner`, `deepseek-flash`)
  get no date, because the model behind them changes.
- Only direct-API entries receive a date. Apps, third-party hosts and open-weight
  entries have none yet.
- Precision is `day` for all current rows; `month` is allowed for sources that give
  only a month. A date may not be later than its source's check time.

**Sources** (downloaded 2026-09-30 by 17:24:52 UTC unless noted):

| Maker | Page | Dated |
| --- | --- | --- |
| OpenAI | https://developers.openai.com/api/docs/changelog | 42 |
| Mistral AI | https://docs.mistral.ai/getting-started/changelog ("We released …" entries) | 37 |
| Anthropic | models overview `releasedOn` (checked 08:07:11Z) for the 4 current models; each legacy model's page "Released" field (Opus/Sonnet 4.5 pages checked 09:01:11Z) | 13 |
| Google | https://ai.google.dev/gemini-api/docs/changelog | 10 |
| DeepSeek | https://api-docs.deepseek.com/updates | 2 |
| xAI | https://docs.x.ai/developers/release-notes | 1 |
| Cohere | dedicated release-note pages under https://docs.cohere.com/changelog/ (checked 2026-09-30T18:13:44Z) | 9 |
| Alibaba (Qwen) | https://www.alibabacloud.com/help/en/model-studio/newly-released-models ("Date" column; checked 18:13:44Z) | 3 |
| Moonshot AI | chat pricing and the K3, K2.7 Code and K2.6 quickstart pages; `/docs/changelog` redirects to Quickstart (checked 18:13:44Z) | 0 |
| Meta | https://dev.meta.ai/docs/models (checked 18:13:44Z) | 0 |

**Outcomes for the four makers added in the T08 review (R1).**
- **Cohere:** 9 dated. Each date is the dated release note that names the API
  identifier (for example Command A+ `command-a-plus-05-2026`, 20 May 2026). Undated:
  - `command-r-03-2024` and `c4ai-aya-vision-32b`: their announcements name no API
    identifier;
  - `command-r-plus-04-2024`, `c4ai-aya-expanse-32b` and `command-light`: no release
    note naming them was found;
  - `tiny-aya-global`: its model page gives no date;
  - `command-r` and `command-r-plus`: aliases.
- **Alibaba (Qwen):** 3 dated from the newly released models table, the same date in
  every service-scope row. `qwen3.7-plus` is listed with its snapshot
  `qwen3.7-plus-2026-05-26`; the date belongs to the row that names the stable
  identifier. `qwen-max-2025-01-25` (evidence only) is not in the current table.
- **Moonshot AI:** none dated. The checked pages state no release dates.
- **Meta:** none dated. Muse Spark and Llama 4 are family entries, which cannot carry a
  date, and the models page states none. The page now names Muse Spark 1.1–1.3 API
  identifiers; adding them as exact entries is a separate catalogue change, not made
  here.

**Other known gaps.** Some listed OpenAI, Google and xAI identifiers have no release statement
in the pages above (for example `gpt-5.2-pro`, `gpt-5.6-cyber`, `gemini-3.1-pro-preview`,
`grok-4.6`). `grok-build-0.1` is described as early access, which is not a release.
The xAI page gives the 2026 months without a year; they are read as 2026 because they
precede its "December 2025" heading.

## Consumer apps (separate entries, no measurements)

ChatGPT (chatgpt.com), Claude (claude.ai), Gemini (gemini.google.com), DeepSeek chat
(chat.deepseek.com), Grok (grok.com), Meta AI (meta.ai), Le Chat (chat.mistral.ai), Qwen
Chat (chat.qwen.ai) and Kimi (kimi.com).
- **Sources:** each is cited to the maker's own page that links it. Gemini and Qwen
  Chat are cited to the loaded app page itself.
- **Identity:** apps are `automatic` identities, with no exact version claimed.
- **No borrowed results:** API results are never attached to an app, and the
  validator and publication gate refuse it.
- **Cohere:** no consumer chat app was verified, so none is listed.

## Evidence-linked historical entries

Entries created from Aider evidence carry the pinned source line as their source, and
their availability is `unknown`. Where a maker's listing contains the same identifier
on the same route, the evidence links to that listed entry. The alias
`codestral-latest` is kept as its own historical entry, because it named a different
model when it was measured.

## Known gaps

- Mistral's `-latest` aliases and Anthropic's pre-4.6 aliases are recorded in notes,
  not as separate entries.
- Meta's Muse API identifiers were not published on the page.
- Cloud platforms (Amazon Bedrock, Google Cloud, Microsoft Foundry) are not catalogued
  as separate routes yet.
- Consumer-app entries do not record which models each app offers.
