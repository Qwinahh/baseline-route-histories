# Aider polyglot route review

Decisions for every row of the preserved Aider polyglot leaderboard snapshot (commit
`5dc9490b`, 69 rows), made on 30 September 2026 for the all-provider catalogue. The rules are
implemented in `scripts/aider_routes.py`; this file records the outcome for each row.

**Rules.**
- A row is accepted only when the row itself identifies the route: a provider prefix, a
  documented bare OpenAI or dated Claude model name, or an explicit API base belonging to
  the model's own provider. Aider's documentation at the pinned commit supports these
  conventions (`docs/llms/openai.md`, `anthropic.md`, `gemini.md`, `xai.md`,
  `openrouter.md`).
- The model's maker and the service that ran it are kept separate. OpenRouter, Fireworks
  AI and NVIDIA NIM are recorded as intermediaries, never as the maker's own API.
- Reasoning effort and thinking budget are part of the setup. A level named in the row's
  label must match what the row records; otherwise the row is excluded.
- Multi-model (architect/editor) runs are never attributed to one model.
- Rows whose stated pass rate does not match their own counts stay excluded, as before.
- Every accepted row is an API measurement run by the Aider project. None of these rows
  measures a consumer app such as ChatGPT, Claude, Gemini or Grok. The API alias
  `chatgpt-4o-latest` is recorded as an OpenAI API route, not as the ChatGPT app.
- The seven DeepSeek observations ingested in T02 keep their ids, values and
  fingerprints unchanged.

Totals: **50 accepted, 19 excluded**. All are historical third-party results
(dated 2024-12-21 to 2025-10-03), not current monitoring.

## Accepted (50)

