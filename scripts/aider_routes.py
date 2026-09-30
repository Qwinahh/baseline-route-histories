"""Reviewed route mappings for Aider polyglot rows (T07). Stdlib only.

Each accepted row is mapped only from what the row itself records: the command's
provider prefix, bare model name or explicit API base, plus recorded reasoning and
thinking settings. The model maker and the service that ran it are kept separate.
Anything ambiguous is refused with a reason; docs/AIDER_ROUTE_REVIEW.md lists every
decision for the preserved snapshot.

Evidence for the routing conventions (Aider docs at the pinned source commit
5dc9490b): docs/llms/openai.md (bare OpenAI names use OPENAI_API_KEY),
docs/llms/anthropic.md (`aider --model <claude model name>`), docs/llms/gemini.md,
docs/llms/xai.md and docs/llms/openrouter.md (`openrouter/<provider>/<model>`).
"""
from __future__ import annotations

import hashlib
import json
import re

PINNED = "Aider docs at commit 5dc9490b"
# Direct provider APIs selected by a LiteLLM prefix. The DeepSeek text is unchanged
# from T02 so existing route fingerprints stay identical.
DIRECT_PREFIXES = {
    "deepseek": ("DeepSeek", "deepseek", "deepseek-api",
                 "DeepSeek API, selected by the LiteLLM provider prefix 'deepseek/' in the source's aider command"),
    "gemini": ("Google", "google", "gemini-api", "Google Gemini API"),
    "xai": ("xAI", "xai", "xai-api", "xAI API"),
    "mistral": ("Mistral AI", "mistral", "mistral-api", "Mistral API"),
    "anthropic": ("Anthropic", "anthropic", "anthropic-api", "Anthropic API"),
    "openai": ("OpenAI", "openai", "openai-api", "OpenAI API"),
}
OPENAI_NAME = re.compile(r"^(gpt-|chatgpt-|o\d)")
ANTHROPIC_NAME = re.compile(r"^claude-[a-z0-9.-]+-\d{8}$")  # dated Claude identifiers, as in Aider's docs
# Explicit API bases recorded in a command. Only a provider's own endpoint is mapped.
API_BASES = {
    "https://dashscope-intl.aliyuncs.com/compatible-mode/v1":
        ("Alibaba (Qwen)", "qwen", "alibaba-model-studio-api",
         "Alibaba Cloud Model Studio API (international), OpenAI-compatible endpoint recorded in the command"),
}
# Hosts that serve other makers' models: (service name, route prefix, maker lookup).
OPENROUTER_MAKERS = {"openai": ("OpenAI", "openai"), "x-ai": ("xAI", "xai"), "google": ("Google", "google"),
                     "qwen": ("Alibaba (Qwen)", "qwen"), "moonshotai": ("Moonshot AI", "moonshot"),
                     "meta-llama": ("Meta", "meta"), "mistralai": ("Mistral AI", "mistral"),
                     "anthropic": ("Anthropic", "anthropic"), "deepseek": ("DeepSeek", "deepseek")}
FIREWORKS_MODELS = {"qwq-32b": ("Alibaba (Qwen)", "qwen")}
NVIDIA_NIM_ORGS = {"meta": ("Meta", "meta")}
# Row-level decisions made after reading each row (docs/AIDER_ROUTE_REVIEW.md).
EXCLUDED_ROWS = {
    "2025-02-24-19-54-07--sonnet37-diff":
        "alias 'sonnet' resolved to claude-3-5-sonnet-20241022 at the run's recorded commit 75e9ee6, "
        "but the row is labelled claude-3-7-sonnet-20250219",
    "2025-04-19-14-43-04--o4-mini-patch":
        "run name refers to o4-mini while the command requests openhands-lm-32b-v0.1; conflicting labels",
    "2025-03-14-23-40-00--cmda-quality-whole2":
        "requested 'command-a-03-2025-quality' is not a model identifier found in Cohere's documentation",
}
COMMAND = re.compile(r"^(?:OPENAI_API_BASE=(https://\S+) )?aider --model (\S+)"
                     r"(?: --reasoning-effort (\S+))?(?: --thinking-tokens (\S+))?$")
LEVELS = ("low", "medium", "high")


def parse_tokens(value: str) -> int:
    """Aider's own rule (models.parse_token_value): k = 1024, M = 1024*1024."""
    value = str(value).strip().upper()
    multiplier = 1024 if value.endswith("K") else 1024 * 1024 if value.endswith("M") else 1
    return int(float(value.rstrip("KM")) * multiplier)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9._-]+", "-", text.lower()).strip("-.")[:100]


def _settings(row: dict, effort_flag, tokens_flag) -> tuple[dict, str | None]:
    settings = {key: row[key] for key in ("reasoning_effort", "thinking_tokens") if key in row}
    if effort_flag:
        if settings.setdefault("reasoning_effort", effort_flag) != effort_flag:
            return settings, "reasoning_effort field disagrees with the command flag"
    if tokens_flag:
        if "thinking_tokens" in settings and parse_tokens(settings["thinking_tokens"]) != parse_tokens(tokens_flag):
            return settings, "thinking_tokens field disagrees with the command flag"
        settings.setdefault("thinking_tokens", tokens_flag)
    return settings, None


