"""Regenerate catalog/models.json from the reviewed listings below (T07). Stdlib only.

    py -3.11 -B catalog/build_catalog_data.py

The listings were read from each provider's official model page on 30 September 2026
(CHECKED); every identifier was confirmed verbatim in the downloaded page. See
docs/CATALOG_SOURCES.md. Evidence-linked historical entries are generated from the
registry routes, one entry per model and access route, and never carry scores here.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import registry  # noqa: E402

CHECKED = "2026-09-30T08:07:11Z"
PAGES = {
    "OpenAI": "https://developers.openai.com/api/docs/models",
    "Anthropic": "https://platform.claude.com/docs/en/models/overview",
    "Google": "https://ai.google.dev/gemini-api/docs/models",
    "DeepSeek": "https://api-docs.deepseek.com/quick_start/pricing/",
    "xAI": "https://docs.x.ai/developers/models",
    "Mistral AI": "https://docs.mistral.ai/models",
    "Alibaba (Qwen)": "https://www.alibabacloud.com/help/en/model-studio/models",
    "Moonshot AI": "https://platform.kimi.ai/docs/pricing/chat",
    "Cohere": "https://docs.cohere.com/docs/models",
    "Meta": "https://dev.meta.ai/docs/models",
}
LLAMA_CARDS = "https://dev.meta.ai/llama/docs/model-cards-and-prompt-formats"
MAKER_KEYS = {"OpenAI": "openai", "Anthropic": "anthropic", "Google": "google", "DeepSeek": "deepseek",
              "xAI": "xai", "Mistral AI": "mistral", "Alibaba (Qwen)": "qwen", "Moonshot AI": "moonshot",
              "Cohere": "cohere", "Meta": "meta"}

RECHECKED = "2026-09-30T09:01:11Z"  # T07 R2: complete inventories and detail pages
OPENAI_ALL = "https://developers.openai.com/api/docs/models/all"
MISTRAL_DETAIL = "https://docs.mistral.ai/models/"
# Lifecycle rule (all makers): "available" only where the page says current/stable/live/
# still available, or gives a future retirement date; "retired" only where it gives a
# past retirement date; otherwise "unknown". A listing alone is not a status claim.
OPENAI_IN_SCOPE = (
    "babbage-002", "davinci-002", "chatgpt-4o-latest", "chat-latest", "codex-mini-latest", "computer-use-preview",
    "gpt-3.5-turbo", "gpt-4", "gpt-4-turbo", "gpt-4-turbo-preview", "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano",
    "gpt-4.5-preview", "gpt-4o", "gpt-4o-mini", "gpt-4o-search-preview", "gpt-4o-mini-search-preview",
    "gpt-5", "gpt-5-chat-latest", "gpt-5-codex", "gpt-5-mini", "gpt-5-nano", "gpt-5-pro", "gpt-5.1",
    "gpt-5.1-chat-latest", "gpt-5.1-codex", "gpt-5.1-codex-max", "gpt-5.1-codex-mini", "gpt-5.2",
    "gpt-5.2-chat-latest", "gpt-5.2-codex", "gpt-5.2-pro", "gpt-5.3-chat-latest", "gpt-5.3-codex", "gpt-5.4",
    "gpt-5.4-mini", "gpt-5.4-nano", "gpt-5.4-pro", "gpt-5.5", "gpt-5.5-pro", "gpt-5.6-cyber", "gpt-5.6-luna",
    "gpt-5.6-sol", "gpt-5.6-terra", "gpt-6-astra", "gpt-6-luna", "gpt-6-sol", "gpt-6.1-sol",
    "gpt-daybreak-blue-latest", "gpt-daybreak-red-latest", "o1", "o1-mini", "o1-preview", "o1-pro", "o3",
    "o3-deep-research", "o3-mini", "o3-pro", "o4-mini", "o4-mini-deep-research")
# Mistral deprecation table rows in scope: (api name, display name, deprecation, retirement).
MISTRAL_TABLE = [
    ("labs-leanstral-1-5", "Leanstral 1.5", "2026-09-29", "2026-09-30"),
    ("labs-leanstral-2603", "Leanstral", "2026-05-22", "2026-06-30"),
    ("mistral-medium-2508", "Mistral Medium 3.1", "2026-05-22", "2026-08-31"),
    ("mistral-small-2506", "Mistral Small 3.2", "2026-04-30", "2026-07-31"),
    ("devstral-2512", "Devstral 2", "2026-05-22", "2026-07-31"),
    ("magistral-medium-2507", "Magistral Medium 1.1", "2025-10-31", "2025-11-30"),
    ("labs-mistral-small-creative", "Mistral Small Creative", "2026-03-31", "2026-04-30"),
    ("labs-devstral-small-2512", "Devstral Small 2", "2026-02-27", "2026-03-31"),
    ("magistral-medium-2509", "Magistral Medium 1.2", "2026-05-22", "2026-07-31"),
    ("magistral-small-2509", "Magistral Small 1.2", "2026-04-30", "2026-07-31"),
    ("magistral-small-2507", "Magistral Small 1.1", "2025-10-31", "2025-11-30"),
    ("devstral-medium-2507", "Devstral Medium 1.0", "2026-02-27", "2026-05-31"),
    ("devstral-small-2507", "Devstral Small 1.1", "2026-02-27", "2026-05-31"),
    ("magistral-medium-2506", "Magistral Medium 1.0", "2025-10-31", "2025-11-30"),
    ("magistral-small-2506", "Magistral Small 1.0", "2025-10-31", "2025-11-30"),
    ("devstral-small-2505", "Devstral Small 1.0", "2025-10-31", "2025-11-30"),
    ("mistral-medium-2505", "Mistral Medium 3", "2026-05-22", "2026-08-31"),
    ("mistral-small-2503", "Mistral Small 3.1", "2025-11-06", "2025-11-30"),
    ("mistral-saba-2502", "Mistral Saba", "2025-06-10", "2025-09-30"),
    ("mistral-small-2501", "Mistral Small 3.0", "2025-11-06", "2025-11-30"),
    ("codestral-2501", "Codestral", "2025-11-06", "2025-11-30"),
    ("mistral-large-2411", "Mistral Large 2.1", "2026-02-27", "2026-05-31"),
    ("pixtral-large-2411", "Pixtral Large", "2026-02-27", "2026-05-31"),
    ("ministral-3b-2410", "Ministral 3B", "2025-12-02", "2025-12-31"),
    ("ministral-8b-2410", "Ministral 8B", "2025-12-02", "2025-12-31"),
    ("mistral-small-2409", "Mistral Small 2.0", "2025-11-06", "2025-11-30"),
    ("pixtral-12b-2409", "Pixtral 12B", "2025-12-02", "2025-12-31"),
    ("mistral-large-2407", "Mistral Large 2.0", "2024-11-30", "2025-03-30"),
    ("open-mistral-nemo-2407", "Mistral Nemo 12B", "2026-05-22", "2026-07-31"),
    ("open-codestral-mamba", "Codestral Mamba 7B", "2025-06-06", "2025-06-06"),
    ("codestral-2405", "Codestral", "2024-12-02", "2025-06-16"),
    ("open-mistral-7b", "Mistral 7B", "2024-11-30", "2025-03-30"),
    ("mistral-small-2402", "Mistral Small 1.0", "2024-11-30", "2025-06-16"),
    ("mistral-large-2402", "Mistral Large 1.0", "2024-11-30", "2025-06-16"),
    ("mistral-medium-2312", "Mistral Medium 1.0", "2024-11-30", "2025-06-16"),
    ("open-mixtral-8x7b", "Mixtral 8x7B", "2024-11-30", "2025-03-30"),
]
# Current Mistral models: (api name from the detail page, display name, alias, detail page slug).
MISTRAL_CURRENT = [
    ("mistral-medium-3-5", "Mistral Medium 3.5", "mistral-medium-latest", "mistral-medium-3-5-26-04"),
    ("mistral-small-2603", "Mistral Small 4.0", "mistral-small-latest", "mistral-small-4-0-26-03"),
    ("mistral-large-2512", "Mistral Large 3", "mistral-large-latest", "mistral-large-3-25-12"),
    ("ministral-14b-2512", "Ministral 3 14B", "ministral-14b-latest", "ministral-3-14b-25-12"),
    ("ministral-8b-2512", "Ministral 3 8B", "ministral-8b-latest", "ministral-3-8b-25-12"),
    ("ministral-3b-2512", "Ministral 3 3B", "ministral-3b-latest", "ministral-3-3b-25-12"),
    ("codestral-2508", "Codestral 25.08", "codestral-latest", "codestral-25-08"),
]


def mistral_status(retirement: str) -> tuple[str, str]:
    check_day = RECHECKED[:10]
    if retirement < check_day:
        return "retired", f"Listed as retired on {retirement}."
    if retirement == check_day:
        return "unknown", f"Retirement is listed for {retirement}, the check date."
    return "available", f"Deprecated; the page lists retirement on {retirement}."


API_LISTINGS = {
    "OpenAI": [(i, "unknown", "Listed on OpenAI's all-models page; lifecycle status is not taken from that page.",
                OPENAI_ALL) for i in OPENAI_IN_SCOPE] +
              [("gpt-rosalind-research", "unknown", "Listed on the models overview; lifecycle status not stated.", None)],
    "Anthropic": [("claude-fable-5-1", "available", "Current model.", None),
                  ("claude-opus-5-5", "available", "Current model.", None),
                  ("claude-sonnet-5-5", "available", "Current model.", None),
                  ("claude-haiku-4-5-20251001", "available", "Current model; alias claude-haiku-4-5.", None)] +
                 [(i, "available", "Listed as a legacy model that is still available.", None)
                  for i in ("claude-fable-5", "claude-opus-5", "claude-opus-4-8", "claude-opus-4-7", "claude-opus-4-6",
                            "claude-sonnet-5", "claude-sonnet-4-6")] +
                 [("claude-opus-4-5-20251101", "available", "Legacy model still available (overview); alias "
                   "claude-opus-4-5. Dated ID from the model's own page.",
                   "https://platform.claude.com/docs/en/models/opus-4-5/overview"),
                  ("claude-sonnet-4-5-20250929", "available", "Legacy model still available (overview); alias "
                   "claude-sonnet-4-5. Dated ID from the model's own page.",
                   "https://platform.claude.com/docs/en/models/sonnet-4-5/overview")],
    "Google": [(i, "available", "Stable model.", None) for i in ("gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash",
                                                                 "gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite")] +
              [(i, "available", "Preview model.", None) for i in ("gemini-3.1-pro-preview", "gemini-3-flash-preview",
                                                                  "gemini-2.5-computer-use-preview-10-2025")] +
              [(i, "unknown", "Listed; status not stated on the overview.", None)
               for i in ("gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-lite")],
    "DeepSeek": [("deepseek-flash", "available", "Current model name.", None),
                 ("deepseek-v4-pro", "unknown", "Listed; status not stated.", None),
                 ("deepseek-v4-flash", "retired", "Legacy name still accepted, but the page says the model it named has been retired.", None)],
    "xAI": [(i, "unknown", "Listed model; lifecycle status not stated.", None)
            for i in ("grok-4.7", "grok-4.6", "grok-4.5", "grok-4.3", "grok-4.20-0309-reasoning",
                      "grok-4.20-0309-non-reasoning", "grok-build-0.1", "grok-4.20-multi-agent-0309")],
    "Mistral AI": [(api, "available", f"{name}; current model. Alias {alias}.", MISTRAL_DETAIL + slug)
                   for api, name, alias, slug in MISTRAL_CURRENT] +
                  [(api, *mistral_status(ret), None) for api, _name, _dep, ret in MISTRAL_TABLE],
    "Alibaba (Qwen)": [(i, "unknown", "Listed under text generation; status not stated.", None)
                       for i in ("qwen3.8-max", "qwen3.7-plus", "qwen3.8-flash")],
    "Moonshot AI": [(i, "unknown", "Listed chat model; status not stated.", None)
                    for i in ("kimi-k3", "kimi-k2.7-code", "kimi-k2.7-code-highspeed", "kimi-k2.6")],
    "Cohere": [(i, "available", "Listed as live.", None) for i in ("command-a-plus-05-2026", "command-a-03-2025", "command-r7b-12-2024",
                                                                  "command-a-translate-08-2025", "command-a-reasoning-08-2025",
                                                                  "command-a-vision-07-2025", "command-r-08-2024", "command-r-plus-08-2024",
                                                                  "north-mini-code-1-0", "c4ai-aya-expanse-32b", "c4ai-aya-vision-32b",
                                                                  "tiny-aya-global")] +
              [(i, "unknown", "Listed as deprecated since 15 September 2025; retirement not stated.", None)
               for i in ("command-r-03-2024", "command-r-plus-04-2024", "command-r-plus", "command-r", "command-light")],
}
# Family-level entries: the page names the model but gives no API identifier.
FAMILY_ENTRIES = [
    ("Meta", "direct_api", "Muse Spark", "Muse", "unknown"),
]
OPEN_WEIGHT_EXACT = [("OpenAI", i, OPENAI_ALL) for i in ("gpt-oss-120b", "gpt-oss-20b")]
LOCAL_ENTRIES = [
    ("Meta", "Llama 4 (open weights)", "Llama", "Open-weight model family; runs wherever it is deployed. "
     "Local and self-hosted runs have no approved evidence representation yet, so no measurements link here."),
]
APPS = [  # (maker, name, family, app url, source url, claim)
    ("OpenAI", "ChatGPT app", "ChatGPT", "https://chatgpt.com/", PAGES["OpenAI"], "OpenAI's API documentation links to chatgpt.com"),
    ("Anthropic", "Claude app", "Claude", "https://claude.ai/", PAGES["Anthropic"], "Anthropic's models overview links to claude.ai for chatting with Claude"),
    ("Google", "Gemini app", "Gemini", "https://gemini.google.com/", "https://gemini.google.com/", "The Gemini app loads at gemini.google.com"),
    ("DeepSeek", "DeepSeek chat app", "DeepSeek", "https://chat.deepseek.com/", "https://www.deepseek.com/", "DeepSeek's home page links to chat.deepseek.com"),
    ("xAI", "Grok app", "Grok", "https://grok.com/", PAGES["xAI"], "xAI's developer documentation links to grok.com"),
    ("Meta", "Meta AI app", "Meta AI", "https://www.meta.ai/", PAGES["Meta"], "Meta's developer documentation links to meta.ai"),
    ("Mistral AI", "Le Chat", "Le Chat", "https://chat.mistral.ai/", PAGES["Mistral AI"], "Mistral's documentation links to chat.mistral.ai"),
    ("Alibaba (Qwen)", "Qwen Chat", "Qwen", "https://chat.qwen.ai/", "https://chat.qwen.ai/", "Qwen Chat loads at chat.qwen.ai"),
    ("Moonshot AI", "Kimi app", "Kimi", "https://www.kimi.com/", PAGES["Moonshot AI"], "Moonshot's platform documentation links to kimi.com"),
]
FAMILY_PREFIXES = [("claude-fable", "Claude Fable"), ("claude-opus", "Claude Opus"), ("claude-sonnet", "Claude Sonnet"),
                   ("claude-haiku", "Claude Haiku"), ("claude", "Claude"), ("gpt-oss", "gpt-oss"), ("gpt", "GPT"),
                   ("chatgpt", "GPT"), ("o", "OpenAI o-series"), ("gemini", "Gemini"), ("gemma", "Gemma"),
                   ("deepseek", "DeepSeek"), ("grok", "Grok"), ("codestral", "Codestral"), ("open-codestral", "Codestral"),
                   ("mistral", "Mistral"), ("open-mistral", "Mistral"), ("magistral", "Magistral"), ("devstral", "Devstral"), ("pixtral", "Pixtral"), ("labs-", "Mistral Labs"), ("open-mixtral", "Mixtral"), ("ministral", "Ministral"),
                   ("qwen", "Qwen"), ("qwq", "Qwen"), ("kimi", "Kimi"), ("command", "Command"), ("north", "North"),
                   ("c4ai-aya", "Aya"), ("tiny-aya", "Aya"), ("llama", "Llama")]


def family_of(identifier: str) -> str:
    for prefix, family in FAMILY_PREFIXES:
        if identifier.startswith(prefix):
            return family
    return identifier


def slug(text: str) -> str:
    import re
    return re.sub(r"[^a-z0-9._-]+", "-", text.lower()).strip("-.")


def entry(**fields):
    base = {"route_ids": [], "notes": ""}
    base.update(fields)
    return base


def build(records: dict) -> dict:
    entries = []
    for maker, items in API_LISTINGS.items():
        for identifier, availability, note, page in items:
            url = page or PAGES[maker]
            checked = RECHECKED if (page or maker == "Mistral AI") else CHECKED
            entries.append(entry(
                id=f"{MAKER_KEYS[maker]}-api.{identifier}", name=identifier, maker=maker, family=family_of(identifier),
                identity_kind="exact", exact_identifier=identifier, service_provider=maker, access_kind="direct_api",
                availability=availability, sources=[{"url": url, "checked_at": checked,
                                                     "claim": f"'{identifier}' appears in the official model listing"}],
                notes=note))
    for maker, access, name, family, availability in FAMILY_ENTRIES:
        entries.append(entry(
            id=f"{MAKER_KEYS[maker]}-api.{slug(name)}", name=name, maker=maker, family=family, identity_kind="family",
            exact_identifier=None, service_provider=maker, access_kind=access, availability=availability,
            sources=[{"url": PAGES[maker], "checked_at": CHECKED, "claim": f"{name} is named in the official listing"}],
            notes="Named in the official listing; the exact API identifier was not verified, so this is a family-level entry."))
    for maker, identifier, page in OPEN_WEIGHT_EXACT:
        entries.append(entry(
            id=f"{MAKER_KEYS[maker]}-local.{identifier}", name=identifier, maker=maker, family=family_of(identifier),
            identity_kind="exact", exact_identifier=identifier, service_provider="Self-hosted", access_kind="local",
            availability="unknown", sources=[{"url": page, "checked_at": RECHECKED,
                                                "claim": f"'{identifier}' appears in the official model listing"}],
            notes="Open-weight model; runs wherever it is deployed. Hosted runs are separate entries."))
    for maker, name, family, note in LOCAL_ENTRIES:
        entries.append(entry(
            id=f"{MAKER_KEYS[maker]}-local.{slug(name)}", name=name, maker=maker, family=family, identity_kind="family",
            exact_identifier=None, service_provider="Self-hosted", access_kind="local", availability="available",
            sources=[{"url": LLAMA_CARDS, "checked_at": CHECKED, "claim": "Meta's Llama model cards describe Llama 4"}],
            notes=note))
    for maker, name, family, app_url, source_url, claim in APPS:
        entries.append(entry(
            id=f"{MAKER_KEYS[maker]}-app.{slug(family)}", name=name, maker=maker, family=family,
            identity_kind="automatic", exact_identifier=None, service_provider=maker, access_kind="consumer_app",
            availability="available", sources=[{"url": source_url, "checked_at": CHECKED, "claim": claim}],
            notes=f"Consumer app at {app_url}. The model behind a reply can change or be chosen automatically, so it is "
                  "not an exact model version. API measurements never count as app measurements."))

    by_key = {(e["maker"], e["exact_identifier"], e["access_kind"], e["service_provider"]): e for e in entries}
    models = {m["id"]: m for m in records["models"]}
    obs_by_series = {}
    for o in records["observations"]:
        obs_by_series.setdefault(o["series_id"], []).append(o)
    evidence_url = {s["route_id"]: obs_by_series[s["id"]][0]["evidence_url"]
                    for s in records["series"] if s["id"] in obs_by_series}
    for route in records["routes"]:
        model = models[route["model_id"]]
        maker = model["provider"]
        service = maker if route["access_type"] == "direct_api" else route["service"]
        key = (maker, model["exact_identifier"], route["access_type"], service)
        target = by_key.get(key)
        if target is None:
            target = entry(
                id=f"{MAKER_KEYS[maker]}-{'api' if route['access_type'] == 'direct_api' else slug(service)}.{slug(model['exact_identifier'])}",
                name=model["exact_identifier"], maker=maker, family=family_of(model["exact_identifier"]),
                identity_kind="exact", exact_identifier=model["exact_identifier"], service_provider=service,
                access_kind=route["access_type"], availability="unknown",
                sources=[{"url": evidence_url[route["id"]], "checked_at": CHECKED,
                          "claim": f"Aider polyglot run requested '{route['requested_model']}'"}],
                notes="Known from historical third-party evidence only. It is not in the maker's current listing "
                      "checked on this date, so current availability is unknown." + (
                          f" Hosted by {service}; made by {maker}." if route["access_type"] == "intermediary" else ""))
            entries.append(target)
            by_key[key] = target
        target["route_ids"].append(route["id"])
    for e in entries:
        e["route_ids"] = sorted(set(e["route_ids"]))
    entries.sort(key=lambda e: (e["name"].lower(), e["id"]))
    return {"schema_version": 1, "checked_at": CHECKED, "entries": entries}


if __name__ == "__main__":
    records, errors = registry.load_registry(ROOT / "registry")
    if errors:
        raise SystemExit("registry invalid: " + "; ".join(errors[:5]))
    document = build(records)
    (ROOT / "catalog" / "models.json").write_text(json.dumps(document, indent=1, ensure_ascii=False) + "\n",
                                                  encoding="utf-8", newline="\n")
    print(f"{len(document['entries'])} entries")
