// Behavioural tests for site/directory.js (run by tests/test_directory.py).
"use strict";
const assert = require("node:assert/strict");
const D = require("../site/directory.js");

const NOW = Date.parse("2026-09-30T00:00:00Z");
const obs = (date) => ({ observed_at: date, retrieved_at: "2026-09-28T22:33:01Z" });
const entries = [
  { id: "openai-app.chatgpt", name: "ChatGPT app", maker: "OpenAI", family: "ChatGPT", exact_identifier: null,
    service_provider: "OpenAI", access_kind: "consumer_app", availability: "available", routes: [] },
  { id: "openai-api.gpt-5", name: "gpt-5", maker: "OpenAI", family: "GPT", exact_identifier: "gpt-5",
    service_provider: "OpenAI", access_kind: "direct_api", availability: "unknown",
    routes: [{ id: "openai-api.gpt-5.s1", observations: [obs("2025-08-23")] }] },
  { id: "xai-openrouter.grok-3-beta", name: "grok-3-beta", maker: "xAI", family: "Grok", exact_identifier: "grok-3-beta",
    service_provider: "OpenRouter", access_kind: "intermediary", availability: "unknown",
    routes: [{ id: "openrouter.x-ai.grok-3-beta", observations: [obs("2025-04-10")] }] },
  { id: "qwen-api.qwen3.8-max", name: "qwen3.8-max", maker: "Alibaba (Qwen)", family: "Qwen", exact_identifier: "qwen3.8-max",
    service_provider: "Alibaba (Qwen)", access_kind: "direct_api", availability: "available", routes: [] },
  { id: "fresh-api.x", name: "Fresh", maker: "Fixture", family: "F", exact_identifier: "x", service_provider: "Fixture",
    access_kind: "direct_api", availability: "available", routes: [{ id: "r", observations: [obs("2026-09-27")] }] },
];

// Unicode and URL round trips (plan Task 3).
const state = D.parseState("#models?q=Qwen%20%2B%20%E4%B8%AD&access=consumer_app");
assert.equal(state.q, "Qwen + 中");
assert.equal(state.access, "consumer_app");
assert.equal(D.parseState(D.encodeState(state)).q, state.q);
assert.doesNotThrow(() => D.parseState("#model/%E0%A4%A"));
assert.equal(D.parseState("#model/%E0%A4%A").view, "model");
assert.equal(D.filterEntries([], state).length, 0);
assert.equal(D.coverage({ routes: [] }, Date.now()).kind, "none");

// Views, deep links and legacy route links.
assert.equal(D.parseState("").view, "models");
assert.equal(D.parseState("#about").view, "how-we-test");        // first-release About links still open
assert.equal(D.parseState("#how-we-test").view, "how-we-test");
assert.equal(D.encodeState(D.parseState("#about")), "#how-we-test");
const detail = D.parseState("#model/openai-api.gpt-5?route=openai-api.gpt-5.s1&q=gpt&provider=OpenAI");
assert.deepEqual([detail.view, detail.id, detail.route, detail.q, detail.provider],
                 ["model", "openai-api.gpt-5", "openai-api.gpt-5.s1", "gpt", "OpenAI"]);
assert.equal(D.parseState(D.encodeState(detail)).route, "openai-api.gpt-5.s1");
const legacy = D.parseState("#deepseek-api.deepseek-chat");
assert.deepEqual([legacy.view, legacy.legacy], ["legacy", "deepseek-api.deepseek-chat"]);
assert.equal(D.encodeState(D.emptyState()), "#models");
assert.equal(D.parseState("#models?q=%ZZ&sort=date").sort, "date"); // malformed escape tolerated

// Search: case, accents and multiple terms.
assert.deepEqual(D.filterEntries(entries, { q: "GROK 3" }, NOW).map((e) => e.id), ["xai-openrouter.grok-3-beta"]);
assert.equal(D.filterEntries(entries, { q: "openrouter" }, NOW).length, 1); // service is searchable
assert.equal(D.filterEntries(entries, { q: "ｑｗｅｎ" }, NOW).length, 1); // NFKC folding

// Maker vs service: the provider filter is the maker; a host never counts as the maker.
assert.deepEqual(D.filterEntries(entries, { provider: "xAI" }, NOW).map((e) => e.id), ["xai-openrouter.grok-3-beta"]);
assert.equal(D.filterEntries(entries, { provider: "OpenRouter" }, NOW).length, 0);

// Apps and APIs stay separate.
assert.deepEqual(D.filterEntries(entries, { access: "consumer_app" }, NOW).map((e) => e.id), ["openai-app.chatgpt"]);
assert.ok(D.filterEntries(entries, { access: "direct_api" }, NOW).every((e) => e.access_kind === "direct_api"));

// Availability and evidence filters.
assert.equal(D.filterEntries(entries, { availability: "unknown" }, NOW).length, 2);
assert.deepEqual(D.filterEntries(entries, { evidence: "none" }, NOW).map((e) => e.id).sort(),
                 ["openai-app.chatgpt", "qwen-api.qwen3.8-max"]);
assert.equal(D.filterEntries(entries, { evidence: "measured" }, NOW).length, 3);

// Coverage uses the measurement date, not the recent retrieval date.
const old = D.coverage(entries[1], NOW);
assert.equal(old.kind, "historical");
assert.equal(old.newest, "2025-08-23");
assert.equal(D.coverage(entries[4], NOW).kind, "recent");
assert.equal(D.coverage(entries[0], NOW).label, "No measurements");

