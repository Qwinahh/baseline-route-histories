// Behavioural tests for site/directory.js (run by tests/test_directory.py).
"use strict";
const assert = require("node:assert/strict");
const D = require("../site/directory.js");

// Routes for the same exact requested model are navigation choices, never merged data.
const api = {id:"api.test", name:"Test 1", maker:"Maker", identity_kind:"exact", exact_identifier:"test-1", access_kind:"direct_api", service_provider:"Maker", routes:[], release:{date:"2026-09-01"}};
const host = {...api, id:"host.test", name:"Test 1 via Puter", access_kind:"intermediary", service_provider:"Puter", release:null};
const otherVersion = {...api, id:"api.test2", exact_identifier:"test-2"};
const appEntry = {...api, id:"app.test", access_kind:"consumer_app"};
const hostTests = {entries:{"host.test":{runs:1,latest_run:"2026-10-07",daily_series:[{}]}}};
const grouped = D.modelGroups([host, api, otherVersion, appEntry], hostTests);
assert.equal(grouped.length, 3);
const testGroup = grouped.find(g=>g.id === api.id);
assert.equal(testGroup.preferred.id, host.id);
assert.equal(testGroup.members.length, 2);
assert.equal(D.groupedEntries([host,api],hostTests,D.emptyState())[0].id,host.id);
assert.equal(D.groupedEntries([host,api],hostTests,{...D.emptyState(),access:"direct_api"})[0].id,api.id);
assert.equal(D.groupedEntries([host,api],hostTests,{...D.emptyState(),q:"Puter"}).length,1);
assert.equal(D.groupedEntries([host,api],hostTests,D.emptyState())[0].release.date,"2026-09-01");
assert.equal(D.parseState(D.encodeState({...D.emptyState(),view:"model",id:api.id,service:api.id})).service,api.id);
assert.equal(host.release,null); // grouping does not rewrite source records
assert.equal(D.modelGroups([api,{...api,id:"other-maker",maker:"Other"}],hostTests).length,2);
assert.equal(D.modelGroups([{...api,identity_kind:"family"},{...host,identity_kind:"family"}],hostTests).length,2);

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
assert.deepEqual(Object.keys(D.STATUS).sort(), ["calibration", "collecting", "higher", "insufficient", "lower", "no_change",
                                              "not_tested", "stale", "unavailable"]);

// T12: one derivation for the directory and the model page. A setup test is never daily
// evidence; a failed latest day or an old newest result is never current monitoring.
const at = (day) => Date.parse(day + "T12:00:00Z");
const setup = { kind: "calibration", date: "2026-09-18", evidence: "verified", first_attempt_correct: 31, scheduled_items: 40 };
const tests = (rec) => ({ runs: rec.runs, entries: { x: rec } });
const calOnly = { runs: 0, latest_run: null, latest_attempt: null, daily: null, calibration: [setup] };
assert.equal(D.baselineStatus(one, tests(calOnly), at("2026-12-01")).key, "calibration");     // no staleness for a one-off
assert.equal(D.baselineStatus(one, tests(calOnly), at("2026-12-01")).label, "One-off setup test");
assert.equal(D.baselineStatus(one, tests(calOnly)).calibration, setup);
assert.equal(D.baselineStatus(one, tests({ runs: 0, latest_attempt: null, calibration: [] })).key, "not_tested");
const daily = { runs: 4, latest_run: "2026-09-27", latest_attempt: "ok", calibration: [setup], daily: {} };
assert.equal(D.baselineStatus(one, tests(daily), at("2026-09-27")).key, "collecting");
assert.equal(D.baselineStatus(one, tests(daily), at("2026-09-29")).key, "collecting");          // two days: still current
assert.equal(D.baselineStatus(one, tests(daily), at("2026-09-30")).key, "stale");
assert.equal(D.baselineStatus(one, tests(daily), at("2026-09-30")).label, "No recent test");
assert.equal(D.baselineStatus(one, tests(Object.assign({}, daily, { latest_attempt: "failed" })), at("2026-09-27")).key, "unavailable");
assert.equal(D.baselineStatus(one, tests({ runs: 0, latest_attempt: "failed", calibration: [setup] })).key, "unavailable");
assert.equal(D.baselineStatus(one, tests(Object.assign({}, daily, { baseline_complete: true,
  analysis: { reviewed: true, verdict: "lower" } })), at("2026-10-15")).key, "stale");      // an old verdict is not current
assert.equal(D.STALE_DAYS, 2);
const groups = D.outcomeGroups({ correct: 30, incorrect: 2, format_error: 1, refusal: 1, truncated: 1, empty: 1,
                                 answered_identity_unknown: 1, timeout: 1, rate_limited: 1, not_sent: 1 });
assert.deepEqual(groups, { correct: 30, incorrect: 2, format_error: 1, refusal: 1, answer_problems: 3, request_errors: 2, not_sent: 1 });
assert.equal(Object.values(groups).reduce((a, b) => a + b, 0), 40);

// T14: evidence kinds and the global new-releases list.
const ev = (rec, entry) => D.evidenceKind(entry || { id: "x", routes: [] }, { entries: rec ? { x: rec } : {} }, NOW).key;
assert.equal(ev(null), "none");
assert.equal(ev(null, { id: "x", routes: [{ observations: [obs("2026-09-01")] }] }), "external");
assert.equal(ev({ runs: 0, calibration: [{}], daily_series: [] }), "ours");                 // a setup test counts
assert.equal(ev({ runs: 3, calibration: [], daily_series: [{}] }), "ours");
assert.equal(ev({ runs: 0, calibration: [], daily_series: [{ rows: [] }] }), "scheduled");  // schedule only: not tested
assert.equal(D.EVIDENCE_KINDS.none, "Catalogue listing only");
const dated = [
  { id: "a", name: "Alpha", maker: "M1", release: { date: "2026-09-03" }, routes: [] },
  { id: "b", name: "Beta", maker: "M2", release: { date: "2026-09-29" }, routes: [] },
  { id: "c", name: "Gamma", maker: "M1", routes: [] },
  { id: "d", name: "Delta", maker: "M3", release: { date: "2026-09" }, routes: [] },
  { id: "e", name: "Epsilon", maker: "M2", release: { date: "2026-09-22" }, routes: [] },
];
assert.deepEqual(D.newReleases(dated, 3).map((e) => e.id), ["b", "e", "a"]);              // global, not by maker
assert.deepEqual(D.newReleases(dated, 10).map((e) => e.id), ["b", "e", "a", "d"]);       // undated never listed

process.stdout.write("directory.js: all assertions passed\n");
