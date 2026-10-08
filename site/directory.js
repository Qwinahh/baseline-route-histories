/* Directory helpers: URL state, search, filters, sorting, evidence coverage and the
   Baseline test status.
   Pure functions (no DOM). Browser global BaselineDirectory; CommonJS for Node tests. */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.BaselineDirectory = factory();
})(this, function () {
  "use strict";
  var DAY_MS = 86400000;
  var VIEWS = ["models", "model", "sources", "how-we-test"];
  var ALIASES = { about: "how-we-test" };     // first-release "About" links keep working
  var DEFAULT_SORT = "release";
  var FILTER_KEYS = ["q", "provider", "access", "evidence", "availability", "sort"];
  var ACCESS_LABELS = {
    consumer_app: "App", direct_api: "API", intermediary: "Third-party host",
    cloud_platform: "Cloud platform", local: "Open weights", unknown: "Unknown access"
  };

  function decode(text) {
    try { return decodeURIComponent(text); } catch (e) { return text; }
  }

  function emptyState() {
    return { view: "models", id: "", route: "", service: "", setup: "", q: "", provider: "", access: "", evidence: "",
             availability: "", sort: DEFAULT_SORT, legacy: "" };
  }

  // "#models?q=..", "#model/<id>?route=..&q=..", "#sources", "#how-we-test" (or the old
  // "#about"), or a legacy
  // "#<route id>" from the first release. Never throws on malformed input.
  function parseState(hash) {
    var state = emptyState();
    var text = String(hash || "").replace(/^#/, "");
    var qIndex = text.indexOf("?");
    var path = qIndex === -1 ? text : text.slice(0, qIndex);
    var query = qIndex === -1 ? "" : text.slice(qIndex + 1);
    var params;
    try { params = new URLSearchParams(query); } catch (e) { params = new URLSearchParams(""); }
    FILTER_KEYS.concat(["route", "service", "setup"]).forEach(function (key) {
      var value;
      try { value = params.get(key); } catch (e) { value = null; }
      if (value !== null) state[key] = value.normalize ? value.normalize("NFC") : value;
    });
    if (!state.sort) state.sort = DEFAULT_SORT;
    if (path.indexOf("model/") === 0) {
      state.view = "model";
      state.id = decode(path.slice(6));
    } else if (path === "" || VIEWS.indexOf(path) !== -1 || ALIASES[path]) {
      state.view = ALIASES[path] || path || "models";
    } else {
      state.view = "legacy";          // resolved by the app against route ids
      state.legacy = decode(path);
    }
    return state;
  }

  function encodeState(state) {
    var params = new URLSearchParams();
    if (state.view === "model" && state.route) params.set("route", state.route);
    if (state.view === "model" && state.service) params.set("service", state.service);
    if (state.view === "model" && state.setup) params.set("setup", state.setup);     // one daily test setup
    FILTER_KEYS.forEach(function (key) {
      var value = state[key];
      if (value && !(key === "sort" && value === DEFAULT_SORT)) params.set(key, value);
    });
    var query = params.toString();
    var path = state.view === "model" ? "model/" + encodeURIComponent(state.id || "")
      : (VIEWS.indexOf(state.view) !== -1 ? state.view : "models");
    return "#" + path + (query ? "?" + query : "");
  }

  function fold(text) {
    return String(text || "").normalize("NFKC").toLowerCase();
  }

  function newestObservation(entry) {
    var newest = null;
    (entry.routes || []).forEach(function (route) {
      (route.observations || []).forEach(function (o) {
        if (newest === null || o.observed_at > newest) newest = o.observed_at;
      });
    });
    return newest;
  }

  // Evidence coverage from the source's measurement dates (never from when Baseline
  // fetched them). kind: none | recent | aging | historical.
  function coverage(entry, nowMs) {
    var count = 0;
    (entry.routes || []).forEach(function (r) { count += (r.observations || []).length; });
    var newest = newestObservation(entry);
    if (!count || !newest) return { kind: "none", label: "No measurements", count: 0, newest: null };
    var days = Math.floor((nowMs - Date.parse(newest.slice(0, 10) + "T00:00:00Z")) / DAY_MS);
    var kind = days <= 7 ? "recent" : days <= 30 ? "aging" : "historical";
    var label = kind === "historical" ? "Historical evidence only" : kind === "aging" ? "Measurements aging" : "Recent measurements";
    return { kind: kind, label: label, count: count, newest: newest, ageDays: days };
  }

  // Cited release date ("YYYY-MM-DD" or "YYYY-MM"), or null when unknown. Never inferred.
  function releaseDate(entry) {
    return entry.release && entry.release.date ? entry.release.date : null;
  }

  // Baseline's own test status: the one derivation used by the directory and the model
  // page (T12). `tests` is the bundle's baseline_tests record. With no Baseline results
  // for an entry the answer is "Not tested by Baseline". A one-off setup test is never
  // daily evidence. A failed or missing latest scheduled day, or no usable daily result
  // in the last STALE_DAYS days, is never shown as current monitoring. Change wording
  // needs a reviewed analysis; anything else stays in a non-judging state.
  var STALE_DAYS = 2;
  var STATUS = {
    not_tested: "Not tested by Baseline", calibration: "One-off setup test", collecting: "Collecting baseline",
    stale: "No recent test", insufficient: "Not enough evidence to judge a change", lower: "Lower on our tests",
    higher: "Higher on our tests", no_change: "No meaningful change detected", unavailable: "Test unavailable"
  };
  var JUDGED = ["insufficient", "lower", "higher", "no_change"];
  function baselineStatus(entry, tests, nowMs) {
    var rec = tests && tests.entries ? tests.entries[entry.id] : null;
    var runs = rec && typeof rec.runs === "number" ? rec.runs : 0;
    var latest = rec && rec.latest_run ? rec.latest_run : null;
    var setups = rec && Array.isArray(rec.calibration) ? rec.calibration : [];
    var calibration = setups.length ? setups[setups.length - 1] : null;
    var key;
    if (!rec) key = "not_tested";
    else if (rec.latest_attempt === "failed") key = "unavailable";
    else if (!runs) key = calibration ? "calibration" : "not_tested";
    else if (nowMs !== undefined && (!latest || ageDays(latest, nowMs) > STALE_DAYS)) key = "stale";
    else if (rec.analysis && rec.analysis.reviewed === true && JUDGED.indexOf(rec.analysis.verdict) !== -1) key = rec.analysis.verdict;
    else key = rec.baseline_complete === true ? "insufficient" : "collecting";
    return { key: key, label: STATUS[key], runs: runs, latest: latest, calibration: calibration };
  }
  function ageDays(day, nowMs) {
    return Math.floor((nowMs - Date.parse(String(day).slice(0, 10) + "T00:00:00Z")) / DAY_MS);
  }

  // First-attempt outcome counts grouped for display. Every scheduled item lands in exactly
  // one group, so the groups always add up to the scheduled count.
  var ANSWER_PROBLEMS = ["truncated", "empty", "malformed", "answered_identity_mismatch", "answered_identity_unknown"];
  var REQUEST_ERRORS = ["timeout", "provider_error", "rate_limited", "auth_error", "client_error"];
  function outcomeGroups(outcomes) {
    var o = outcomes || {};
    var sum = function (keys) { return keys.reduce(function (n, k) { return n + (o[k] || 0); }, 0); };
    return { correct: o.correct || 0, incorrect: o.incorrect || 0, format_error: o.format_error || 0,
             refusal: o.refusal || 0, answer_problems: sum(ANSWER_PROBLEMS), request_errors: sum(REQUEST_ERRORS),
             not_sent: o.not_sent || 0 };
  }

  // What evidence an entry has (T14): Baseline's own results, a Baseline schedule still waiting
  // for its first result, other published tests only, or nothing. Never a quality label.
  var EVIDENCE_KINDS = {
    ours: "Tested by Baseline", scheduled: "Baseline test scheduled, no result yet",
    external: "Other published tests only", none: "Catalogue listing only"
  };
  // The newest published daily result of an entry across all of its setups, or null. A result is a graph
  // point (a complete zero counts; a gap, unavailable, partial or open day does not). It names its own
  // setup: an older setup's result is never relabelled with a newer setup that has none yet.
  function latestDailyResult(rec) {
    var best = null;
    ((rec && rec.daily_series) || []).forEach(function (series) {
      (series.rows || []).forEach(function (row) {
        if (row.eligible && (!best || row.date > best.date)) best = { series: series, date: row.date };
      });
    });
    return best;
  }
  function evidenceKind(entry, tests, nowMs) {
    var rec = tests && tests.entries ? tests.entries[entry.id] : null;
    var key;
    if (rec && ((rec.runs || 0) > 0 || latestDailyResult(rec) || (rec.calibration || []).length)) key = "ours";
    else if (rec && (rec.daily_series || []).length) key = "scheduled";
    else key = coverage(entry, nowMs === undefined ? Date.now() : nowMs).kind !== "none" ? "external" : "none";
    return { key: key, label: EVIDENCE_KINDS[key] };
  }

  // The newest cited releases across every maker (T14), in the directory's own release order
  // (T08): dated entries only, never grouped by provider.
  function newReleases(entries, count) {
    var state = emptyState();
    return filterEntries(entries, state).filter(function (e) { return releaseDate(e) !== null; }).slice(0, count);
  }

  function matches(entry, q) {
    if (!q) return true;
    var haystack = fold([entry.name, entry.id, entry.exact_identifier, entry.family, entry.maker,
                         entry.service_provider].join(" "));
    return fold(q).split(/\s+/).filter(Boolean).every(function (term) { return haystack.indexOf(term) !== -1; });
  }

  function filterEntries(entries, state, nowMs) {
    var now = nowMs === undefined ? Date.now() : nowMs;
    var list = (entries || []).filter(function (e) {
      if (!matches(e, state.q)) return false;
      if (state.provider && e.maker !== state.provider) return false;
      if (state.access && e.access_kind !== state.access) return false;
      if (state.availability && e.availability !== state.availability) return false;
      if (state.evidence) {
        var kind = coverage(e, now).kind;
        if (state.evidence === "measured" && kind === "none") return false;
        if (state.evidence === "none" && kind !== "none") return false;
      }
      return true;
    });
    var byName = function (a, b) {
      var x = fold(a.name), y = fold(b.name);
      return x < y ? -1 : x > y ? 1 : a.id < b.id ? -1 : a.id > b.id ? 1 : 0;
    };
    if (state.sort === "provider") {
      list.sort(function (a, b) { return fold(a.maker) < fold(b.maker) ? -1 : fold(a.maker) > fold(b.maker) ? 1 : byName(a, b); });
    } else if (state.sort === "date") {
      list.sort(function (a, b) {
        var x = newestObservation(a), y = newestObservation(b);
        if (x === y) return byName(a, b);
        if (x === null) return 1;           // unmeasured entries last
        if (y === null) return -1;
        return x < y ? 1 : -1;              // newest first
      });
    } else if (state.sort === "name") {
      list.sort(byName);
    } else {                                // newest cited release first; unknown dates last
      list.sort(function (a, b) {
        var x = releaseDate(a), y = releaseDate(b);
        if (x === y) return byName(a, b);
        if (x === null) return 1;
        if (y === null) return -1;
        return x < y ? 1 : -1;
      });
    }
    return list;
  }

  function distinct(entries, key) {
    var seen = {};
    (entries || []).forEach(function (e) { if (e[key]) seen[e[key]] = true; });
    return Object.keys(seen).sort(function (a, b) { return fold(a) < fold(b) ? -1 : 1; });
  }

  function modelKey(e) {
    if (e.identity_kind !== "exact" || !e.exact_identifier || e.access_kind === "consumer_app") return "entry:" + e.id;
    // Explicit catalogue alias only. Do not strip arbitrary host prefixes or version suffixes.
    var id = e.id === "puter.x-ai-grok-4.7" && e.exact_identifier === "x-ai/grok-4.7" ? "grok-4.7" : e.exact_identifier;
    return JSON.stringify([e.maker, id]);
  }
  function preferredRoute(members, tests) {
    function rank(e) {
      var r = tests && tests.entries && tests.entries[e.id];
      if (r && r.runs > 0) return 4;
      if (r && (r.calibration || []).length) return 3;
      if (r && (r.daily_series || []).length) return 2;
      return newestObservation(e) ? 1 : 0;
    }
    return members.slice().sort(function (a, b) {
      var difference = rank(b) - rank(a);
      if (difference) return difference;
      if (a.access_kind === "direct_api" && b.access_kind !== "direct_api") return -1;
      if (b.access_kind === "direct_api" && a.access_kind !== "direct_api") return 1;
      return a.id.localeCompare(b.id);
    })[0];
  }
  function modelGroups(entries, tests) {
    var groups = new Map();
    entries.forEach(function (e) {
      var key = modelKey(e);
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(e);
    });
    return Array.from(groups.values()).map(function (members) {
      var canonical = members.filter(function (e) { return e.access_kind === "direct_api"; })
        .sort(function (a, b) { return a.id.localeCompare(b.id); })[0] || members[0];
      return { id: canonical.id, canonical: canonical, members: members, preferred: preferredRoute(members, tests) };
    });
  }
  function groupedEntries(entries, tests, state, nowMs) {
    var matched = new Set(filterEntries(entries, state, nowMs).map(function (e) { return e.id; }));
    var list = modelGroups(entries, tests).map(function (group) {
      var members = group.members.filter(function (e) { return matched.has(e.id); });
      if (!members.length) return null;
      var selected = preferredRoute(members, tests);
      // Display metadata only: all evidence remains attached to selected.id.
      return Object.assign({}, selected, { name: group.canonical.name.replace(/ via Puter$/, ""),
        release: group.canonical.release || selected.release, model_group: group });
    }).filter(Boolean);
    return filterEntries(list, Object.assign(emptyState(), { sort: state.sort }), nowMs);
  }

  return { parseState: parseState, encodeState: encodeState, filterEntries: filterEntries,
           coverage: coverage, newestObservation: newestObservation, distinct: distinct,
           releaseDate: releaseDate, baselineStatus: baselineStatus, STATUS: STATUS, STALE_DAYS: STALE_DAYS,
           outcomeGroups: outcomeGroups, evidenceKind: evidenceKind, EVIDENCE_KINDS: EVIDENCE_KINDS,
           latestDailyResult: latestDailyResult,
           newReleases: newReleases, modelGroups: modelGroups, groupedEntries: groupedEntries,
           ACCESS_LABELS: ACCESS_LABELS, emptyState: emptyState, DEFAULT_SORT: DEFAULT_SORT };
});
