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
    return { view: "models", id: "", route: "", q: "", provider: "", access: "", evidence: "",
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
    FILTER_KEYS.concat(["route"]).forEach(function (key) {
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

  return { parseState: parseState, encodeState: encodeState, filterEntries: filterEntries,
           coverage: coverage, newestObservation: newestObservation, distinct: distinct,
           releaseDate: releaseDate, baselineStatus: baselineStatus, STATUS: STATUS, STALE_DAYS: STALE_DAYS,
           outcomeGroups: outcomeGroups,
           ACCESS_LABELS: ACCESS_LABELS, emptyState: emptyState, DEFAULT_SORT: DEFAULT_SORT };
});