// Sorting: alphabetical default, provider, and date with unmeasured entries last.
assert.deepEqual(D.filterEntries(entries, {}, NOW).map((e) => e.name),
                 ["ChatGPT app", "Fresh", "gpt-5", "grok-3-beta", "qwen3.8-max"]);
const byDate = D.filterEntries(entries, { sort: "date" }, NOW).map((e) => e.id);
assert.deepEqual(byDate.slice(0, 3), ["fresh-api.x", "openai-api.gpt-5", "xai-openrouter.grok-3-beta"]);
assert.deepEqual(byDate.slice(3).sort(), ["openai-app.chatgpt", "qwen-api.qwen3.8-max"]);
assert.equal(D.filterEntries(entries, { sort: "provider" }, NOW)[0].maker, "Alibaba (Qwen)");
assert.deepEqual(D.distinct(entries, "maker"), ["Alibaba (Qwen)", "Fixture", "OpenAI", "xAI"]);

// Newest cited release first (T08): unknown dates last, deterministic ties by name then id,
// month-precision dates never invented into days, and no date taken from the name.
const rel = (date, precision) => ({ date: date, precision: precision || "day",
  source: { url: "https://example.test/", checked_at: "2026-09-30T00:00:00Z", claim: "fixture" } });
const released = [
  { id: "b", name: "Beta 2512", maker: "M", access_kind: "direct_api", routes: [] },              // name looks dated; no citation
  { id: "a2", name: "Same", maker: "M", access_kind: "direct_api", release: rel("2026-09-01"), routes: [] },
  { id: "a1", name: "Same", maker: "M", access_kind: "direct_api", release: rel("2026-09-01"), routes: [] },
  { id: "c", name: "Old", maker: "M", access_kind: "direct_api", release: rel("2024-05-29"), routes: [] },
  { id: "d", name: "Month", maker: "M", access_kind: "direct_api", release: rel("2025-07", "month"), routes: [] },
  { id: "e", name: "Alpha", maker: "M", access_kind: "direct_api", routes: [] },
];
assert.equal(D.DEFAULT_SORT, "release");
assert.deepEqual(D.filterEntries(released, D.parseState("#models"), NOW).map((e) => e.id), ["a1", "a2", "d", "c", "e", "b"]);
assert.deepEqual(D.filterEntries(released, { sort: "release" }, NOW).map((e) => e.id),
                 D.filterEntries(released.slice().reverse(), { sort: "release" }, NOW).map((e) => e.id));
assert.equal(D.releaseDate(released[0]), null);
assert.equal(D.releaseDate(released[4]), "2025-07");
assert.deepEqual(D.filterEntries(released, D.parseState("#models?sort=name"), NOW).map((e) => e.id).slice(0, 2), ["e", "b"]);
assert.equal(D.encodeState(D.parseState("#models?sort=name")), "#models?sort=name");   // old default stays explicit
assert.equal(D.encodeState(D.parseState("#models?sort=release")), "#models");

// Baseline status boundary (T08). Only labelled fixtures reach the non-default states; the
// published bundle is refused if it holds any Baseline results (scripts/release_check.py).
const FIXTURE = "FIXTURE-NOT-FOR-PUBLICATION";
const one = { id: "x" };
const status = (rec) => D.baselineStatus(one, { runs: rec ? rec.runs : 0, label: FIXTURE, entries: rec ? { x: rec } : {} });
assert.equal(D.baselineStatus(one, undefined).label, "Not tested by Baseline");
assert.equal(D.baselineStatus(one, { runs: 0, entries: {} }).key, "not_tested");
assert.equal(status({ runs: 0, analysis: { reviewed: true, verdict: "lower" } }).key, "not_tested"); // zero runs never judged
assert.equal(status({ runs: 3, latest_run: "2026-09-29" }).label, "Collecting baseline");
assert.equal(status({ runs: 3, latest_run: "2026-09-29" }).latest, "2026-09-29");
assert.equal(status({ runs: 30, baseline_complete: true }).label, "Not enough evidence to judge a change");
assert.equal(status({ runs: 30, baseline_complete: true, analysis: { reviewed: false, verdict: "lower" } }).key, "insufficient");
assert.equal(status({ runs: 30, baseline_complete: true, analysis: { verdict: "higher" } }).key, "insufficient");
assert.equal(status({ runs: 30, baseline_complete: true, analysis: { reviewed: true, verdict: "lower" } }).label, "Lower on our tests");
assert.equal(status({ runs: 30, baseline_complete: true, analysis: { reviewed: true, verdict: "higher" } }).label, "Higher on our tests");
assert.equal(status({ runs: 30, baseline_complete: true, analysis: { reviewed: true, verdict: "no_change" } }).label, "No meaningful change detected");
assert.equal(status({ runs: 30, baseline_complete: true, analysis: { reviewed: true, verdict: "0% change" } }).key, "insufficient");
assert.equal(status({ runs: 30, latest_attempt: "failed", analysis: { reviewed: true, verdict: "lower" } }).label, "Test unavailable");
assert.deepEqual(Object.keys(D.STATUS).sort(), ["collecting", "higher", "insufficient", "lower", "no_change", "not_tested", "unavailable"]);

process.stdout.write("directory.js: all assertions passed\n");
