/* Directory helpers: URL state, search, filters, sorting and evidence coverage.
   Pure functions (no DOM). Browser global BaselineDirectory; CommonJS for Node tests. */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.BaselineDirectory = factory();
})(this, function () {
  "use strict";
  var DAY_MS = 86400000;
  var VIEWS = ["models", "model", "sources", "about"];
  var FILTER_KEYS = ["q", "provider", "access", "evidence", "availability", "sort"];
  var ACCESS_LABELS = {
    consumer_app: "Consumer app", direct_api: "Direct API", intermediary: "Hosted by a third party",
    cloud_platform: "Cloud platform", local: "Open weights / local", unknown: "Unknown access"
  };

  function decode(text) {
    try { return decodeURIComponent(text); } catch (e) { return text; }
  }

  function emptyState() {
    return { view: "models", id: "", route: "", q: "", provider: "", access: "", evidence: "",
             availability: "", sort: "name", legacy: "" };
  }

  // "#models?q=..", "#model/<id>?route=..&q=..", "#sources", "#about", or a legacy
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
    if (!state.sort) state.sort = "name";
    if (path.indexOf("model/") === 0) {
      state.view = "model";
      state.id = decode(path.slice(6));
    } else if (path === "" || VIEWS.indexOf(path) !== -1) {
      state.view = path || "models";
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
      if (value && !(key === "sort" && value === "name")) params.set(key, value);
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
    var byName = function (a, b) { return fold(a.name) < fold(b.name) ? -1 : fold(a.name) > fold(b.name) ? 1 : 0; };
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
    } else {
      list.sort(byName);
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
           ACCESS_LABELS: ACCESS_LABELS, emptyState: emptyState };
});