def _label_conflict(label: str, settings: dict) -> str | None:
    """A reasoning or thinking level named in the label must match what the row records."""
    note = " ".join(re.findall(r"\(([^)]*)\)", label)).lower()
    effort = settings.get("reasoning_effort")
    for level in LEVELS:
        if re.search(rf"\b{level}\b", note) and effort != level:
            return f"label says '{level}' but the row records reasoning_effort={effort!r}"
    tokens = parse_tokens(settings["thinking_tokens"]) if "thinking_tokens" in settings else None
    match = re.search(r"(\d+)k think", note)
    if match and tokens not in (int(match.group(1)) * 1000, int(match.group(1)) * 1024):
        return f"label says {match.group(1)}k thinking but the row records thinking_tokens={tokens}"
    if "no think" in note and tokens not in (None, 0):
        return f"label says no thinking but the row records thinking_tokens={tokens}"
    return None


def classify(row: dict) -> tuple[dict | None, str | None]:
    """Return (mapping, None) for a reviewed route, or (None, reason)."""
    label, command = row.get("model", ""), row.get("command", "")
    if row.get("dirname") in EXCLUDED_ROWS:
        return None, EXCLUDED_ROWS[row["dirname"]]
    if row.get("edit_format") == "architect" or "editor_model" in row or " + " in label \
            or "--architect" in command or "--editor-model" in command:
        return None, "multi-model (architect/editor) run; cannot be attributed to one model"
    match = COMMAND.match(command)
    if not match:
        return None, "unsupported command form"
    base, requested, effort_flag, tokens_flag = match.groups()
    settings, problem = _settings(row, effort_flag, tokens_flag)
    if problem:
        return None, problem
    problem = _label_conflict(label, settings)
    if problem:
        return None, problem

    prefix, _, rest = requested.partition("/")
    access, notes = "direct_api", "Route inferred from the provider prefix recorded by the source; tier/region not stated."
    if base:
        if base not in API_BASES or prefix != "openai" or not rest:
            return None, "custom API base not mapped to a verified provider endpoint"
        maker, maker_key, route_prefix, service = API_BASES[base]
        exact, evidence = rest, f"API base {base} recorded in the command"
    elif not rest:
        if OPENAI_NAME.match(requested):
            (maker, maker_key, route_prefix, service), exact = DIRECT_PREFIXES["openai"], requested
            evidence = f"bare OpenAI model name; OpenAI API per {PINNED} (docs/llms/openai.md)"
        elif ANTHROPIC_NAME.match(requested):
            (maker, maker_key, route_prefix, service), exact = DIRECT_PREFIXES["anthropic"], requested
            evidence = f"bare Claude model name; Anthropic API per {PINNED} (docs/llms/anthropic.md)"
        else:
            return None, f"bare name {requested!r} is an unreviewed alias"
        notes = "Route inferred from a bare model name as documented by Aider; tier/region not stated."
    elif prefix in DIRECT_PREFIXES:
        if prefix == "openai" and not OPENAI_NAME.match(rest):
            return None, "openai/ prefix with a non-OpenAI model and no recorded API base"
        maker, maker_key, route_prefix, service = DIRECT_PREFIXES[prefix]
        exact, evidence = rest, f"LiteLLM provider prefix '{prefix}/' per {PINNED}"
    elif prefix == "openrouter":
        org, _, name = rest.partition("/")
        if org not in OPENROUTER_MAKERS or not name or "/" in name:
            return None, f"OpenRouter model '{rest}' has no verifiable maker"
        (maker, maker_key), exact = OPENROUTER_MAKERS[org], name
        access, service, route_prefix = "intermediary", "OpenRouter", f"openrouter.{org}"
        evidence = f"'openrouter/<provider>/<model>' per {PINNED} (docs/llms/openrouter.md)"
    elif prefix == "fireworks_ai":
        name = rest.rsplit("/", 1)[-1]
        if not rest.startswith("accounts/fireworks/models/") or name not in FIREWORKS_MODELS:
            return None, "Fireworks model without a reviewed maker"
        (maker, maker_key), exact = FIREWORKS_MODELS[name], name
        access, service, route_prefix = "intermediary", "Fireworks AI", "fireworks"
        evidence = "LiteLLM prefix 'fireworks_ai/' (Fireworks AI serverless model path)"
    elif prefix == "nvidia_nim":
        org, _, name = rest.partition("/")
        if org not in NVIDIA_NIM_ORGS or not name:
            return None, "NVIDIA NIM model without a reviewed maker"
        (maker, maker_key), exact = NVIDIA_NIM_ORGS[org], name
        access, service, route_prefix = "intermediary", "NVIDIA NIM", f"nvidia-nim.{org}"
        evidence = "LiteLLM prefix 'nvidia_nim/' (NVIDIA NIM hosted model path)"
    else:
        return None, f"provider prefix {prefix!r} has no reviewed route mapping"
    if access == "intermediary":
        notes = (f"Hosted by {service}; the model was made by {maker}. The host's serving "
                 "configuration is not stated by the source.")

    route_id = _slug(f"{route_prefix}.{exact}")
    if settings:
        digest = hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest()[:8]
        route_id = f"{route_id}.s{digest}"
    return {
        "maker": maker, "service_provider": service if access == "intermediary" else maker,
        "access_type": access, "requested_model": requested, "exact_identifier": exact,
        "model_id": _slug(f"{maker_key}.{exact}"), "route_id": route_id, "service": service,
        "settings": settings, "mapping_evidence": evidence, "route_notes": notes,
    }, None


def resolve_route(row: dict) -> dict | None:
    """The reviewed mapping for a row, or None when it is not (yet) mappable."""
    return classify(row)[0]
