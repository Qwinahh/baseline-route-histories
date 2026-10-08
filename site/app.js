/* Baseline: model directory, model detail, sources and "How we test" views (T07, T08).
   Renders window.BASELINE_DATA. All text goes through textContent. Ages, badges and the
   chart's "no recorded evidence" band are recomputed from the viewer's clock every minute.
   URL state lives in the hash (site/directory.js), so back/forward and shared links work. */
(function () {
  "use strict";
  var D = window.BASELINE_DATA;
  var F = window.BaselineFreshness;
  var Dir = window.BaselineDirectory;
  var Chart = window.BaselineResultsChart;
  var app = document.getElementById("app");
  var SVGNS = "http://www.w3.org/2000/svg";
  var REPO = "https://github.com/Qwinahh/baseline-route-histories/blob/main/";
  var SOURCE_LABELS = { "aider-polyglot": "Aider coding results" };
  // Directory note for the selected order (T08 review: never claim the default order after a change).
  var SORT_NOTES = {
    release: "Sorted by newest release; entries without a verified release date are listed last.",
    name: "Sorted by name (A–Z).",
    provider: "Sorted by provider, then name.",
    date: "Sorted by latest published test; entries without one are listed last."
  };
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  // Age wording follows the newest measurement date (never Baseline's retrieval time).
  var AGE_NOTE = {
    recent: "The newest measurement is from the last " + F.RECENT_DAYS + " days.",
    aging: "The newest measurement is " + F.RECENT_DAYS + " to " + F.AGING_DAYS + " days old.",
    stale: "The newest measurement is more than " + F.AGING_DAYS + " days old.",
    unknown: "The measurement age is unknown."
  };
  var ASCII = [
    "          .",
    "      .   :   .",
    "    . : . + . : .",
    "  . : + * o * + : .",
    "    . : . + . : .",
    "      .   :   .",
    "          ."
  ].join("\n");

  if (!D || !F || !Dir || !Chart) {
    app.appendChild(el("p", { class: "notice" }, "The page data could not be loaded. Reload the page to try again."));
    return;
  }

  // ------------------------------------------------------------------ helpers
  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) { node.setAttribute(k, attrs[k]); });
    append(node, children);
    return node;
  }
  function append(node, children) {
    [].concat(children === undefined ? [] : children).forEach(function (c) {
      if (c === null || c === undefined || c === false) return;
      if (Array.isArray(c)) { append(node, c); return; }
      node.appendChild(typeof c === "string" || typeof c === "number" ? document.createTextNode(String(c)) : c);
    });
    return node;
  }
  function s(tag, attrs, text) {
    var node = document.createElementNS(SVGNS, tag);
    Object.keys(attrs || {}).forEach(function (k) { node.setAttribute(k, attrs[k]); });
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function link(href, text) {
    var external = /^https:\/\//.test(href);
    return el("a", external ? { href: href, rel: "noopener noreferrer" } : { href: href }, text);
  }
  function pct(m) { return (100 * m.numerator / m.denominator).toFixed(1) + "%"; }
  function utc(value) { return value.replace("T", " ").replace("Z", " UTC"); }
  function dateText(o) { return o.precision === "day" ? o.observed_at + " (date only)" : utc(o.observed_at); }
  function fmt(v) { return v === null || v === undefined ? "not stated" : typeof v === "object" ? JSON.stringify(v) : String(v); }
  function liveAge(value) { return el("span", { "data-age": value, class: "live" }, F.describeAge(value, Date.now())); }
  function liveStatus(value) {
    var st = F.measurementStatus(value, Date.now());
    return el("span", { class: "badge", "data-status-of": value, "data-status": st.key }, st.label);
  }
  // "22 Sep 2026" (day precision) or "Sep 2026" (month precision), from the cited date only.
  function dayText(date) {
    var parts = String(date).slice(0, 10).split("-");
    var month = MONTHS[Number(parts[1]) - 1] + " " + parts[0];
    return parts.length === 3 ? Number(parts[2]) + " " + month : month;
  }
  function releaseText(release) {
    return dayText(release.date);   // "YYYY-MM-DD" or "YYYY-MM", as validated
  }
  function settingsText(settings) {
    var keys = Object.keys(settings || {});
    return keys.length ? keys.map(function (k) { return k.replace("_", " ") + " " + settings[k]; }).join(", ") : "default settings";
  }

  // ------------------------------------------------------------------ data
  var routeById = {};
  D.routes.forEach(function (r) { routeById[r.id] = r; });
  var sourceById = {};
  D.sources.forEach(function (x) { sourceById[x.id] = x; });
  var entries = D.catalog.map(function (e) {
    var copy = {};
    Object.keys(e).forEach(function (k) { copy[k] = e[k]; });
    copy.routes = e.route_ids.map(function (id) { return routeById[id]; }).filter(Boolean);
    return copy;
  });
  var entryById = {};
  entries.forEach(function (e) { entryById[e.id] = e; });
  var makers = Dir.distinct(entries, "maker");
  var measured = entries.filter(function (e) { return e.routes.length; });
  // Baseline's own tests (T12): admitted daily results and one-off setup tests, kept apart.
  // No entry record means "Not tested by Baseline".
  var TESTS = D.baseline_tests || { runs: 0, calibration_runs: 0, entries: {}, methods: [] };
  var METHODS = TESTS.methods || [];
  var modelGroups = Dir.modelGroups(entries, TESTS);
  var groupByEntry = {};
  modelGroups.forEach(function (g) { g.members.forEach(function (e) { groupByEntry[e.id] = g; }); });
  function displayEntry(e) {
    var g = groupByEntry[e.id];
    return Object.assign({}, g.preferred, { name: g.canonical.name.replace(/ via Puter$/, ""),
      release: g.canonical.release || g.preferred.release, model_group: g });
  }
  function ownStatus(e) { return Dir.baselineStatus(e, TESTS, Date.now()); }
  // Data-derived coverage (8 October 2026): the exact models with at least one published Baseline daily
  // result in any of their daily setups, computed from the admitted results and never from an editorial
  // list. A catalogue-only, scheduled-only, calibration-only or third-party-measured entry is not counted;
  // each result stays on its own route and setup (review R1: a new empty setup never hides older results).
  function latestResult(e) { return Dir.latestDailyResult(TESTS.entries[e.id]); }
  function hasDailyResult(e) { return latestResult(e) !== null; }
  var testedGroups = modelGroups.filter(function (g) { return g.members.some(hasDailyResult); })
    .sort(function (a, b) { return displayEntry(a.preferred).name.localeCompare(displayEntry(b.preferred).name); });
  var lastRuns = {};
  D.runs.forEach(function (run) { if (!run.superseded) lastRuns[run.source_id] = run; });

  // ------------------------------------------------------------------ routing
  var state = Dir.parseState(window.location.hash);

  function go(next, replace) {
    state = next;
    var hash = Dir.encodeState(state);
    if (replace) window.history.replaceState(null, "", hash);
    else window.location.hash = hash;
  }

  function render(focusHeading) {
    while (app.firstChild) app.removeChild(app.firstChild);
    document.querySelectorAll("nav.primary a").forEach(function (a) {
      var current = a.getAttribute("data-view") === (state.view === "model" ? "models" : state.view);
      if (current) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
    });
    if (state.view === "legacy") {
      // First-release links (#<route id>) open that route's model detail.
      var legacyRoute = state.legacy;
      var owner = entries.filter(function (e) { return e.route_ids.indexOf(legacyRoute) !== -1; })[0];
      if (owner) {
        state = Dir.emptyState();
        state.view = "model"; state.id = owner.id; state.route = legacyRoute;
        window.history.replaceState(null, "", Dir.encodeState(state));
      } else {
        app.appendChild(notFound("That link does not match a model or route in this directory."));
        return;
      }
    }
    if (state.view === "model") app.appendChild(modelView());
    else if (state.view === "sources") app.appendChild(sourcesView());
    else if (state.view === "how-we-test") app.appendChild(howView());
    else app.appendChild(directoryView());
    if (focusHeading) {
      var h = app.querySelector("h1");
      if (h) { h.setAttribute("tabindex", "-1"); h.focus(); }
    }
  }

  window.addEventListener("hashchange", function () {
    state = Dir.parseState(window.location.hash);
    render(true);
  });

  // ------------------------------------------------------------------ directory
  function directoryView() {
    var counts = { apps: entries.filter(function (e) { return e.access_kind === "consumer_app"; }).length };
    var wrap = el("section", { class: "directory", "aria-labelledby": "directory-title" });
    append(wrap, el("div", { class: "hero" }, [
      el("div", { class: "hero-text" }, [
        el("h1", { id: "directory-title" }, "Follow changes in AI model performance."),
        el("p", { class: "lede" }, TESTS.runs
          ? "Baseline publishes results from its own repeated tests for some models; each entry shows its status. Browse models and other published results below."
          : TESTS.calibration_runs
            ? "Baseline has published a one-off setup test of its own; no repeated daily results are published yet. Browse models and other published results below."
            : "Baseline's own recurring tests have not started yet. Browse models and other published results below.")
      ]),
      el("pre", { class: "ascii", "aria-hidden": "true" }, ASCII)
    ]));

    var search = el("input", { type: "search", id: "q", name: "q", autocomplete: "off", spellcheck: "false",
                               placeholder: "Search models or providers", value: state.q });
    search.value = state.q;
    var controls = el("form", { class: "controls", role: "search", "aria-label": "Find models" }, [
      el("div", { class: "search" }, [el("label", { for: "q" }, "Search"), search]),
      el("div", { class: "filters primary-filters" }, [
        select("provider", "Provider", [["", "All providers"]].concat(makers.map(function (m) { return [m, m]; }))),
        select("access", "App or API", [["", "Apps and APIs"]].concat(Object.keys(Dir.ACCESS_LABELS).filter(function (k) {
          return entries.some(function (e) { return e.access_kind === k; });
        }).map(function (k) { return [k, Dir.ACCESS_LABELS[k]]; })))
      ]),
      filterPanel([
        select("sort", "Sort", [["release", "Newest release"], ["name", "Name (A–Z)"], ["provider", "Provider"],
                                ["date", "Latest published test"]]),
        select("evidence", "Other published tests", [["", "Any"], ["measured", "Available"], ["none", "None recorded"]]),
        select("availability", "Availability", [["", "Any availability"], ["available", "Available"],
                                                ["retired", "Retired"], ["unknown", "Unknown"]])
      ])
    ]);
    var highlights = highlightsView();
    if (highlights && !pristine()) highlights.setAttribute("hidden", "");
    controls.addEventListener("submit", function (ev) { ev.preventDefault(); });
    search.addEventListener("input", function () { update({ q: search.value }); });
    var status = el("p", { class: "result-count", role: "status", "aria-live": "polite" });
    var results = el("div", { class: "results" });
    append(wrap, [controls, highlights, status, results]);   // search first, then Featured / New releases
    var sortNote = el("span", { class: "sort-note" }, SORT_NOTES[state.sort] || SORT_NOTES.release);
    append(wrap, el("p", { class: "fine" }, [
      sortNote,
      " Release dates are cited from each maker's announcements, release notes or model pages. ",
      "Apps (" + counts.apps + ") are listed separately from APIs; API results are never shown as app results. ",
      "Other published tests are limited to the sources listed under ", link("#sources", "Sources"), ". This is not an exhaustive list."
    ]));
    drawResults(results, status);

    // Secondary filters: one labelled disclosure, open on wide screens or when one is set
    // (small screens keep results near the top).
    function filterPanel(fields) {
      var active = ["evidence", "availability"].some(function (k) { return state[k]; }) || state.sort !== Dir.DEFAULT_SORT;
      var wide = window.matchMedia ? window.matchMedia("(min-width: 721px)").matches : true;
      var panel = el("details", { class: "filter-panel" }, [el("summary", {}, "More filters and sorting"), el("div", { class: "filters" }, fields)]);
      if (active || wide) panel.setAttribute("open", "");
      return panel;
    }
    function select(key, label, options) {
      var id = "f-" + key;
      var node = el("select", { id: id, name: key });
      options.forEach(function (o) {
        var opt = el("option", { value: o[0] }, o[1]);
        if (state[key] === o[0]) opt.setAttribute("selected", "selected");
        node.appendChild(opt);
      });
      node.value = state[key] || (key === "sort" ? Dir.DEFAULT_SORT : "");
      node.addEventListener("change", function () { var patch = {}; patch[key] = node.value; update(patch); });
      return el("div", { class: "field" }, [el("label", { for: id }, label), node]);
    }
    function update(patch) {
      Object.keys(patch).forEach(function (k) { state[k] = patch[k]; });
      go(state, true);
      sortNote.textContent = SORT_NOTES[state.sort] || SORT_NOTES.release;
      drawResults(results, status);
      if (highlights) {
        if (pristine()) highlights.removeAttribute("hidden"); else highlights.setAttribute("hidden", "");
      }
    }
    return wrap;
  }

  // Featured and New releases (T14) appear only on the unfiltered directory; any search,
  // filter or other sort shows the full matching list alone.
  function pristine() {
    return !state.q && !state.provider && !state.access && !state.evidence && !state.availability &&
      (!state.sort || state.sort === Dir.DEFAULT_SORT);
  }

  function entryLink(e, setup) {
    var g = e.model_group || groupByEntry[e.id];
    return Dir.encodeState({ view: "model", id: g.id, service: e.id, setup: setup || "", route: "", q: "", provider: "",
                             access: "", evidence: "", availability: "", sort: Dir.DEFAULT_SORT });
  }

  function highlightCard(e) {
    e = displayEntry(e);
    var ev = Dir.evidenceKind(e, TESTS, Date.now());
    return el("li", { class: "feature-card" }, [
      link(entryLink(e), e.name),
      el("span", { class: "sub" }, e.maker + " · " + accessText(e) + (Dir.releaseDate(e) ? " · released " + releaseText(e.release) : "")),
      el("span", { class: "tag", "data-evidence": ev.key }, ev.label)
    ]);
  }

  function highlightsView() {
    var featured = D.featured;
    var grouped = Dir.groupedEntries(entries, TESTS, Dir.emptyState());
    var newest = Dir.newReleases(grouped, 8);
    var featuredSeen = new Set();
    var parts = [testedView(featuredSeen)];
    if (featured) {
      parts.push(el("section", { class: "featured", "aria-labelledby": "featured-title" }, [
        el("h2", { id: "featured-title" }, "Featured"),
        el("p", { class: "sub" }, featured.explanation),
        el("ul", { class: "feature-groups" }, featured.groups.map(function (g) {
          return el("li", { class: "feature-group" }, [
            el("h3", {}, g.family),
            el("p", { class: "sub" }, g.reason),
            el("ul", { class: "feature-list" }, g.entries.map(function (id) { return entryById[id]; })
              .filter(Boolean).filter(function (e) {
                var id = groupByEntry[e.id].id;
                if (featuredSeen.has(id)) return false;
                featuredSeen.add(id); return true;
              }).map(highlightCard))
          ]);
        }))
      ]));
    }
    if (newest.length) {
      parts.push(el("section", { class: "new-releases", "aria-labelledby": "new-releases-title" }, [
        el("h2", { id: "new-releases-title" }, "New releases"),
        el("p", { class: "sub" }, "The newest cited release dates across all makers, newest first. A release date is " +
          "when the maker released the model, not when anyone tested it."),
        el("ol", { class: "feature-list" }, newest.map(highlightCard))
      ]));
    }
    parts.push(el("h2", { class: "all-models" }, "All models"));
    return el("div", { class: "highlights" }, parts);
  }

  // One measured model: the route and setup holding its newest published result, named, labelled and
  // linked from that same result (review R1), never from a newer setup without results.
  function measuredCard(g) {
    var best = null;
    g.members.forEach(function (member) {
      var hit = latestResult(member);
      if (hit && (!best || hit.date > best.date)) best = { entry: member, series: hit.series, date: hit.date };
    });
    var e = Object.assign({}, best.entry, { name: g.canonical.name.replace(/ via Puter$/, ""),
      release: g.canonical.release || best.entry.release, model_group: g });
    var setups = TESTS.entries[best.entry.id].daily_series || [];
    var newer = setups.length && setups[0].series_id !== best.series.series_id;
    return el("li", { class: "feature-card" }, [
      link(entryLink(e, best.series.series_id), e.name),
      el("span", { class: "sub" }, e.maker + " · " + accessText(e) + (Dir.releaseDate(e) ? " · released " + releaseText(e.release) : "")),
      el("span", { class: "sub test-name" }, testName(best.series) + " · scheduled " +
        dayText(best.series.schedule.start_date) + " to " + dayText(best.series.schedule.end_date) +
        " · latest result " + dayText(best.date) +
        (newer ? " · a newer test setup has no result yet" : "")),
      el("span", { class: "tag", "data-evidence": "ours" }, Dir.EVIDENCE_KINDS.ours)
    ]);
  }

  // The measured models, each with the test of its newest result; computed, never curated.
  function testedView(seen) {
    var cards = testedGroups.map(function (g) {
      seen.add(g.id);
      return measuredCard(g);
    });
    var n = testedGroups.length;
    return el("section", { class: "tested", "aria-labelledby": "tested-title" }, [
      el("h2", { id: "tested-title" }, "Measured by Baseline"),
      el("p", { class: "sub" }, n
        ? n + (n === 1 ? " exact model has" : " exact models have") + " published Baseline daily results. This list " +
          "is computed from those results. A result belongs only to the route it was measured on; every other " +
          "entry is a catalogue listing until Baseline publishes a test of it."
        : "No model has published Baseline daily results yet. Every entry is a catalogue listing until Baseline " +
          "publishes a test of it."),
      n ? el("ul", { class: "feature-list" }, cards) : null
    ]);
  }

  function accessText(e) {
    var label = Dir.ACCESS_LABELS[e.access_kind] || e.access_kind;
    return e.access_kind === "intermediary" ? label + " (" + e.service_provider + ")" : label;
  }

  function drawResults(results, status) {
    while (results.firstChild) results.removeChild(results.firstChild);
    var list = Dir.groupedEntries(entries, TESTS, state, Date.now());
    status.textContent = list.length === 1 ? "1 model or app" : list.length + " models and apps";
    if (!list.length) {
      var clear = el("button", { type: "button", class: "button" }, "Clear search and filters");
      clear.addEventListener("click", function () {
        var fresh = Dir.emptyState();
        go(fresh, true);
        render(false);
        var q = document.getElementById("q");
        if (q) q.focus();
      });
      append(results, el("div", { class: "empty" }, [el("p", {}, "No entries match your search."), clear]));
      return;
    }
    var head = el("div", { class: "row head", "aria-hidden": "true" },
                  ["Model", "Released", "Baseline tests", "Other published tests"].map(function (h) { return el("span", {}, h); }));
    var ul = el("ul", { class: "rows", "aria-label": "Models" });
    list.forEach(function (e) {
      var cov = Dir.coverage(e, Date.now());
      var st = ownStatus(e);
      var target = Dir.encodeState({ view: "model", id: e.model_group.id, service: e.id, route: "", q: state.q, provider: state.provider,
                                     access: state.access, evidence: state.evidence,
                                     availability: state.availability, sort: state.sort });
      ul.appendChild(el("li", { class: "row" }, [
        el("span", { class: "cell name" }, [link(target, e.name),
          e.exact_identifier && e.exact_identifier !== e.name ? el("code", { class: "sub" }, e.exact_identifier) : null,
          el("span", { class: "sub" }, e.maker + " · " + accessText(e) +
            (e.model_group.members.length > 1 ? " · " + e.model_group.members.length + " access routes" : "")),
          e.identity_kind === "exact" ? null : el("span", { class: "sub" }, e.identity_kind === "automatic"
            ? "model chosen by the app" : "family entry, exact version not verified")]),
        el("span", { class: "cell", "data-label": "Released" }, Dir.releaseDate(e)
          ? releaseText(e.release) : el("span", { class: "muted" }, "No verified date")),
        el("span", { class: "cell", "data-label": "Baseline tests" }, [
          el("span", { class: "status", "data-status": st.key }, st.label),
          st.key === "calibration" ? el("span", { class: "sub" }, setupScore(st.calibration))
            : st.latest ? el("span", { class: "sub" }, "latest daily test " + dayText(st.latest)) : null]),
        el("span", { class: "cell", "data-label": "Other published tests" }, cov.kind === "none"
          ? el("span", { class: "muted" }, "None recorded")
          : [el("span", { class: "tag", "data-kind": cov.kind }, "Other published tests available"),
             el("span", { class: "sub" }, "latest test " + dayText(cov.newest))])
      ]));
    });
    append(results, [head, ul]);
  }

  // ------------------------------------------------------------------ detail
  function backLink() {
    var back = { view: "models", id: "", route: "", q: state.q, provider: state.provider, access: state.access,
                 evidence: state.evidence, availability: state.availability, sort: state.sort };
    return el("p", { class: "back" }, link(Dir.encodeState(back), "← All models"));
  }

  function notFound(message) {
    return el("section", { class: "notfound" }, [
      el("h1", {}, "Not found"), el("p", {}, message),
      el("p", {}, link("#models", "Go to the model directory"))
    ]);
  }

  function statusBlock(st) {
    var detail = {
      not_tested: "We don't yet have our own repeated tests for this model.",
      calibration: st.calibration ? setupScore(st.calibration) + ". Not enough repeated tests to judge a change." : "",
      collecting: "Baseline has started repeated tests; there are not yet enough runs to compare against.",
      stale: "Baseline's newest usable daily result is " + (st.latest ? "from " + dayText(st.latest) : "missing") +
             "; nothing newer has been published, so this is not current monitoring.",
      insufficient: "Baseline's runs so far cannot tell a real change from normal variation.",
      lower: "A reviewed analysis of Baseline's repeated tests found lower results than its baseline.",
      higher: "A reviewed analysis of Baseline's repeated tests found higher results than its baseline.",
      no_change: "A reviewed analysis of Baseline's repeated tests found no meaningful change.",
      unavailable: "Baseline's most recent scheduled test did not produce a usable result, so no new result was recorded."
    }[st.key];
    return el("div", { class: "status-block", "data-status": st.key }, [
      el("p", { class: "status-label" }, st.label), el("p", {}, detail)]);
  }

  // ------------------------------------------------------------------ Baseline's own results
  function words(name) { return String(name).split("_").join(" "); }
  function ownSettingsText(x) {
    return "temperature " + x.temperature + ", thinking level " + x.thinking_level + ", output limit " +
      x.max_output_tokens + " tokens, " + x.timeout_seconds + "-second timeout";
  }
  // "38 of 40 correct on this test, 1 Oct 2026" — always from the published record.
  function setupScore(rec) {
    if (!rec || rec.evidence !== "verified") return "Setup test " + (rec ? dayText(rec.date) : "") + ": evidence unavailable, so no counts are shown";
    return rec.first_attempt_correct + " of " + rec.scheduled_items + " correct on this test, " + dayText(rec.date);
  }
  function recovered(rec) {
    var r = rec.retry_recovered;
    return r.correct + r.incorrect + r.format_error + r.other;
  }
  function outcomeList(rec) {
    var g = Dir.outcomeGroups(rec.first_attempt_outcomes);
    return el("ul", { class: "counts" }, [
      el("li", {}, "Correct on the first attempt: " + g.correct + " of " + rec.scheduled_items),
      el("li", {}, "Incorrect: " + g.incorrect),
      el("li", {}, "Wrong answer format: " + g.format_error),
      el("li", {}, "Refused: " + g.refusal),
      el("li", {}, "Cut off, empty, unreadable or from another model version: " + g.answer_problems),
      el("li", {}, "Request errors or timeouts: " + g.request_errors),
      el("li", {}, "Not sent: " + g.not_sent),
      el("li", {}, "Answered on a retry after a request error (shown separately, never added to the first-attempt count): " +
        recovered(rec) + (recovered(rec) ? ", of which " + rec.retry_recovered.correct + " correct" : ""))
    ]);
  }
  function techDetails(rec) {
    return el("details", { class: "tech" }, [
      el("summary", {}, "Technical details"),
      el("dl", { class: "facts" }, [
        el("dt", {}, "Run"), el("dd", {}, rec.run_id ? el("code", {}, rec.run_id) : "none"),
        el("dt", {}, "Route"), el("dd", {}, [el("code", {}, rec.route_id), " · model ", el("code", {}, rec.requested_model)]),
        el("dt", {}, "Settings"), el("dd", {}, ownSettingsText(rec.settings)),
        el("dt", {}, "Question set"), el("dd", {}, [rec.panel_id + " · sha256 ", el("code", { class: "hash" }, rec.panel_sha256)]),
        el("dt", {}, "Configuration"), el("dd", {}, el("code", { class: "hash" }, rec.config_fingerprint)),
        el("dt", {}, "Report sha256"), el("dd", {}, rec.report_sha256 ? el("code", { class: "hash" }, rec.report_sha256) : "not available")
      ])
    ]);
  }
  var ROW_STATE = { completed: "Completed", stopped: "Stopped early", interrupted: "Interrupted",
                    gap: "Missed (recorded gap)", no_record: "No record", open: "Still open",
                    incomplete: "Incomplete (outcome uncertain)" };
  function dailyRow(row) {
    var r = row.record;
    var state = ROW_STATE[row.state] || row.state;
    if (!r || r.evidence !== "verified") {
      var why = row.state === "open" ? "run not yet resolved when last checked; no score"
        : !r ? "nothing was recorded for this date" : r.status === "gap" ? "no run took place" : "evidence unavailable";
      return el("tr", {}, [el("th", { scope: "row" }, dayText(row.date)), el("td", { "data-label": "Result" }, state + " — " + why),
                           el("td", { colspan: "4", "data-label": "Counts" }, "no counts")]);
    }
    var g = Dir.outcomeGroups(r.first_attempt_outcomes);
    return el("tr", {}, [
      el("th", { scope: "row" }, dayText(row.date)),
      el("td", { "data-label": "Result" }, state + (r.valid_day ? "" : " — fewer than 90% attempted; not a usable day")),
      el("td", { "data-label": "First-attempt correct" }, r.first_attempt_correct + " of " + r.scheduled_items),
      el("td", { "data-label": "Sent" }, r.attempted_items + " attempted, " + g.not_sent + " not sent"),
      el("td", { "data-label": "Errors and refusals" }, (g.refusal + g.answer_problems + g.request_errors) + " (" + g.refusal + " refused, " +
        g.request_errors + " request errors)"),
      el("td", { "data-label": "Correct on retry" }, String(r.retry_recovered.correct))
    ]);
  }
  // One daily series as an SVG graph (T13). Layout comes from site/results-chart.js; this only draws it.
  var MARK_GLYPHS = { gap: "x", no_record: "x", partial: "~", unavailable: "?", open: "o", pending: "·" };
  function dailyChart(series) {
    var lay = Chart.layout(series, { width: 720, height: 250 });
    var puter = isPuter(series);
    var detail = el("p", { class: "point-detail", "aria-live": "polite" },
      lay.points.length || lay.marks.length ? "Select a point or mark to see that day's details." : "");
    var svg = s("svg", { class: "chart daily-chart", viewBox: "0 0 " + lay.width + " " + lay.height, role: "group",
      "aria-label": (puter ? series.route.label + ", small sample of " + lay.max + " questions. Model identity not " +
        "confirmed unless stated per day. " : "") +
        "Daily test scores: correct answers out of " + lay.max + " by test date. " + lay.points.length +
        (lay.points.length === 1 ? " daily score" : " daily scores") + " and " +
        lay.marks.filter(function (m) { return m.kind !== "pending"; }).length + " dates without a score." });
    lay.yTicks.forEach(function (t) {
      svg.appendChild(s("line", { x1: lay.left, x2: lay.right, y1: t.y, y2: t.y, class: "gridline" }));
      svg.appendChild(s("text", { x: lay.left - 6, y: t.y + 4, "text-anchor": "end" }, String(t.value)));
    });
    svg.appendChild(s("line", { x1: lay.left, x2: lay.right, y1: lay.plotBottom, y2: lay.plotBottom, class: "axis" }));
    lay.xTicks.forEach(function (t) {
      svg.appendChild(s("line", { x1: t.x, x2: t.x, y1: lay.plotBottom, y2: lay.plotBottom + 5, class: "axis" }));
      svg.appendChild(s("text", { x: t.x, y: lay.plotBottom + 17, "text-anchor": "middle" }, t.label));
    });
    svg.appendChild(s("text", { x: 4, y: lay.laneY + 4, "text-anchor": "start", class: "lane-label" }, "no score"));
    svg.appendChild(s("line", { x1: lay.left, x2: lay.right, y1: lay.laneY - 11, y2: lay.laneY - 11, class: "lane" }));
    lay.segments.forEach(function (seg) {
      svg.appendChild(s("polyline", { class: "score-line", fill: "none",
        points: seg.map(function (p) { return p.x.toFixed(1) + "," + p.y.toFixed(1); }).join(" ") }));
    });
    function selectable(node, label) {
      node.setAttribute("tabindex", "0");
      node.setAttribute("role", "button");
      node.setAttribute("aria-label", label);
      node.appendChild(s("title", {}, label));
      function show() { detail.textContent = label; }
      node.addEventListener("click", show);
      node.addEventListener("keydown", function (ev) {
        if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); show(); }
      });
      return node;
    }
    lay.marks.forEach(function (m) {
      var g = s("g", { class: "mark", "data-kind": m.kind });
      g.appendChild(s("text", { x: m.x, y: lay.laneY + 4, "text-anchor": "middle" }, MARK_GLYPHS[m.kind]));
      svg.appendChild(m.kind === "pending" ? g : selectable(g, m.label));
    });
    lay.points.forEach(function (p) {
      var g = s("g", { class: "score-point" });
      g.appendChild(s("circle", { cx: p.x, cy: p.y, r: 5, class: "point" }));
      svg.appendChild(selectable(g, p.label));
    });
    if (lay.message) {
      svg.appendChild(s("text", { x: (lay.left + lay.right) / 2, y: (lay.top + lay.plotBottom) / 2, "text-anchor": "middle",
                                  class: "chart-message" }, lay.message));
    }
    var legend = el("ul", { class: "chart-legend" }, [
      el("li", {}, puter ? "● a daily score: all " + lay.max + " questions attempted and gradeable, with no model mismatch. " +
        "Lines join consecutive days only." : "● a daily score: every question attempted. Lines join consecutive days only."),
      el("li", {}, "x a missed day: no run, or nothing recorded."),
      el("li", {}, puter ? "~ a partial or ungradeable run, or a model mismatch: shown with its counts, not as a score."
        : "~ an incomplete run: shown with its attempted count, not as a score."),
      el("li", {}, "? run evidence unavailable: no score shown."),
      el("li", {}, "o a run still open or unresolved when last checked: no score yet, not counted as missed."),
      el("li", {}, "· a later date: not yet tested or not yet published.")
    ]);
    return el("figure", { class: "own-chart" }, [
      el("p", { class: "axis-title" }, puter ? "Correct answers out of " + lay.max + ", by test date (UTC)"
        : "Correct answers out of " + lay.max + " (first attempts), by test date (UTC)"),
      el("div", { class: "chart-scroll" }, svg),
      lay.message ? el("p", { class: "chart-note" }, lay.message + ".") : null,
      detail, el("details", { class: "chart-key" }, [el("summary", {}, "How to read this graph"), legend])]);
  }

  function checkedNote(d) {
    var ageDays = Math.floor((Date.now() - Date.parse(d.as_of)) / 86400000);
    var ended = Date.now() > Date.parse(d.schedule.end_date + "T23:59:59Z");
    return el("p", { class: "sub" }, "Results checked up to " + utc(d.as_of) + "." +
      (ageDays > Dir.STALE_DAYS && !ended
        ? " Nothing newer has been published since then; later dates are not yet known, not confirmed as missed." : ""));
  }

  // One graph area per model (owner decision, 6 October 2026): a labelled selector shows one Baseline
  // test setup at a time. Setups are never stacked, merged or joined into one trend.
  // Every label is unique: two setups with the same settings and dates still differ in their daily
  // window or configuration, and both are named.
  function windowText(sch) {
    var start = sch.window_start_utc.split(":").map(Number);
    var closes = start[0] * 60 + start[1] + sch.window_minutes;
    return sch.window_start_utc + "–" + ("0" + Math.floor(closes / 60) % 24).slice(-2) + ":" + ("0" + closes % 60).slice(-2) + " UTC";
  }
  function setupText(d, e) {
    var service = isPuter(d) ? d.route.label + " through " + d.route.service_provider : (e ? accessText(e) : "");
    var config = String(d.config_fingerprint || d.series_fingerprint || "").slice(0, 8);
    return (isPuter(d) ? puterSettingsText(d.settings) : ownSettingsText(d.settings)) + " · " + d.panel_items +
      " questions · " + (service ? service + " · " : "") + "scheduled " + dayText(d.schedule.start_date) + " to " +
      dayText(d.schedule.end_date) + ", daily " + windowText(d.schedule) + (config ? " · configuration " + config : "");
  }
  function dailyBlock(rec, e) {
    var list = rec.daily_series || (rec.daily ? [rec.daily] : []);
    var parts = [el("h3", {}, "Daily test scores")];
    if (!list.length) {
      return parts.concat(el("div", { class: "chart-empty" }, [
        el("p", {}, "Waiting for daily results."),
        el("p", {}, "No daily test results have been published for this model yet.")]));
    }
    var content = el("div", { class: "daily-selected" });
    function showSetup(index) {
      if (!Number.isInteger(index) || index < 0 || index >= list.length) return;
      var d = list[index];
      while (content.firstChild) content.removeChild(content.firstChild);
      append(content, el("p", { class: "test-name" }, testName(d)));
      if (isPuter(d)) append(content, el("p", { class: "sub route-disclosure" },
        "Tested through " + d.route.service_provider + " · " +
        (identityConfirmed(d) ? "model identity reported as requested" : "model identity unverified") +
        " · " + d.planned_items + "-question sample"));
      append(content, dailyChart(d));
      var details = el("details", { class: "evidence test-details" }, [
        el("summary", {}, "Test details"),
        el("p", { class: "setup-description" }, (list.length > 1 ? "Selected: " : "Setup: ") + setupText(d, e))
      ]);
      if (isPuter(d)) append(details, puterLabels(d));
      append(content, [details, checkedNote(d), dailySection(d)]);
      if (isPuter(d)) append(content, el("p", {},
        "Four questions are a small sample and are not comparable with the 40-question tests."));
    }
    // A link may name one setup (?setup=<series id>, from a measured card); otherwise the latest is shown.
    var initial = Math.max(0, list.map(function (d) { return d.series_id; }).indexOf(state.setup));
    if (list.length > 1) {
      var selector = el("select", { id: "daily-setup" }, list.map(function (d, i) {
        return el("option", { value: String(i) }, (i === 0 ? "Latest setup" : "Earlier setup") + ": " + setupText(d, e));
      }));
      selector.value = String(initial);
      selector.addEventListener("change", function () { showSetup(Number(selector.value)); });
      parts.push(el("div", { class: "setup-choice" }, [
        el("label", { for: "daily-setup" }, "Test setup"),
        el("p", { class: "sub" }, "Choose a test setup. Different setups are kept separate and are never joined into one trend."),
        selector]));
    }
    showSetup(initial);
    parts.push(content);
    parts.push(el("p", {}, "These scores describe this fixed test. A rise or fall alone does not establish an overall " +
      "change in model quality. Not enough repeated tests to judge a change."));
    return parts;
  }

  // ------------------------------------------------------------------ Puter four-question series
  function isPuter(d) { return d && d.contract === "puter-subset-v1"; }
  // Which test a graph shows: the full reference set, or a separate quick check of a few of its questions.
  // The two are separate tests; a quick-check score is never shown as a share of the full set.
  function testName(d) {
    return isPuter(d) ? "Quick check: " + d.planned_items + " of the " + d.parent_panel_items + " reference questions, " +
      "through " + d.route.service_provider : "Reference test: all " + d.panel_items + " questions";
  }
  function puterSettingsText(x) {
    return "Puter SDK " + x.sdk_version + ", provider " + x.provider + ", output limit " + x.max_tokens + " tokens" +
      (x.reasoning_effort ? ", reasoning " + x.reasoning_effort : "") + ", no retries";
  }
  // Confirmed only when every attempted answer of every verified day reported the requested model.
  function identityConfirmed(d) {
    var verified = d.rows.filter(function (row) { return row.record && row.record.evidence === "verified" && row.record.attempted; });
    return verified.length > 0 && verified.every(function (row) {
      return row.record.identity.reported_match === row.record.attempted;
    });
  }
  function puterLabels(d) {
    return el("div", { class: "puter-labels" }, [
      d.synthetic ? el("p", { class: "notice synthetic", role: "note" }, "Synthetic preview — not real measurements") : null,
      el("p", { class: "labels" }, [el("strong", {}, d.route.label), " · ",
        el("span", { class: "tag", "data-kind": "sample" }, "Small sample: " + d.planned_items + " questions"),
        identityConfirmed(d) ? null : [" · ", el("span", { class: "tag", "data-kind": "identity" }, "Model identity not confirmed")]]),
      el("p", { class: "sub" }, "Requested route through " + d.route.service_provider + " (an intermediary): model " +
        d.route.exact_identifier + ", " + d.route.service_provider + " provider " + d.route.requested_provider + ". " +
        d.planned_items + " fixed questions (" + d.subset_item_ids.join(", ") + ") from the " + d.parent_panel_items +
        "-question set " + d.parent_panel_id + ", graded with " + d.grader_version + ". These are responses for the " +
        "requested Puter route, not verified " + d.route.maker + " model performance.")
    ]);
  }
  function puterRow(row) {
    var r = row.record;
    var state = ROW_STATE[row.state] || row.state;
    if (!r || r.evidence !== "verified") {
      var why = row.state === "open" ? "run not yet resolved when last checked; no score"
        : !r ? "nothing was recorded for this date" : r.status === "gap" ? "no run took place"
        : r.status === "incomplete" ? "outcome uncertain; no counts" : "evidence unavailable; no counts";
      return el("tr", {}, [el("th", { scope: "row" }, dayText(row.date)), el("td", { "data-label": "Result" }, state + " — " + why),
                           el("td", { colspan: "4", "data-label": "Counts" }, "no counts")]);
    }
    var ng = r.not_graded, id = r.identity;
    var notGraded = ng.refusal + ng.error + ng.truncated + ng.missing_text + ng.malformed + ng.uncertain;
    var reason = row.eligible ? "" : r.attempted < r.planned_items ? " — not every question attempted; not a daily score"
      : r.answered < r.planned_items ? " — not every answer gradeable; not a daily score"
      : " — returned model differed; not a daily score";
    var identity = id.mismatch ? id.mismatch + " from a different model" + (id.unknown ? ", " + id.unknown + " not confirmed" : "")
      : id.reported_match === r.attempted && r.attempted ? "reported as requested" : "not confirmed (" + id.unknown + " of " + r.attempted + " unknown)";
    return el("tr", {}, [
      el("th", { scope: "row" }, dayText(row.date)),
      el("td", { "data-label": "Result" }, state + reason),
      el("td", { "data-label": "Correct" }, r.correct + " of " + r.planned_items),
      el("td", { "data-label": "Attempted" }, r.attempted + " of " + r.planned_items + " attempted, " + r.not_sent + " not sent"),
      el("td", { "data-label": "Not graded or errors" }, notGraded + " (" + ng.refusal + " refused, " + ng.error + " errors, " +
        (ng.truncated + ng.missing_text + ng.malformed) + " cut off or unreadable, " + ng.uncertain + " uncertain)"),
      el("td", { "data-label": "Model identity" }, identity)
    ]);
  }

  function dailySection(d) {
    var parts = [];
    var sch = d.schedule;
    var end = sch.window_start_utc.split(":").map(Number);
    var closes = end[0] * 60 + end[1] + sch.window_minutes;
    var hhmm = ("0" + Math.floor(closes / 60) % 24).slice(-2) + ":" + ("0" + closes % 60).slice(-2);
    var last = d.rows.length ? d.rows[d.rows.length - 1] : null;
    parts.push(el("p", {}, "Scheduled once a day between " + sch.window_start_utc + " and " + hhmm + " UTC, " +
      dayText(sch.start_date) + " to " + dayText(sch.end_date) + ". Published results cover scheduled dates up to " +
      dayText(d.as_of) + "." + (last ? " Latest scheduled date: " + dayText(last.date) + " — " + (ROW_STATE[last.state] || last.state) + "." : "")));
    if (d.rows.length) {
      parts.push(el("details", { class: "evidence own-table" }, [el("summary", {}, "Daily results as a table"),
        el("div", { class: "table-scroll" }, el("table", { class: "log own" }, [
        el("caption", {}, "Daily results by date. Each row is a separate day; rows are not joined into a trend."),
        el("thead", {}, el("tr", {}, (isPuter(d) ? ["Date", "Result", "Correct", "Attempted", "Not graded or errors", "Model identity"]
          : ["Date", "Result", "First-attempt correct", "Sent", "Errors and refusals", "Correct on retry"])
          .map(function (h) { return el("th", { scope: "col" }, h); }))),
        el("tbody", {}, d.rows.slice().reverse().map(isPuter(d) ? puterRow : dailyRow))
      ]))]));
    }
    if (d.not_yet_due) {
      parts.push(el("p", { class: "sub" }, d.not_yet_due + (d.not_yet_due === 1 ? " later scheduled date was" : " later scheduled dates were") +
        " not yet due when these results were prepared; they are not counted as missed."));
    }
    return parts;
  }
  function setupSection(list) {
    if (!list.length) return [];
    var parts = [el("h3", {}, "One-off setup test")];
    list.slice().reverse().forEach(function (rec) {
      parts.push(el("p", { class: "summary" }, [el("strong", {}, rec.evidence === "verified"
        ? rec.first_attempt_correct + " of " + rec.scheduled_items + " correct on this test" : "Evidence unavailable"),
        " · measured " + dayText(rec.date) + " (UTC date)"]));
      parts.push(el("p", {}, "A single run, made once to check the questions and settings before daily testing. " +
        "It is not part of the daily history, and one run cannot show a change. Not enough repeated tests to judge a change."));
      if (rec.evidence === "verified") parts.push(outcomeList(rec));
      parts.push(techDetails(rec));
    });
    return parts;
  }
  function ownTestsSection(e, st) {
    var rec = TESTS.entries ? TESTS.entries[e.id] : null;
    var body;
    if (!rec) {
      body = el("p", {}, ["No Baseline test history yet. ", link("#how-we-test", "How we test")]);
    } else if (rec.daily === undefined && rec.calibration === undefined) {
      body = el("p", {}, st.runs + (st.runs === 1 ? " Baseline run" : " Baseline runs") + (st.latest ? "; latest test " + dayText(st.latest) + "." : "."));
    } else {
      body = [
        dailyBlock(rec, e),
        setupSection(rec.calibration || []),
        el("p", { class: "note" }, ["These counts come from Baseline's private run records. Before publication they were " +
          "checked against stored file hashes, either by a person or automatically under a publication policy a person " +
          "approved. Prompts and raw responses stay private, so individual answers cannot be checked from this page. ",
          link("#how-we-test", "How we test")])
      ];
    }
    return el("section", { class: "part", "aria-labelledby": "our-tests" }, [el("h2", { id: "our-tests" }, "Our tests"), body]);
  }

  function modelView() {
    var e = entryById[state.id];
    if (!e) return notFound("There is no entry with the id “" + state.id + "”. It may have been renamed.");
    var group = groupByEntry[e.id];
    // Canonical model links open the measured route. Old route-specific links still work.
    var chosen = group.members.filter(function (member) { return member.id === state.service; })[0];
    if (chosen) e = chosen;
    else if (state.route) {
      e = group.members.filter(function (member) { return member.route_ids.indexOf(state.route) !== -1; })[0] || e;
    } else if (e.id === group.id) e = group.preferred;
    var routes = e.routes.slice().sort(function (a, b) { return settingsText(a.settings) < settingsText(b.settings) ? -1 : 1; });
    var route = routes.filter(function (r) { return r.id === state.route; })[0] || routes[0];
    var st = ownStatus(e);
    var wrap = el("article", { class: "detail", "aria-labelledby": "model-title" }, backLink());
    append(wrap, el("header", { class: "identity" }, [
      el("p", { class: "eyebrow" }, e.maker + " · " + accessText(e)),
      el("h1", { id: "model-title" }, group.canonical.name.replace(/ via Puter$/, "")),
      e.exact_identifier && e.exact_identifier !== e.name ? el("p", { class: "ident" }, el("code", {}, e.exact_identifier)) : null,
      el("p", { class: "released" }, e.release
        ? ["Released " + releaseText(e.release) + " · ", link(e.release.source.url, "release source")]
        : "No verified release date recorded"),
      statusBlock(st)
    ]));

    if (group.members.length > 1) {
      var access = el("select", { id: "model-service" }, group.members.map(function (member) {
        return el("option", { value: member.id }, member.service_provider + " · " +
          (Dir.ACCESS_LABELS[member.access_kind] || member.access_kind) + " · " + Dir.evidenceKind(member, TESTS).label);
      }));
      access.value = e.id;
      access.addEventListener("change", function () {
        go(Object.assign({}, state, { id: group.id, service: access.value, route: "" }), false);
        render(false);
      });
      append(wrap, el("div", { class: "setup-choice" }, [el("label", { for: "model-service" }, "Access route"), access,
        el("p", { class: "sub" }, "Showing results for this route only. Other services may behave differently; their results are kept separate.")]));
    }
    append(wrap, ownTestsSection(e, st));

    var other = el("section", { class: "part", "aria-labelledby": "other-tests" }, el("h2", { id: "other-tests" }, "Other published tests"));
    if (!route) {
      append(other, el("p", {}, e.access_kind === "consumer_app"
        ? "No other published results are recorded here for this app. Results for the maker's API models are separate entries; API results are never shown as app results."
        : "No other published results are recorded here. That is missing evidence, not a score of zero and not evidence of stability."));
    } else {
      var cov = Dir.coverage(e, Date.now());
      var src = sourceById[route.source_ids[0]] || {};
      var count = e.routes.reduce(function (n, r) { return n + r.observations.length; }, 0);
      append(other, el("p", { class: "summary" }, [
        el("strong", {}, SOURCE_LABELS[src.id] || (src.author || "Third-party") + " results"),
        " · latest test " + dayText(cov.newest) + " · " + count + (count === 1 ? " run" : " runs") + ", not run by Baseline"]));
      var more = el("details", { class: "evidence" }, el("summary", {}, "View dated results and sources"));
      if (state.route) more.setAttribute("open", "");
      if (routes.length > 1) {
        var nav = el("nav", { class: "routes", "aria-label": "Setup" }, el("span", { class: "label" }, "Setup:"));
        routes.forEach(function (r) {
          var target = Dir.encodeState({ view: "model", id: e.id, route: r.id, q: state.q, provider: state.provider,
                                         access: state.access, evidence: state.evidence, availability: state.availability, sort: state.sort });
          var a = link(target, settingsText(r.settings));
          if (r === route) a.setAttribute("aria-current", "true");
          nav.appendChild(a);
        });
        append(more, nav);
      }
      append(more, history(route));
      append(other, more);
    }
    append(wrap, other);

    append(wrap, el("section", { class: "part", "aria-labelledby": "model-details" }, [
      el("h2", { id: "model-details" }, "Model details"),
      el("dl", { class: "facts" }, [
        el("dt", {}, "Identity"), el("dd", {}, e.identity_kind === "exact" ? el("code", {}, e.exact_identifier)
          : e.identity_kind === "automatic" ? "Chosen by the app; not an exact model version" : "Family entry; exact version not verified"),
        el("dt", {}, "Service"), el("dd", {}, e.service_provider + (e.access_kind === "intermediary" ? " (made by " + e.maker + ")" : "")),
        el("dt", {}, "Availability"), el("dd", {}, e.availability === "unknown" ? "Unknown" : e.availability === "retired" ? "Retired" : "Available"),
        el("dt", {}, "Release date"), el("dd", {}, e.release ? [releaseText(e.release) + " — ", link(e.release.source.url, e.release.source.claim),
          el("span", { class: "sub" }, " (checked " + e.release.source.checked_at.slice(0, 10) + ")")]
          : "No verified release date recorded."),
        el("dt", {}, "Listed from"), el("dd", {}, e.sources.map(function (src, i) {
          return [i ? " · " : "", link(src.url, src.claim), el("span", { class: "sub" }, " (checked " + src.checked_at.slice(0, 10) + ")")];
        }))
      ]),
      e.notes ? el("p", { class: "note" }, e.notes) : null
    ]));
    return wrap;
  }

  function history(r) {
    var dates = r.observations.map(function (o) { return o.observed_at; });
    var newest = F.newest(dates);
    var newestObs = r.observations.filter(function (o) { return o.observed_at === newest; })[0];
    var firstRetrieved = r.observations.map(function (o) { return o.retrieved_at; }).sort()[0];
    var src = sourceById[r.source_ids[0]] || {};
    var run = lastRuns[r.source_ids[0]];
    var sorted = dates.slice().sort();
    var section = el("section", { class: "history", id: r.id, "aria-label": "History for " + r.requested_model });
    append(section, [
      el("div", { class: "panel" }, el("dl", { class: "fresh" }, [
        el("div", {}, [el("dt", {}, "Newest measurement"), el("dd", {}, [
          el("span", { class: "big" }, liveAge(newest)), dateText(newestObs), liveStatus(newest)])]),
        el("div", {}, [el("dt", {}, "Copied by Baseline"), el("dd", {}, [
          el("span", { class: "big" }, liveAge(firstRetrieved)), utc(firstRetrieved), el("br"),
          el("span", { class: "sub" }, "When we saved the source, not when it was measured.")])]),
        el("div", {}, [el("dt", {}, "Source last checked"), el("dd", {}, src.last_successful_check ? [
          el("span", { class: "big" }, liveAge(src.last_successful_check)), utc(src.last_successful_check), el("br"),
          el("span", { class: "sub" }, run && run.status === "failed"
            ? "The most recent check failed; the evidence shown is unchanged."
            : "The latest successful check of the source for new results.")] : "never checked")])
      ])),
      el("div", { class: "limits", role: "note" }, [
        el("strong", {}, "Read before comparing. "),
        "These results come from " + (src.author || "a third-party source") + ", measured through " +
        r.service.split(",")[0] + ", not by Baseline. " + AGE_NOTE[F.measurementStatus(newest, Date.now()).key] + " " +
        r.observations.length + (r.observations.length === 1 ? " run" : " runs") +
        " recorded; each lettered setup is a separate configuration, so its records in the table are never joined into a trend."
      ]),
      // One graph per model (owner decision, 6 October 2026): third-party records are tables, not a second graph.
      el("p", { class: "caption" }, [
        "These third-party results use a different test and are not included in Baseline's graph. " +
        "The dated records and sources are retained below; missing dates are not filled in. ",
        r.observations.length + (r.observations.length === 1 ? " run on " + sorted[0] + ". " :
          " runs between " + sorted[0] + " and " + sorted[sorted.length - 1] + ". Longest gap between runs: " +
          F.longestGapDays(dates) + " days. "),
        "No observations are recorded here between these runs or after the latest one. " +
        "This covers only the evidence Baseline holds: other measurements may exist elsewhere, and the source may have runs it did not publish."
      ]),
      el("h2", {}, "Runs"),
      el("p", { class: "caption", id: r.id + "-table-note" },
        "Pass rate counts exercises passed within two tries, out of those run. “Not run” counts exercises missing from the run."),
      el("div", { class: "table-scroll" }, table(r)),
      el("details", {}, [el("summary", {}, "What changed between runs"), breaks(r)]),
      el("details", {}, [el("summary", {}, "Route and setup details"), el("dl", { class: "facts" }, [
        el("dt", {}, "Requested model"), el("dd", {}, el("code", {}, r.requested_model)),
        el("dt", {}, "Service"), el("dd", {}, r.service),
        el("dt", {}, "Settings"), el("dd", {}, settingsText(r.settings)),
        el("dt", {}, "Route notes"), el("dd", {}, r.notes || "none"),
        el("dt", {}, "Mapping decision"), el("dd", {}, link(REPO + "docs/AIDER_ROUTE_REVIEW.md", "Aider route review"))
      ])]),
      el("details", {}, [el("summary", {}, "Source and licence"), sourceBlock(src)])
    ]);
    return section;
  }

  function chart(r) {
    var W = 720, H = 250, L = 46, R = 20, T = 30, B = 38;
    var now = Date.now();
    var times = r.observations.map(function (o) { return F.parseMoment(o.observed_at).time; });
    var t0 = Math.min.apply(null, times) - 30 * F.DAY_MS;
    var t1 = Math.max(now, Math.max.apply(null, times)) + 20 * F.DAY_MS;
    function x(t) { return L + (t - t0) / (t1 - t0) * (W - L - R); }
    function y(v) { return T + (1 - v / 100) * (H - T - B); }
    var pid = "hatch-" + r.id.replace(/[^a-z0-9]/gi, "");
    var svg = s("svg", { class: "chart", viewBox: "0 0 " + W + " " + H, role: "img", "data-chart-for": r.id,
      "aria-label": "Pass rate for " + r.requested_model + ": " + r.observations.map(function (o) {
        return o.series_letter + " " + o.observed_at + " " + pct(o.metric); }).join(", ") + ". Points are not connected. " +
      "Hatched band: no observations recorded here after " + r.observations[r.observations.length - 1].observed_at + "." });
    var defs = s("defs");
    var pat = s("pattern", { id: pid, width: 8, height: 8, patternUnits: "userSpaceOnUse", patternTransform: "rotate(45)" });
    pat.appendChild(s("line", { x1: 0, y1: 0, x2: 0, y2: 8, class: "hatch-line" }));
    defs.appendChild(pat);
    svg.appendChild(defs);
    [0, 25, 50, 75, 100].forEach(function (v) {
      svg.appendChild(s("line", { x1: L, x2: W - R, y1: y(v), y2: y(v), class: "gridline" }));
      svg.appendChild(s("text", { x: L - 6, y: y(v) + 4, "text-anchor": "end" }, v + "%"));
    });
    var d = new Date(t0); d = new Date(Date.UTC(d.getUTCFullYear(), Math.floor(d.getUTCMonth() / 3) * 3 + 3, 1));
    while (d.getTime() < t1) {
      var tx = x(d.getTime());
      svg.appendChild(s("line", { x1: tx, x2: tx, y1: H - B, y2: H - B + 5, class: "axis" }));
      svg.appendChild(s("text", { x: tx, y: H - B + 18, "text-anchor": "middle" }, MONTHS[d.getUTCMonth()] + " " + d.getUTCFullYear()));
      d = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 3, 1));
    }
    svg.appendChild(s("line", { x1: L, x2: W - R, y1: H - B, y2: H - B, class: "axis" }));
    var last = Math.max.apply(null, times);
    var gx0 = x(last + F.DAY_MS), gx1 = x(now);
    if (gx1 > gx0) {
      svg.appendChild(s("rect", { x: gx0, y: T, width: gx1 - gx0, height: H - T - B, fill: "url(#" + pid + ")", opacity: 0.55, "data-gap": "trailing" }));
      if (gx1 - gx0 > 110) {
        svg.appendChild(s("text", { x: (gx0 + gx1) / 2, y: T + 16, "text-anchor": "middle", class: "gap-label" },
          "no recorded evidence · " + Math.floor((now - last) / F.DAY_MS) + " days"));
      }
    }
    svg.appendChild(s("line", { x1: x(now), x2: x(now), y1: T - 8, y2: H - B, class: "today" }));
    svg.appendChild(s("text", { x: x(now), y: T - 12, "text-anchor": "middle", class: "today-label" }, "today"));
    r.observations.forEach(function (o, i) {
      var px = x(F.parseMoment(o.observed_at).time), py = y(100 * o.metric.numerator / o.metric.denominator);
      if (i > 0 && o.breaks.length) svg.appendChild(s("line", { x1: px, x2: px, y1: T, y2: H - B, class: "break" }));
      svg.appendChild(s("text", { x: px, y: T - 12 + (i % 2 ? 11 : 0), "text-anchor": "middle", class: "letter" }, o.series_letter));
      var c = s("circle", { cx: px, cy: py, r: 6, class: "point" });
      c.appendChild(s("title", {}, o.series_letter + " · " + o.observed_at + " · " + (o.source_label || "no label") + " · " +
        o.metric.numerator + "/" + o.metric.denominator + " (" + pct(o.metric) + ")"));
      svg.appendChild(c);
      svg.appendChild(s("text", { x: px + 9, y: py + 4, class: "value" }, pct(o.metric)));
    });
    return svg;
  }

  function table(r) {
    var head = ["Setup", "Measured", "Source's model label", "Passed by 2nd try", "Share", "Not run", "Test tool", "Edit format", "Evidence"];
    var tbody = el("tbody");
    r.observations.forEach(function (o) {
      var sd = o.source_details;
      var series = r.series.filter(function (x) { return x.id === o.series_id; })[0];
      var cells = [el("span", { class: "letter-chip" }, o.series_letter), dateText(o), o.source_label || "not stated",
        o.metric.numerator + " / " + o.metric.denominator, pct(o.metric), String(o.exclusions.missing || 0),
        series.harness, sd.edit_format || "not stated", link(o.evidence_url, "source line ↗")];
      var tr = el("tr");
      cells.forEach(function (c, i) { tr.appendChild(el("td", { "data-label": head[i], class: i >= 3 && i <= 5 ? "num" : "" }, c)); });
      tbody.appendChild(tr);
    });
    return el("table", { "aria-describedby": r.id + "-table-note" }, [
      el("thead", {}, el("tr", {}, head.map(function (h) { return el("th", { scope: "col" }, h); }))), tbody]);
  }

  function breaks(r) {
    var list = el("ul", { class: "breaks" });
    r.observations.forEach(function (o, i) {
      if (i === 0) return;
      var prev = r.observations[i - 1];
      var li = el("li", {}, [el("strong", {}, prev.series_letter + " → " + o.series_letter + ": ")]);
      if (!o.breaks.length) append(li, "same setup (runs join one series)");
      o.breaks.forEach(function (b, k) {
        append(li, [k ? "; " : "", el("span", { class: "change" }, b.field + ": " + fmt(b.from) + " → " + fmt(b.to))]);
      });
      list.appendChild(li);
    });
    if (!list.children.length) list.appendChild(el("li", {}, "Only one run; nothing to compare."));
    return list;
  }

  function sourceBlock(src) {
    var numeric = src.reuse_decision === "numeric_republication_permitted";
    return el("div", { class: "source" }, [
      el("p", {}, [link(src.url, src.author), numeric ? "" : el("span", { class: "badge" }, "link only")]),
      el("p", {}, src.method),
      numeric && src.licence ? el("p", {}, ["Numbers reused under the ", link(src.licence.upstream_url, src.licence.name),
        " (", link(src.licence.file, "copy of the licence"), "), from commit ", el("code", {}, (src.revision || "").slice(0, 12)),
        ". Only results are reused; benchmark exercises are not copied."])
        : el("p", {}, "No reuse permission for its numbers, so none are shown here. Follow the link to read it at the source."),
      el("p", { class: "sub" }, ["Last checked: ", src.last_successful_check ? [utc(src.last_successful_check), " (",
        liveAge(src.last_successful_check), ")"] : "never", ". Update schedule: ", src.expected_update_cadence || "not stated by the source", "."])
    ]);
  }

  // ------------------------------------------------------------------ sources & about
  function sourcesView() {
    var byMaker = {};
    D.catalog.forEach(function (e) {
      // A route through an intermediary is listed under that service: its listing is not the maker's.
      var lister = e.access_kind === "intermediary" ? e.service_provider : e.maker;
      e.sources.forEach(function (src) {
        if (/github\.com\/Aider-AI/.test(src.url)) return;
        (byMaker[lister] = byMaker[lister] || {})[src.url] = src.checked_at;
      });
    });
    var rows = D.runs.map(function (run) {
      return el("tr", {}, [
        el("td", { "data-label": "Started" }, utc(run.started_at)),
        el("td", { "data-label": "Source" }, run.source_id),
        el("td", { "data-label": "Result" }, run.superseded ? el("span", { class: "superseded" }, run.status) : run.status),
        el("td", { "data-label": "Problems" }, run.problem_types.join(", ") || "none"),
        el("td", { "data-label": "Note" }, run.superseded ? "Superseded development run; not evidence." : "")]);
    });
    return el("section", { class: "page", "aria-labelledby": "sources-title" }, [
      el("h1", { id: "sources-title" }, "Sources"),
      el("h2", {}, "Measurement sources"),
      D.sources.map(sourceBlock),
      el("h2", {}, "Where the model list comes from"),
      el("p", {}, "Model and app entries were taken from each maker's official model listing. Routes through an intermediary service (for example Puter) are listed under that service, from its own model listing; such a listing does not confirm which model answers a request. A listing shows what exists, not how a model performs."),
      el("ul", { class: "plain" }, Object.keys(byMaker).sort().map(function (maker) {
        return el("li", {}, [el("strong", {}, maker + ": "), Object.keys(byMaker[maker]).map(function (u, i) {
          return [i ? " · " : "", link(u, u.replace(/^https:\/\//, "")), " (checked " + byMaker[maker][u].slice(0, 10) + ")"];
        })]);
      })),
      el("details", {}, [
        el("summary", {}, "Ingestion log (" + D.runs.length + " runs, " + D.runs.filter(function (x) { return x.status === "failed"; }).length + " failed)"),
        el("p", { class: "sub" }, "Every attempt to copy a source is kept, including failures. Superseded runs stay listed but are not evidence."),
        el("div", { class: "table-scroll" }, el("table", { class: "log" }, [
          el("thead", {}, el("tr", {}, ["Started", "Source", "Result", "Problems", "Note"].map(function (h) { return el("th", { scope: "col" }, h); }))),
          el("tbody", {}, rows)]))
      ])
    ]);
  }

  // The published method, described from the admitted data rather than fixed copy (T12).
  function methodSection() {
    return [el("h2", {}, "Our test method")].concat(METHODS.map(function (m) {
      var cats = m.panel_categories.map(words);
      return el("ul", {}, [
        el("li", {}, m.panel_items + " short questions written for Baseline (set " + m.panel_id + "), in " + cats.length +
          " categories: " + cats.join(", ") + "."),
        el("li", {}, "Each question is sent through the service named on the model page (the maker's own API or a " +
          "third-party host) with fixed settings: " + ownSettingsText(m.settings) + ". The first attempt is what counts. " +
          "Where a setup permits an operational retry after a failed request, an answer recovered that way is shown " +
          "separately and never added to the first-attempt count; a setup without retries keeps the failure as it happened."),
        el("li", {}, "Answers are graded automatically against a fixed answer key (" + m.grader_version + "): an exact answer, a JSON object, a whole number or one of the listed choices. Grading is strict, so a right answer in the wrong format counts as a format error."),
        el("li", {}, "A daily run counts as usable only if at least 90% of its questions were attempted. Missed, failed or interrupted days stay listed; nothing is filled in."),
        el("li", {}, "Results apply only to the exact route tested: that model through that service, with these settings. " +
          "An app, another version of the model, another model from the same maker, or the same model through another " +
          "service is a separate entry and is not covered."),
        el("li", {}, "The questions were written and first run as a one-off setup test before this description was published, so the method was not publicly preregistered. No formal plan for judging changes exists yet, so no change verdict is shown."),
        el("li", {}, "Prompts and raw responses stay private. The counts come from Baseline's private run records, which were checked against stored file hashes before publication; visitors cannot check individual answers.")
      ]);
    }));
  }

  function howView() {
    var statuses = [
      ["not_tested", "We have no repeated tests of our own for this model. Nothing about its performance over time is claimed."],
      ["calibration", "Only a single setup run has been published. It is not part of the daily history, and one run cannot show a change."],
      ["collecting", "Our repeated tests have started, but there are not yet enough runs to compare against."],
      ["stale", "Daily results exist, but no usable result from the last " + Dir.STALE_DAYS + " days has been published, so the page does not show current monitoring."],
      ["insufficient", "We have runs, but they cannot separate a real change from normal run-to-run variation."],
      ["lower", "Shown only after a reviewed analysis finds results below the model's own baseline, beyond a threshold declared in advance."],
      ["higher", "Shown only after a reviewed analysis finds results above the model's own baseline, beyond a threshold declared in advance."],
      ["no_change", "Shown only after a reviewed analysis finds no change beyond that threshold."],
      ["unavailable", "Our most recent attempt to test failed; no result was recorded for it."]
    ];
    return el("section", { class: "page", "aria-labelledby": "how-title" }, [
      el("h1", { id: "how-title" }, "How we test"),
      el("p", { class: "lede" }, TESTS.runs
        ? "Baseline publishes results from its own repeated tests for some models. Each model page shows the status below. Models without an entry of their own are not tested by Baseline."
        : TESTS.calibration_runs
          ? "Baseline has published a one-off setup test of its own; no repeated daily results are published yet. Every other model is marked “Not tested by Baseline”, and no Baseline trend or change is shown."
          : "Baseline's own recurring tests have not started yet. Until they do, every model is marked “Not tested by Baseline”, and no Baseline score, trend or change is shown."),
      el("h2", {}, "What each status means"),
      el("dl", { class: "statuses" }, statuses.map(function (s) {
        return [el("dt", {}, el("span", { class: "status", "data-status": s[0] }, Dir.STATUS[s[0]])), el("dd", {}, s[1])];
      })),
      METHODS.length ? methodSection() : [
        el("h2", {}, "What our tests will be"),
        el("ul", {}, [
          el("li", {}, "A fixed set of test prompts, run through each model's named service on a declared timetable, with every attempt and failure kept."),
          el("li", {}, "Results are only ever from real runs. A scheduled day that fails or is missed stays visible; nothing is filled in."),
          el("li", {}, "An app is tested only as an app. API results are never shown as app results.")
        ])],
      el("h2", {}, "Other published tests"),
      el("p", {}, "Some models have results published by others. They are shown by their measurement date, linked to their source, and kept separate from Baseline's own tests."),
      el("ul", {}, [
        el("li", {}, "Apps, direct APIs, third-party hosts and open weights are separate entries. A result belongs only to the exact route it was measured on."),
        el("li", {}, "Each lettered setup is one exact configuration: route, settings, test tool version and commit, edit format and suite size. Different setups are not directly comparable, so points are never joined."),
        el("li", {}, "Measured dates are shown as the source gives them. This source gives a date only, with no time or timezone, so ages are about a day either way."),
        el("li", {}, "Freshness labels use the newest measurement's age: Recent up to " + F.RECENT_DAYS + " days, Aging up to " + F.AGING_DAYS + " days, Stale after that. This is a display convention, not a statistical test."),
        el("li", {}, "“Copied by Baseline” is when we saved the source. A copy made today of an old result is still an old result."),
        el("li", {}, "No confidence intervals are shown: the source reports one run per setup, which is not enough to estimate run-to-run variation."),
        el("li", {}, "Rises and falls are shown the same way. Nothing here says whether a provider changed a model deliberately."),
        el("li", {}, "An entry with no results has missing evidence, not a score of zero.")
      ]),
      el("h2", {}, "Release dates"),
      el("p", {}, "The directory lists the newest releases first. A release date is shown only when a maker's announcement, changelog or model page states it, and each date links to that page. Dates are never guessed from a model's name, from when we checked a page, or from when a test was run. Entries without a cited date are listed last."),
      el("h2", {}, "Methods and decisions"),
      el("ul", { class: "plain" }, [
        el("li", {}, link(REPO + "docs/AIDER_ROUTE_REVIEW.md", "Which benchmark rows are included, and why others are excluded")),
        el("li", {}, link(REPO + "docs/CATALOG_SOURCES.md", "How the model list and release dates were checked")),
        el("li", {}, link(REPO + "docs/SOURCES.md", "Source reuse permissions")),
        el("li", {}, link(REPO + "docs/DATA_CONTRACT.md", "Data rules")),
        el("li", {}, link(REPO + "docs/OWN_RESULTS_FORMAT.md", "How Baseline's own results are checked and admitted"))
      ])
    ]);
  }

  // ------------------------------------------------------------------ start
  if (D.own_results_preview) {
    document.body.insertBefore(el("p", { class: "notice review-copy", role: "note" },
      "Review copy: this page includes Baseline test results that have not yet been approved for publication."),
      document.body.firstChild);
  }
  if (D.synthetic_preview) {
    document.body.insertBefore(el("p", { class: "notice review-copy synthetic", role: "note" },
      "Synthetic preview — not real measurements"), document.body.firstChild);
  }
  document.body.appendChild(el("footer", {}, [
    "Data built " + utc(D.generated_at) + " from registry schema v" + D.schema_version + ". ",
    "Ages are worked out from your device clock each minute, so they stay current without a rebuild."
  ]));
  render(false);

  function tick() {
    var now = Date.now();
    document.querySelectorAll("[data-age]").forEach(function (n) { n.textContent = F.describeAge(n.getAttribute("data-age"), now); });
    document.querySelectorAll("[data-status-of]").forEach(function (n) {
      var v = n.getAttribute("data-status-of");
      if (!v) return;
      var st = F.measurementStatus(v, now);
      n.setAttribute("data-status", st.key);
      if (n.classList.contains("badge")) n.textContent = st.label;
    });
    document.querySelectorAll("[data-chart-for]").forEach(function (old) {
      var r = routeById[old.getAttribute("data-chart-for")];
      if (r) old.parentNode.replaceChild(chart(r), old);
    });
  }
  window.setInterval(tick, 60000);
  window.BaselinePage = { tick: tick, state: function () { return state; } };
})();
