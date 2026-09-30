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