| Row | Source label | Command | Maker | Service (access) | Identifier | Settings |
| --- | --- | --- | --- | --- | --- | --- |
| [L1](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L1) | Gemini 2.0 Pro exp-02-05 | `aider --model gemini/gemini-2.0-pro-exp-02-05` | Google | Google Gemini API (direct api) | `gemini-2.0-pro-exp-02-05` | none recorded |
| [L27](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L27) | gpt-4o-mini-2024-07-18 | `aider --model gpt-4o-mini-2024-07-18` | OpenAI | OpenAI API (direct api) | `gpt-4o-mini-2024-07-18` | none recorded |
| [L53](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L53) | claude-3-5-sonnet-20241022 | `aider --model claude-3-5-sonnet-20241022` | Anthropic | Anthropic API (direct api) | `claude-3-5-sonnet-20241022` | none recorded |
| [L79](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L79) | gpt-4o-2024-11-20 | `aider --model gpt-4o-2024-11-20` | OpenAI | OpenAI API (direct api) | `gpt-4o-2024-11-20` | none recorded |
| [L105](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L105) | gpt-4o-2024-08-06 | `aider --model gpt-4o-2024-08-06` | OpenAI | OpenAI API (direct api) | `gpt-4o-2024-08-06` | none recorded |
| [L157](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L157) | DeepSeek Chat V2.5 | `aider --model deepseek/deepseek-chat` | DeepSeek | DeepSeek API, selected by the LiteLLM provider prefix 'deepseek/' in the source's aider command (direct api) | `deepseek-chat` | none recorded |
| [L183](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L183) | claude-3-5-haiku-20241022 | `aider --model claude-3-5-haiku-20241022` | Anthropic | Anthropic API (direct api) | `claude-3-5-haiku-20241022` | none recorded |
| [L235](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L235) | o1-mini-2024-09-12 | `aider --model o1-mini` | OpenAI | OpenAI API (direct api) | `o1-mini` | none recorded |
| [L261](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L261) | gemini-exp-1206 | `aider --model gemini/gemini-exp-1206` | Google | Google Gemini API (direct api) | `gemini-exp-1206` | none recorded |
| [L287](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L287) | gemini-2.0-flash-exp | `aider --model gemini/gemini-2.0-flash-exp` | Google | Google Gemini API (direct api) | `gemini-2.0-flash-exp` | none recorded |
| [L339](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L339) | DeepSeek Chat V3 (prev) | `aider --model deepseek/deepseek-chat` | DeepSeek | DeepSeek API, selected by the LiteLLM provider prefix 'deepseek/' in the source's aider command (direct api) | `deepseek-chat` | none recorded |
| [L391](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L391) | Codestral 25.01 | `aider --model mistral/codestral-latest` | Mistral AI | Mistral API (direct api) | `codestral-latest` | none recorded |
| [L417](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L417) | DeepSeek R1 | `aider --model deepseek/deepseek-reasoner` | DeepSeek | DeepSeek API, selected by the LiteLLM provider prefix 'deepseek/' in the source's aider command (direct api) | `deepseek-reasoner` | none recorded |
| [L471](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L471) | qwen-max-2025-01-25 | `OPENAI_API_BASE=https://dashscope-intl.aliyuncs.com/compatible-mode/v1 aider --model openai/qwen-max-2025-01-25` | Alibaba (Qwen) | Alibaba Cloud Model Studio API (international), OpenAI-compatible endpoint recorded in the command (direct api) | `qwen-max-2025-01-25` | none recorded |
| [L548](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L548) | gemini-2.0-flash-thinking-exp-01-21 | `aider --model gemini/gemini-2.0-flash-thinking-exp-01-21` | Google | Google Gemini API (direct api) | `gemini-2.0-flash-thinking-exp-01-21` | none recorded |
| [L626](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L626) | claude-3-7-sonnet-20250219 (32k thinking tokens) | `aider --model anthropic/claude-3-7-sonnet-20250219 --thinking-tokens 32k` | Anthropic | Anthropic API (direct api) | `claude-3-7-sonnet-20250219` | thinking_tokens=32k |
| [L678](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L678) | QwQ-32B | `aider --model fireworks_ai/accounts/fireworks/models/qwq-32b` | Alibaba (Qwen) | Fireworks AI (intermediary) | `qwq-32b` | none recorded |
| [L758](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L758) | gemma-3-27b-it | `aider --model openrouter/google/gemma-3-27b-it` | Google | OpenRouter (intermediary) | `gemma-3-27b-it` | none recorded |
| [L784](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L784) | DeepSeek V3 (0324) | `aider --model deepseek/deepseek-chat` | DeepSeek | DeepSeek API, selected by the LiteLLM provider prefix 'deepseek/' in the source's aider command (direct api) | `deepseek-chat` | none recorded |
| [L810](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L810) | Gemini 2.5 Pro Preview 03-25 | `aider --model gemini/gemini-2.5-pro-preview-03-25` | Google | Google Gemini API (direct api) | `gemini-2.5-pro-preview-03-25` | none recorded |
| [L836](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L836) | chatgpt-4o-latest (2025-03-29) | `aider --model chatgpt-4o-latest` | OpenAI | OpenAI API (direct api) | `chatgpt-4o-latest` | none recorded |
| [L888](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L888) | Llama 4 Maverick | `aider --model nvidia_nim/meta/llama-4-maverick-17b-128e-instruct` | Meta | NVIDIA NIM (intermediary) | `llama-4-maverick-17b-128e-instruct` | none recorded |
| [L914](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L914) | Grok 3 Beta | `aider --model openrouter/x-ai/grok-3-beta` | xAI | OpenRouter (intermediary) | `grok-3-beta` | none recorded |
| [L966](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L966) | Grok 3 Mini Beta (high) | `aider --model xai/grok-3-mini-beta --reasoning-effort high` | xAI | xAI API (direct api) | `grok-3-mini-beta` | reasoning_effort=high |
| [L1018](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L1018) | gpt-4.1 | `aider --model gpt-4.1` | OpenAI | OpenAI API (direct api) | `gpt-4.1` | none recorded |
| [L1044](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L1044) | gpt-4.1-mini | `aider --model gpt-4.1-mini` | OpenAI | OpenAI API (direct api) | `gpt-4.1-mini` | none recorded |
| [L1070](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L1070) | gpt-4.1-nano | `aider --model gpt-4.1-nano` | OpenAI | OpenAI API (direct api) | `gpt-4.1-nano` | none recorded |
| [L1148](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L1148) | gemini-2.5-flash-preview-04-17 (default) | `aider --model gemini/gemini-2.5-flash-preview-04-17` | Google | Google Gemini API (direct api) | `gemini-2.5-flash-preview-04-17` | none recorded |
| [L1174](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L1174) | Gemini 2.5 Pro Preview 05-06 | `aider --model gemini/gemini-2.5-pro-preview-05-06` | Google | Google Gemini API (direct api) | `gemini-2.5-pro-preview-05-06` | none recorded |
| [L1200](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L1200) | Qwen3 32B | `aider --model openrouter/qwen/qwen3-32b` | Alibaba (Qwen) | OpenRouter (intermediary) | `qwen3-32b` | none recorded |
| [L1256](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L1256) | claude-sonnet-4-20250514 (no thinking) | `aider --model claude-sonnet-4-20250514` | Anthropic | Anthropic API (direct api) | `claude-sonnet-4-20250514` | none recorded |
| [L1284](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L1284) | claude-sonnet-4-20250514 (32k thinking) | `aider --model claude-sonnet-4-20250514` | Anthropic | Anthropic API (direct api) | `claude-sonnet-4-20250514` | thinking_tokens=32000 |
| [L1313](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L1313) | claude-opus-4-20250514 (no think) | `aider --model claude-opus-4-20250514` | Anthropic | Anthropic API (direct api) | `claude-opus-4-20250514` | none recorded |
| [L1341](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L1341) | claude-opus-4-20250514 (32k thinking) | `aider --model claude-opus-4-20250514` | Anthropic | Anthropic API (direct api) | `claude-opus-4-20250514` | thinking_tokens=32000 |
| [L1370](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L1370) | gemini-2.5-flash-preview-05-20 (no think) | `aider --model gemini/gemini-2.5-flash-preview-05-20` | Google | Google Gemini API (direct api) | `gemini-2.5-flash-preview-05-20` | thinking_tokens=0 |
| [L1399](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L1399) | gemini-2.5-flash-preview-05-20 (24k think) | `aider --model gemini/gemini-2.5-flash-preview-05-20` | Google | Google Gemini API (direct api) | `gemini-2.5-flash-preview-05-20` | thinking_tokens=24576 |
| [L1428](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L1428) | gemini-2.5-pro-preview-06-05 (default think) | `aider --model gemini/gemini-2.5-pro-preview-06-05` | Google | Google Gemini API (direct api) | `gemini-2.5-pro-preview-06-05` | none recorded |
| [L1456](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L1456) | gemini-2.5-pro-preview-06-05 (32k think) | `aider --model gemini/gemini-2.5-pro-preview-06-05 --thinking-tokens 32k` | Google | Google Gemini API (direct api) | `gemini-2.5-pro-preview-06-05` | thinking_tokens=32768 |
| [L1485](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L1485) | DeepSeek R1 (0528) | `aider --model deepseek/deepseek-reasoner` | DeepSeek | DeepSeek API, selected by the LiteLLM provider prefix 'deepseek/' in the source's aider command (direct api) | `deepseek-reasoner` | none recorded |
| [L1513](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L1513) | o3 (high) | `aider --model o3 --reasoning-effort high` | OpenAI | OpenAI API (direct api) | `o3` | reasoning_effort=high |
| [L1542](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L1542) | o3 | `aider --model o3` | OpenAI | OpenAI API (direct api) | `o3` | none recorded |
| [L1601](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L1601) | o3-pro (high) | `aider --model o3-pro` | OpenAI | OpenAI API (direct api) | `o3-pro` | reasoning_effort=high |
| [L1630](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L1630) | grok-4 (high) | `aider --model openrouter/x-ai/grok-4` | xAI | OpenRouter (intermediary) | `grok-4` | reasoning_effort=high |
| [L1659](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L1659) | Kimi K2 | `aider --model openrouter/moonshotai/kimi-k2` | Moonshot AI | OpenRouter (intermediary) | `kimi-k2` | none recorded |
| [L1687](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L1687) | gpt-oss-120b (high) | `aider --model openrouter/openai/gpt-oss-120b --reasoning-effort high` | OpenAI | OpenRouter (intermediary) | `gpt-oss-120b` | reasoning_effort=high |
| [L1715](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L1715) | gpt-5 (high) | `aider --model openai/gpt-5` | OpenAI | OpenAI API (direct api) | `gpt-5` | reasoning_effort=high |
| [L1744](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L1744) | gpt-5 (medium) | `aider --model openai/gpt-5` | OpenAI | OpenAI API (direct api) | `gpt-5` | reasoning_effort=medium |
| [L1773](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L1773) | gpt-5 (low) | `aider --model openai/gpt-5` | OpenAI | OpenAI API (direct api) | `gpt-5` | reasoning_effort=low |
| [L1802](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L1802) | DeepSeek-V3.2-Exp (Reasoner) | `aider --model deepseek/deepseek-reasoner` | DeepSeek | DeepSeek API, selected by the LiteLLM provider prefix 'deepseek/' in the source's aider command (direct api) | `deepseek-reasoner` | none recorded |
| [L1830](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L1830) | DeepSeek-V3.2-Exp (Chat) | `aider --model deepseek/deepseek-chat` | DeepSeek | DeepSeek API, selected by the LiteLLM provider prefix 'deepseek/' in the source's aider command (direct api) | `deepseek-chat` | none recorded |

## Excluded (19)

| Row | Source label | Command | Reason |
| --- | --- | --- | --- |
| [L131](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L131) | o1-2024-12-17 (high) | `aider --model openrouter/openai/o1` | inconsistent source values: pass_rate_2 61.7 does not equal pass_num_2/test_cases (139/224) |
| [L209](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L209) | Qwen2.5-Coder-32B-Instruct | `aider --model openai/Qwen/Qwen2.5-Coder-32B-Instruct # via hyperbolic` | unsupported command form |
| [L313](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L313) | yi-lightning | `aider --model openai/yi-lightning` | openai/ prefix with a non-OpenAI model and no recorded API base |
| [L365](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L365) | Qwen2.5-Coder-32B-Instruct | `aider --model openai/Qwen2.5-Coder-32B-Instruct` | openai/ prefix with a non-OpenAI model and no recorded API base |
| [L443](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L443) | DeepSeek R1 + claude-3-5-sonnet-20241022 | `aider --architect --model r1 --editor-model sonnet` | multi-model (architect/editor) run; cannot be attributed to one model |
| [L496](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L496) | o3-mini (medium) | `aider --model o3-mini` | label says 'medium' but the row records reasoning_effort=None |
| [L522](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L522) | o3-mini (high) | `aider --model o3-mini --reasoning-effort high` | inconsistent source values: pass_rate_2 60.4 does not equal pass_num_2/test_cases (136/224) |
| [L574](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L574) | chatgpt-4o-latest (2025-02-15) | `aider --model chatgpt-4o-latest` | inconsistent source values: pass_rate_2 27.1 does not equal pass_num_2/test_cases (61/223) |
| [L600](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L600) | claude-3-7-sonnet-20250219 (no thinking) | `aider --model sonnet` | alias 'sonnet' resolved to claude-3-5-sonnet-20241022 at the run's recorded commit 75e9ee6, but the row is labelled claude-3-7-sonnet-20250219 |
| [L652](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L652) | gpt-4.5-preview | `aider --model openai/gpt-4.5-preview` | inconsistent source values: pass_rate_2 44.9 does not equal pass_num_2/test_cases (101/224) |
| [L704](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L704) | QwQ-32B + Qwen 2.5 Coder Instruct | `aider --model fireworks_ai/accounts/fireworks/models/qwq-32b --architect` | multi-model (architect/editor) run; cannot be attributed to one model |
| [L732](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L732) | command-a-03-2025-quality | `OPENAI_API_BASE=https://api.cohere.ai/compatibility/v1 aider --model openai/command-a-03-2025-quality` | requested 'command-a-03-2025-quality' is not a model identifier found in Cohere's documentation |
| [L862](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L862) | Quasar Alpha | `aider --model openrouter/openrouter/quasar-alpha` | OpenRouter model 'openrouter/quasar-alpha' has no verifiable maker |
| [L940](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L940) | Grok 3 Mini Beta (low) | `aider --model openrouter/x-ai/grok-3-mini-beta` | label says 'low' but the row records reasoning_effort=None |
| [L992](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L992) | Optimus Alpha | `aider --model openrouter/openrouter/optimus-alpha` | OpenRouter model 'openrouter/optimus-alpha' has no verifiable maker |
| [L1096](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L1096) | o4-mini (high) | `aider --model o4-mini` | label says 'high' but the row records reasoning_effort=None |
| [L1122](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L1122) | openhands-lm-32b-v0.1 | `aider --model openrouter/all-hands/openhands-lm-32b-v0.1` | run name refers to o4-mini while the command requests openhands-lm-32b-v0.1; conflicting labels |
| [L1228](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L1228) | Qwen3 235B A22B diff, no think, Alibaba API | `aider --model openai/qwen3-235b-a22b` | openai/ prefix with a non-OpenAI model and no recorded API base |
| [L1570](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/polyglot_leaderboard.yml#L1570) | o3 (high) + gpt-4.1 | `aider --model o3` | inconsistent source values: pass_rate_2 78.2 does not equal pass_num_2/test_cases (176/224) |

## Notes on specific exclusions

- **Row "sonnet37-diff":** at the run's recorded commit `75e9ee6`, Aider's `sonnet`
  alias pointed to `claude-3-5-sonnet-20241022` (checked in `aider/models.py` at that
  commit). The row is labelled `claude-3-7-sonnet-20250219`, so the identity conflicts.
- **Rows through `openai/` without a recorded base URL** (Qwen, Yi, Qwen3 235B): the
  endpoint that served them is not recorded. One comment says "via hyperbolic", but a
  comment is not a recorded configuration.
- **Quasar Alpha and Optimus Alpha:** anonymous OpenRouter test models; their maker is
  not verifiable from the row.
- **"o4-mini-patch":** the run name and the requested model disagree.
- **Command A:** `command-a-03-2025-quality` does not appear as a model identifier in
  Cohere's documentation (see docs/CATALOG_SOURCES.md), so the route cannot be verified.
