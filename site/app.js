/* Baseline: Baseline's own measurements as one monitoring surface (monitor interface, 11 October 2026), with
   "How we test" and Sources. Renders window.BASELINE_DATA. All text goes through textContent. Only models with a
   scored Baseline result are listed; catalogue entries and third-party results are kept in the data but not shown.
   URL state lives in the hash (site/directory.js), so back/forward and shared links work. */
(function () {
  "use strict";
  var D = window.BASELINE_DATA;
  var F = window.BaselineFreshness;
  var Dir = window.BaselineDirectory;
  var Chart = window.BaselineResultsChart;
  var M = window.BaselineMeasured;
  var app = document.getElementById("app");
  var SVGNS = "http://www.w3.org/2000/svg";
  var REPO = "https://github.com/Qwinahh/baseline-route-histories/blob/main/";
  // List note for the selected order (T08 review: never claim the default order after a change).
  var SORT_NOTES = {
    release: "Sorted by newest release; models without a cited release date are listed last.",
    name: "Sorted by name (A–Z).",
    provider: "Sorted by provider, then name.",
    date: "Sorted by latest Baseline result."
  };
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  if (!D || !F || !Dir || !Chart || !M) {
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
  function utc(value) { return value.replace("T", " ").replace("Z", " UTC"); }
  function liveAge(value) { return el("span", { "data-age": value, class: "live" }, F.describeAge(value, Date.now())); }
  // "22 Sep 2026" (day precision) or "Sep 2026" (month precision), from the cited date only.
  function dayText(date) {
    var parts = String(date).slice(0, 10).split("-");
    var month = MONTHS[Number(parts[1]) - 1] + " " + parts[0];
    return parts.length === 3 ? Number(parts[2]) + " " + month : month;
  }
  function releaseText(release) {
    return dayText(release.date);   // "YYYY-MM-DD" or "YYYY-MM", as validated
  }

  // ------------------------------------------------------------------ data
  var routeById = {};
  D.routes.forEach(function (r) { routeById[r.id] = r; });
  var entries = D.catalog.map(function (e) {
    var copy = {};
    Object.keys(e).forEach(function (k) { copy[k] = e[k]; });
    copy.routes = e.route_ids.map(function (id) { return routeById[id]; }).filter(Boolean);
    return copy;
  });
  var entryById = {};
  entries.forEach(function (e) { entryById[e.id] = e; });
  // Baseline's own tests (T12): admitted daily, quick-check and reference results and one-off setup tests.
  var TESTS = D.baseline_tests || { runs: 0, calibration_runs: 0, entries: {}, methods: [] };
  var METHODS = TESTS.methods || [];
  var modelGroups = Dir.modelGroups(entries, TESTS);
  var groupByEntry = {};
  modelGroups.forEach(function (g) { g.members.forEach(function (e) { groupByEntry[e.id] = g; }); });
  function ownStatus(e) { return Dir.baselineStatus(e, TESTS, Date.now()); }
  function testsOf(e) { return TESTS.entries ? TESTS.entries[e.id] || null : null; }
  function seriesOf(e) { var rec = testsOf(e); return (rec && rec.daily_series) || []; }
  // Measured (9 October 2026): an entry with a scored Baseline result in one of its series (site/measured.js).
  // A schedule, a gap, a partial or error-only run, a one-off setup test, a catalogue listing or a third-party
  // observation is not one. Computed from the admitted results, never from an editorial list.
  function measuredMember(e) { return M.isMeasured(testsOf(e)); }
  // Own records of any kind (a schedule, a one-off setup test or scored results): the entry has its own page,
  // which says exactly what was published. Only scored results put a model in the list and the focus.
  function hasOwnRecords(e) {
    var rec = testsOf(e);
    return !!rec && (seriesOf(e).length > 0 || (rec.calibration || []).length > 0);
  }
  var seriesOwner = {};
  // One entry per measured exact model (a model group). It opens on the route and series holding the model's
  // preferred result: a full 40-question test before a quick check, then the newest result. A route's newer
  // setup without a result never hides an older measured one.
  var measuredModels = modelGroups.map(function (g) {
    var leads = g.members.filter(measuredMember).map(function (member) {
      var list = seriesOf(member), index = M.defaultIndex(list, "");
      list.forEach(function (series) { seriesOwner[series.series_id] = member; });
      return { entry: member, series: list[index], latest: M.latestScored(list[index]) };
    });
    if (!leads.length) return null;
    leads.sort(function (a, b) {
      return (M.isFull(b.series) - M.isFull(a.series)) || (b.latest.at - a.latest.at) || (a.entry.id < b.entry.id ? -1 : 1);
    });
    var top = leads[0];
    return { id: g.id, group: g, entry: top.entry, series: top.series, latest: top.latest, leads: leads,
             name: displayName(g), maker: top.entry.maker,
             exact_identifier: top.entry.exact_identifier, family: top.entry.family,
             service_provider: top.entry.service_provider, access_kind: top.entry.access_kind,
             release: g.canonical.release || top.entry.release };
  }).filter(Boolean);
  var makers = Dir.distinct(measuredModels, "maker");

  // ------------------------------------------------------------------ routing
  var state = Dir.parseState(window.location.hash);

  function go(next, replace) {
    state = next;
    var hash = Dir.encodeState(state);
    if (replace) window.history.replaceState(null, "", hash);
    else window.location.hash = hash;
  }

  // The comparison depends on the clock (the 48-hour rule), so the open page keeps a handle on the two places that
  // show it: the home focus and the model page's caption (review R2). `refreshLive` replaces only what changed.
  var live = { readout: null, kicker: null, moves: null };

  function render(focusHeading) {
    var railScroll = (document.querySelector && document.querySelector(".rail")) ? document.querySelector(".rail").scrollTop : 0;
    live = { readout: null, kicker: null, moves: null, chart: null };
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
        app.appendChild(notFound("That link does not match a model or route on this site."));
        return;
      }
    }
    if (state.view === "model") app.appendChild(modelView());
    else if (state.view === "sources") app.appendChild(sourcesView());
    else if (state.view === "how-we-test") app.appendChild(howView());
    else app.appendChild(directoryView());
    var again = pendingFocus ? document.getElementById(pendingFocus) : null;
    pendingFocus = null;
    if (again) {                                    // a rail or picker selection keeps focus where it was, without
      var rail = document.querySelector && document.querySelector(".rail");   // scrolling the page or the rail
      if (rail && railScroll) rail.scrollTop = railScroll;
      try { again.focus({ preventScroll: true }); } catch (err) { again.focus(); }
      keepHeadingVisible();
    } else if (focusHeading) {
      var h = app.querySelector("h1");
      if (h) { h.setAttribute("tabindex", "-1"); h.focus(); }
    }
    fitChart();
  }

  // After a selection, the new model's name and readout stay in view: if the page was scrolled past the workspace
  // heading, it is brought back to the top of the viewport; otherwise nothing moves.
  function keepHeadingVisible() {
    var h = app.querySelector && app.querySelector("#model-title");
    if (!h || !h.getBoundingClientRect || !window.scrollBy) return;
    var top = h.getBoundingClientRect().top;
    if (top < 0) window.scrollBy(0, top - 12);
  }

  // The graph is laid out at the width it is shown at (review R3), so its labels keep their real size at every
  // screen width; a resize redraws only the graph, keeping the model, setup, view and selected point.
  var resizeTimer = null;
  window.addEventListener("resize", function () {
    if (resizeTimer) window.clearTimeout(resizeTimer);
    resizeTimer = window.setTimeout(fitChart, 150);
  });

  window.addEventListener("hashchange", function () {
    state = Dir.parseState(window.location.hash);
    render(true);
  });

  // ------------------------------------------------------------------ the monitor (11 October 2026)
  // One working surface: the tested models on a rail (one selector on phones) beside one history workspace for the
  // selected model. The home opens on the existing focus choice (site/measured.js); rail links, movement links, deep
  // links and back/forward select a model in the same workspace. Nothing here changes which results count, which
  // comparisons are allowed or how services and test setups are kept apart.
  var chartMode = null;            // the visitor's chosen graph view ("score" or "change"), kept while it is valid
  var pendingFocus = null;         // the rail link or picker to refocus after a selection redraws the page

  function directoryView() { return monitorView(homeSelection()); }

  function notFound(message) { return monitorView({ notFound: message }); }

  // A link to one model and setup that keeps the visitor's rail search, provider and sort (review R2), so choosing a
  // model never resets the list; back and forward restore both, since they live in the same hash.
  function entryLink(e, setup) {
    var g = groupByEntry[e.id];
    return Dir.encodeState({ view: "model", id: g.id, service: e.id, setup: setup || "", route: "", q: state.q || "",
                             provider: state.provider || "", access: "", evidence: "", availability: "",
                             sort: state.sort || Dir.DEFAULT_SORT });
  }

  function accessText(e) {
    var label = Dir.ACCESS_LABELS[e.access_kind] || e.access_kind;
    return e.access_kind === "intermediary" ? label + " (" + e.service_provider + ")" : label;
  }
  // "the Anthropic API", "Puter (a third-party host)", "this app": the service a result or its absence is about.
  function serviceText(e) {
    return e.access_kind === "direct_api" ? "the " + e.service_provider + " API"
      : e.access_kind === "intermediary" ? e.service_provider + " (a third-party host)"
      : e.access_kind === "consumer_app" ? "this app" : accessText(e);
  }
  // The friendliest name the catalogue already gives a model (never invented): a member's display name when it differs
  // from the exact identifier, without its "via <service>" suffix. Exact identifiers stay in the context and details.
  function displayName(g) {
    var friendly = g.members.filter(function (m) { return m.name.replace(/ via \S.*$/, "") !== m.exact_identifier; })
      .map(function (m) { return m.name.replace(/ via \S.*$/, ""); });
    return friendly[0] || g.canonical.name.replace(/ via \S.*$/, "");
  }
  function scoreText(p) { return p.correct + "/" + p.total; }
  function shortDay(date) { var d = String(date).split("-"); return Number(d[2]) + " " + MONTHS[Number(d[1]) - 1]; }
  function kindText(d, e) {
    return isPuter(d) ? "Quick check · " + d.planned_items + " questions · " + e.service_provider
      : isReference(d) ? "Reference test · " + d.planned_items + " questions · " + e.service_provider
      : d.panel_items + " questions · " + (e.access_kind === "direct_api" ? e.service_provider + " API" : e.service_provider);
  }

  function focusModels() {
    return measuredModels.map(function (m) {
      return { id: m.id, measured: m, series: [].concat.apply([], m.leads.map(function (l) { return seriesOf(l.entry); })) };
    });
  }
  function currentFocus() { return M.highlight(focusModels(), Date.now()); }
  // The home opens on the existing choice: the largest eligible recent movement, else the latest (or first) full
  // measurement, else the latest quick check. It is chosen once; a later refresh never moves the selection.
  function homeSelection() {
    var h = currentFocus();
    if (!h) return null;
    var owner = seriesOwner[h.series.series_id];
    return { entry: owner, group: groupByEntry[owner.id], setup: h.series.series_id };
  }

  function monitorView(sel) {
    var moves = el("aside", { class: "rail-moves", "aria-label": "Recent comparable movement" });
    live.moves = { node: moves, key: null };
    drawMoves();
    return el("div", { class: "monitor" }, [moves, railView(sel), workspaceView(sel)]);
  }

  // ---------------------------------------------------------------- the rail
  function railView(sel) {
    var selected = sel && sel.entry && measuredMember(sel.entry) ? sel.group.id : "";
    var rail = el("nav", { class: "rail", "aria-label": "Models tested by Baseline" });
    if (!measuredModels.length) {
      return append(rail, [el("h2", { class: "rail-title" }, "Tested models"), el("p", { class: "rail-count" }, "None yet")]);
    }
    var byName = measuredModels.slice().sort(function (a, b) { return a.name.toLowerCase() < b.name.toLowerCase() ? -1 : 1; });
    // Phones: every tested model, whatever the desktop filters; the link is made when one is chosen.
    var picker = el("select", { id: "model-picker" }, (selected ? [] : [el("option", { value: "" }, "Choose a tested model")])
      .concat(byName.map(function (m) {
        return el("option", { value: m.id },
          m.name + " — " + scoreText(m.latest) + ", " + shortDay(m.latest.date) + (isPuter(m.series) ? " (quick check)" : ""));
      })));
    picker.value = selected || "";
    picker.addEventListener("change", function () {
      var m = byName.filter(function (x) { return x.id === picker.value; })[0];
      if (!m) return;
      pendingFocus = "model-picker";
      window.location.hash = entryLink(m.entry, m.series.series_id);
    });
    var search = el("input", { type: "search", id: "q", name: "q", autocomplete: "off", spellcheck: "false",
                               placeholder: "Search", value: state.q });
    search.value = state.q;
    search.addEventListener("input", function () { update({ q: search.value }); });
    var filters = el("form", { class: "rail-filters", role: "search", "aria-label": "Find tested models" }, [
      el("label", { for: "q", class: "visually-hidden" }, "Search tested models"), search,
      field("provider", "Provider", [["", "All providers"]].concat(makers.map(function (m) { return [m, m]; }))),
      field("sort", "Sort", [["release", "Newest release"], ["name", "Name"], ["provider", "Provider"], ["date", "Latest result"]])
    ]);
    filters.addEventListener("submit", function (ev) { ev.preventDefault(); });
    var status = el("p", { class: "rail-count", role: "status", "aria-live": "polite" });
    var list = el("ul", { class: "rail-list" });
    append(rail, [el("div", { class: "picker" }, [el("label", { for: "model-picker" }, "Model"), picker]),
      el("h2", { class: "rail-title" }, "Tested models"), filters, status, list,
      el("p", { class: "rail-note" }, [SORT_NOTES[state.sort] || SORT_NOTES.release, " Each entry is one exact model " +
        "through one named service; results through different services are never combined."])]);
    drawRail(list, status, selected);

    function field(key, label, options) {
      var id = "f-" + key;
      var node = el("select", { id: id, name: key }, options.map(function (o) { return el("option", { value: o[0] }, o[1]); }));
      node.value = state[key] || (key === "sort" ? Dir.DEFAULT_SORT : "");
      node.addEventListener("change", function () { var patch = {}; patch[key] = node.value; update(patch); });
      return el("div", { class: "field" }, [el("label", { for: id }, label), node]);
    }
    function update(patch) {
      Object.keys(patch).forEach(function (k) { state[k] = patch[k]; });
      state.access = ""; state.evidence = ""; state.availability = "";   // retired filters never linger in links
      go(state, true);
      drawRail(list, status, selected);
      if (live.moves) { live.moves.key = null; drawMoves(); }   // movement links carry the same filters
    }
    return rail;
  }

  function drawRail(list, status, selected) {
    while (list.firstChild) list.removeChild(list.firstChild);
    var shown = Dir.filterEntries(measuredModels, { q: state.q, provider: state.provider,
                                                    sort: state.sort === "date" ? "name" : state.sort }, Date.now());
    if (state.sort === "date") shown.sort(function (a, b) { return b.latest.at - a.latest.at; });   // stable: by name
    var n = measuredModels.length;
    status.textContent = shown.length === n ? n + (n === 1 ? " tested model" : " tested models")
      : shown.length + " of " + n + " tested models";
    if (!shown.length) {
      var clear = el("button", { type: "button", class: "button" }, "Clear search and filters");
      clear.addEventListener("click", function () {
        state.q = ""; state.provider = ""; go(state, true);
        var q = document.getElementById("q"), pv = document.getElementById("f-provider");
        if (q) q.value = "";
        if (pv) pv.value = "";
        drawRail(list, status, selected);
        if (q) q.focus();
      });
      append(list, el("li", { class: "rail-empty" }, [el("p", {}, "No tested model matches your search."), clear]));
      return;
    }
    shown.forEach(function (m) {
      var a = el("a", { href: entryLink(m.entry, m.series.series_id), id: "rail-" + m.id, class: "rail-link" }, [
        el("span", { class: "rail-name" }, m.name),
        el("span", { class: "rail-score" }, [el("strong", {}, scoreText(m.latest)), " · " + shortDay(m.latest.date)]),
        el("span", { class: "rail-kind" }, kindText(m.series, m.entry))]);
      if (m.id === selected) a.setAttribute("aria-current", "true");
      a.addEventListener("click", function () { pendingFocus = a.getAttribute("id"); });
      list.appendChild(el("li", { class: "rail-item" }, a));
    });
  }

  // Recent comparable movements, as links that select that model and setup in the workspace. Shown only when one
  // qualifies (the existing 40-question, consecutive-day, fully gradeable, fresh, latest-attempt rules).
  function drawMoves() {
    var node = live.moves && live.moves.node;
    if (!node) return;
    var moves = M.movements(focusModels(), Date.now());
    var key = moves.map(function (m) { return m.series.series_id + "|" + m.latest.date; }).join(",");
    if (key === live.moves.key) return;
    live.moves.key = key;
    while (node.firstChild) node.removeChild(node.firstChild);
    if (!moves.length) { node.setAttribute("hidden", ""); return; }
    node.removeAttribute("hidden");
    append(node, [el("h2", { class: "rail-title" }, "Recent comparable movement"),
      el("ul", {}, moves.map(function (mv) {
        var owner = seriesOwner[mv.series.series_id], c = mv.comparison;
        var n = c.latest.correct - c.previous.correct;
        return el("li", {}, link(entryLink(owner, mv.series.series_id), mv.model.measured.name + ": " + Chart.signed(n) +
          (Math.abs(n) === 1 ? " correct answer, " : " correct answers, ") + shortDay(c.previous.date) + " to " + shortDay(c.latest.date)));
      })),
      el("p", { class: "rail-note" }, "Change within each model's own test, not a ranking of models.")]);
  }

  // ---------------------------------------------------------------- the workspace
  function workspaceView(sel) {
    var ws = el("section", { class: "workspace", "aria-labelledby": "model-title" });
    if (sel && sel.notFound) {
      return append(ws, [el("h1", { id: "model-title" }, "Not found"), el("p", {}, sel.notFound),
        el("p", {}, link("#models", "See the models Baseline has tested"))]);
    }
    if (!sel) {
      return append(ws, [el("h1", { id: "model-title" }, "No tested models yet"), el("p", { class: "lede" },
        TESTS.calibration_runs ? "Baseline has published only a one-off setup test so far. Models are listed here " +
          "once Baseline publishes repeated test results; the setup test is on its model's page."
        : "Baseline has no scored test result of its own to show yet. A model is listed here once Baseline has a " +
          "scored result for it.")]);
    }
    if (!hasOwnRecords(sel.entry)) return append(ws, unmeasuredContent(sel.entry, sel.group));
    return append(ws, measuredContent(sel.entry, sel.group, sel.setup));
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
                    incomplete: "Incomplete (outcome uncertain)", paused: "Paused (no collection authorized)" };
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
  // "~" also marks a scored run the Change view leaves out (not fully gradeable): visible, selectable, explained.
  var MARK_GLYPHS = { gap: "x", no_record: "x", partial: "~", unavailable: "?", open: "o", pending: "·", failed: "!",
                      not_comparable: "~", paused: "\u2013" };
  var STACKED = 960;               // below this width the rail becomes one selector above the workspace (styles.css)
  // The width the graph is shown at, from the page's own layout: the workspace beside a 240px rail, or the full
  // column when stacked. The SVG is laid out at that size, so 12px labels render at about 12px.
  function plotWidth() {
    var vw = window.innerWidth || 1366;
    var pad = vw <= STACKED ? 12 : Math.min(32, Math.max(12, Math.round(vw * 0.03)));
    var column = Math.min(1280, vw - 2 * pad);
    var width = vw <= STACKED ? column : column - 240 - 28;
    return Math.max(300, Math.round(width - 2));
  }
  function chartSize(width) {
    var w = width || plotWidth();
    return { width: w, height: Math.max(280, Math.min(380, Math.round(w * 0.42))), trim: true };
  }
  // Draws (or redraws) the selected series' graph into its slot, keeping the view and the selected point.
  function drawChart(slot, series, mode, selectedDate, width) {
    while (slot.firstChild) slot.removeChild(slot.firstChild);
    var size = chartSize(width);
    live.chart = { slot: slot, series: series, mode: mode, selected: selectedDate || null, width: size.width };
    slot.appendChild(dailyChart(series, mode, size, selectedDate));
  }
  // After a render or a resize: redraw only when the shown width has really changed.
  function fitChart() {
    var c = live.chart;
    if (!c || !c.slot) return;
    var shown = c.slot.clientWidth ? Math.round(c.slot.clientWidth - 2) : plotWidth();
    if (Math.abs(shown - c.width) > 8) drawChart(c.slot, c.series, c.mode, c.selected, Math.max(300, shown));
  }
  // The graph is the workspace's main visual: about 380px tall on a wide screen and 280px on a phone, drawn at that
  // size so labels stay readable (no sideways scrolling). Score view keeps the full 0 to total scale; Change view
  // (results-chart.js changeLayout) shows correct answers gained or lost since the first fully gradeable result.
  function dailyChart(series, mode, size, selectedDate) {
    var opts = size || chartSize();
    var change = mode === "change" ? Chart.changeLayout(series, opts) : null;
    var lay = change && !change.unavailable ? change : Chart.layout(series, opts);
    var isChange = lay.mode === "change";
    var puter = isPuter(series), reference = isReference(series);
    var detail = el("p", { class: "point-detail", "aria-live": "polite" },
      lay.points.length || lay.marks.length ? "Select a point or mark to see that day's details." : "");
    var svg = s("svg", { class: "chart daily-chart fit", "data-mode": isChange ? "change" : "score",
      viewBox: "0 0 " + lay.width + " " + lay.height, role: "group",
      "aria-label": isChange ? "Change in correct answers out of " + lay.max + " since " + Chart.fullDay(lay.anchor.date) +
        " (" + lay.anchor.correct + " of " + lay.max + "), from " + Chart.signed(-lay.extent) + " to " + Chart.signed(lay.extent) +
        ". " + lay.points.length + " fully gradeable results and " +
        lay.marks.filter(function (m) { return m.kind !== "pending"; }).length + " dates without a change point." : reference ? series.route.label + ", reference evaluations: correct answers out of " + lay.max +
        " by finish date. " + lay.points.length + (lay.points.length === 1 ? " complete evaluation" : " complete evaluations") +
        " and " + lay.marks.length + " without a score." : (puter ? series.route.label + ", small sample of " + lay.max +
        " questions. Model identity not confirmed unless stated per day. " : "") +
        "Daily test scores: correct answers out of " + lay.max + " by test date. " + lay.points.length +
        (lay.points.length === 1 ? " daily score" : " daily scores") + " and " +
        lay.marks.filter(function (m) { return m.kind !== "pending"; }).length + " dates without a score." });
    lay.yTicks.forEach(function (t) {
      svg.appendChild(s("line", { x1: lay.left, x2: lay.right, y1: t.y, y2: t.y, class: t.value === 0 && isChange ? "zero-line" : "gridline" }));
      svg.appendChild(s("text", { x: lay.left - 6, y: t.y + 4, "text-anchor": "end", class: "tick" }, t.label || String(t.value)));
    });
    svg.appendChild(s("line", { x1: lay.left, x2: lay.right, y1: lay.plotBottom, y2: lay.plotBottom, class: "axis" }));
    lay.xTicks.forEach(function (t) {
      var edge = t.x > lay.right - 24 ? "end" : "middle";       // the last date stays inside the plot
      svg.appendChild(s("line", { x1: t.x, x2: t.x, y1: lay.plotBottom, y2: lay.plotBottom + 5, class: "axis" }));
      svg.appendChild(s("text", { x: edge === "end" ? t.x + 4 : t.x, y: lay.plotBottom + 17, "text-anchor": edge }, t.label));
    });
    // The lane label ends before the plot area, so a mark on the first date never runs into it.
    svg.appendChild(s("text", { x: lay.left - 8, y: lay.laneY + 4, "text-anchor": "end", class: "lane-label" },
      isChange ? "not plotted" : "no score"));
    svg.appendChild(s("line", { x1: lay.left, x2: lay.right, y1: lay.laneY - 11, y2: lay.laneY - 11, class: "lane" }));
    (lay.transitions || []).forEach(function (t) {     // a dated schedule change: a new setup, window or a pause
      var line = s("line", { x1: t.x, x2: t.x, y1: lay.top, y2: lay.laneY + 8, class: "transition", "data-date": t.date });
      line.appendChild(s("title", {}, t.label));
      svg.appendChild(line);
    });
    lay.segments.forEach(function (seg) {
      svg.appendChild(s("polyline", { class: "score-line", fill: "none",
        points: seg.map(function (p) { return p.x.toFixed(1) + "," + p.y.toFixed(1); }).join(" ") }));
    });
    // Hover, keyboard focus and touch select the same detail; a selection stays until another is made. The selected
    // point is labelled directly; the latest point always is.
    var selLabel = s("text", { class: "point-label selected-label", "text-anchor": "middle" }, "");
    var selected = null, shows = {};
    function pointText(p) { return isChange ? Chart.signed(p.delta) : p.correct + "/" + lay.max; }
    function selectable(node, label, p) {
      node.setAttribute("tabindex", "0");
      node.setAttribute("role", "button");
      node.setAttribute("aria-label", label);
      node.appendChild(s("title", {}, label));
      function show() {
        detail.textContent = label;
        if (selected) selected.removeAttribute("data-selected");
        selected = node;
        node.setAttribute("data-selected", "true");
        if (live.chart) live.chart.selected = node.getAttribute("data-date");
        if (p && p !== lastPoint) {
          selLabel.setAttribute("x", p.x); selLabel.setAttribute("y", labelY(p)); selLabel.textContent = pointText(p);
        } else selLabel.textContent = "";
      }
      if (node.getAttribute("data-date")) shows[node.getAttribute("data-date")] = show;
      node.addEventListener("click", show);
      node.addEventListener("mouseenter", show);
      node.addEventListener("focus", show);
      node.addEventListener("keydown", function (ev) {
        if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); show(); }
      });
      return node;
    }
    var lastPoint = lay.points.length ? lay.points[lay.points.length - 1] : null;
    function labelY(p) { return p.y - 12 < lay.top + 4 ? p.y + 20 : p.y - 12; }   // never clipped at the top edge
    // Invisible hit areas (review R3): 40px where dates allow, never under 24px, never larger than half the gap to
    // the nearest other date, so crowded dates stay separately selectable. The visible dots keep their size.
    var xs = lay.points.map(function (p) { return p.x; }).concat(lay.marks.filter(function (m) { return m.kind !== "pending"; })
      .map(function (m) { return m.x; })).sort(function (a, b) { return a - b; });
    var gap = Infinity;
    for (var i = 1; i < xs.length; i++) if (xs[i] - xs[i - 1] > 0.5) gap = Math.min(gap, xs[i] - xs[i - 1]);
    var hit = Math.max(12, Math.min(20, Math.floor(gap / 2)));
    lay.marks.forEach(function (m) {
      var g = s("g", { class: "mark", "data-kind": m.kind, "data-date": m.date });
      if (m.kind !== "pending") {
        g.appendChild(s("rect", { x: m.x - hit, y: lay.laneY - 14, width: 2 * hit, height: 28, class: "hit" }));
      }
      g.appendChild(s("text", { x: m.x, y: lay.laneY + 4, "text-anchor": "middle" }, MARK_GLYPHS[m.kind] || "?"));
      svg.appendChild(m.kind === "pending" ? g : selectable(g, m.label));
    });
    lay.points.forEach(function (p) {
      var g = s("g", { class: "score-point" + (isChange && p.date === lay.anchor.date ? " anchor" : ""), "data-date": p.date });
      g.appendChild(s("circle", { cx: p.x, cy: p.y, r: hit, class: "hit" }));
      g.appendChild(s("circle", { cx: p.x, cy: p.y, r: 5, class: "point" }));
      svg.appendChild(selectable(g, p.label, p));
    });
    if (lastPoint) {                                    // the latest result, labelled directly
      var nearRight = lastPoint.x > lay.right - 60;
      svg.appendChild(s("text", { x: lastPoint.x + (nearRight ? -10 : 10), y: labelY(lastPoint), class: "point-label",
        "text-anchor": nearRight ? "end" : "start" }, pointText(lastPoint) + (isChange ? " (" + lastPoint.correct + "/" + lay.max + ")" : "")));
    }
    svg.appendChild(selLabel);
    if (selectedDate && shows[selectedDate]) shows[selectedDate]();   // a redraw keeps the selection (resize, view)
    if (lay.message) {
      svg.appendChild(s("text", { x: (lay.left + lay.right) / 2, y: (lay.top + lay.plotBottom) / 2, "text-anchor": "middle",
                                  class: "chart-message" }, lay.message));
    }
    var legend = isChange ? el("ul", { class: "chart-legend" }, [
      el("li", {}, "● a fully gradeable result: correct answers gained (+) or lost (−) since " + Chart.fullDay(lay.anchor.date) +
        ", when this setup's first fully gradeable result scored " + lay.anchor.correct + " of " + lay.max + ". That first " +
        "result is a reference point, not an established baseline or launch performance."),
      el("li", {}, "The vertical range is symmetric about zero, at least " + Chart.signed(-lay.extent).replace("\u2212", "±") +
        " answers; the score scale in Score view is never cropped."),
      el("li", {}, "~ not plotted: an incomplete run, or a scored run that was not fully gradeable (a refusal, an " +
        "error or an unreadable answer). Its count is in Score view; it is never a change point or the starting point."),
      el("li", {}, "x a missed day, ! a run with no gradeable answer, ? evidence unavailable, o a run still open: no point."),
      el("li", {}, reference ? "Separate evaluations are never joined into a line." : "Lines join consecutive days only.")
    ]) : reference ? el("ul", { class: "chart-legend" }, [
      el("li", {}, "● a complete evaluation: all " + lay.max + " questions answered and gradeable, with no model mismatch, " +
        "placed at its finish date. Separate evaluations are never joined into a line."),
      el("li", {}, "~ a partial, stopped or expired evaluation: shown with its counts, not as a score.")
    ]) : el("ul", { class: "chart-legend" }, [
      el("li", {}, puter ? "● a daily score: all " + lay.max + " questions attempted and gradeable, with no model mismatch. " +
        "Lines join consecutive days only." : "● a daily score: every question attempted. Lines join consecutive days only."),
      el("li", {}, "x a missed day: no run, or nothing recorded."),
      el("li", {}, puter ? "~ a partial or ungradeable run, or a model mismatch: shown with its counts, not as a score."
        : "~ an incomplete run: shown with its attempted count, not as a score."),
      el("li", {}, "? run evidence unavailable: no score shown."),
      el("li", {}, "! a run with no gradeable answer, for example every request failed: a failure, not a score of zero."),
      el("li", {}, "o a run still open or unresolved when last checked: no score yet, not counted as missed."),
      el("li", {}, "· a later date: not yet tested or not yet published.")
    ]);
    return el("figure", { class: "own-chart" }, [
      el("p", { class: "axis-title" }, isChange ? "Change from " + shortDay(lay.anchor.date) + ": " + lay.anchor.correct + "/" +
        lay.max + " · correct answers gained or lost, out of " + lay.max + ", by test date (UTC)"
        : reference ? "Correct answers out of " + lay.max + ", by evaluation finish date (UTC)"
        : puter ? "Correct answers out of " + lay.max + ", by test date (UTC)"
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
    if (isReference(d)) {
      return puterSettingsText(d.settings) + " · " + d.planned_items + " questions in batches of " + d.batch_plan.join(", ") +
        " · " + d.route.label + " through " + d.route.service_provider + " · evaluations " + dayText(d.schedule.start_date) +
        " to " + dayText(d.schedule.end_date) + " · configuration " + String(d.series_fingerprint).slice(0, 8);
    }
    var service = isPuter(d) ? d.route.label + " through " + d.route.service_provider : (e ? accessText(e) : "");
    var config = String(d.config_fingerprint || d.series_fingerprint || "").slice(0, 8);
    var segmented = (d.schedule_segments || []).length > 1;
    return (isPuter(d) ? puterSettingsText(d.settings) : ownSettingsText(d.settings)) + " · " + d.panel_items +
      " questions · " + (service ? service + " · " : "") + "scheduled " + dayText(d.schedule.start_date) + " to " +
      dayText(d.schedule.end_date) + (segmented ? " in " + d.schedule_segments.length + " dated segments, latest daily "
        : ", daily ") + windowText(d.schedule) + (config ? " · configuration " + config : "");
  }
  // The workspace for one model (11 October 2026): its name; test size, date and identity; the latest raw score with
  // the observed change only where the comparison rules allow it; Score and Change views; the graph; a short caveat;
  // then details. One setup at a time; setups and services are never stacked, merged or joined. An explicit ?setup=
  // link is respected; otherwise a full test with a result opens, then a quick check (site/measured.js), so a newer
  // setup without results never hides an older scored one. Other setups and routes are under test details.
  function measuredContent(e, group, setupId) {
    var rec = testsOf(e), list = seriesOf(e);
    var kicker = el("p", { class: "ws-kicker" });
    var body = el("div", { class: "ws-body" });
    var more = el("div", { class: "ws-details" });
    var parts = [kicker, el("h1", { id: "model-title" }, displayName(group)), body, more];
    if (!list.length) {
      append(body, [el("p", { class: "context" }, e.maker + " · " + accessText(e) + " · requested model " + e.exact_identifier),
        el("h2", { id: "our-tests" }, "No repeated test results yet"),
        el("p", {}, "Waiting for daily results. No daily test results have been published for this model yet.")]);
    }
    var seriesDetails = el("div", { class: "series-details" });
    function showSeries(index, fromSelector) {
      if (!Number.isInteger(index) || index < 0 || index >= list.length) return;
      var d = list[index];
      while (body.firstChild) body.removeChild(body.firstChild);
      while (seriesDetails.firstChild) seriesDetails.removeChild(seriesDetails.firstChild);
      var obs = M.observation(d, Date.now());
      var available = M.changeAvailable(d);
      var mode = chartMode === "score" ? "score" : chartMode === "change" ? (available ? "change" : "score")
        : (available ? "change" : "score");
      var chartSlot = el("div", { class: "chart-slot" });
      drawChart(chartSlot, d, mode, null);
      var readout = readoutView(d, obs);
      live.readout = { node: readout, series: d, key: obs ? obs.key : "" };
      live.kicker = { node: kicker, series: d };
      kicker.textContent = kickerText(d);
      append(body, [contextView(e, d, obs), readout,
        modeControls(d, available, mode, function (next) {
          chartMode = next;
          drawChart(chartSlot, d, next, live.chart ? live.chart.selected : null);
        }),
        chartSlot, el("p", { class: "caveat" }, caveatText(d))]);
      var details = el("details", { class: "evidence test-details" }, [
        el("summary", {}, "Test details, other setups and results table")]);
      if (list.length > 1) {
        var selector = el("select", { id: "daily-setup" }, list.map(function (x, i) {
          return el("option", { value: String(i) }, (i === 0 ? "Latest setup" : "Earlier setup") + ": " + setupText(x, e));
        }));
        selector.value = String(index);
        selector.addEventListener("change", function () {
          var i = Number(selector.value);
          go(Object.assign({}, state, { view: "model", id: group.id, service: e.id, setup: list[i].series_id, route: "" }), true);
          showSeries(i, true);
        });
        append(details, el("div", { class: "setup-choice" }, [
          el("label", { for: "daily-setup" }, "Test setup"),
          el("p", { class: "sub" }, "Choose a test setup. Different setups are kept separate and are never joined into one trend."),
          selector]));
      }
      append(details, el("p", { class: "setup-description" }, (list.length > 1 ? "Selected: " : "Setup: ") + setupText(d, e)));
      if (isPuter(d)) append(details, puterLabels(d));
      if (isReference(d)) append(details, referenceLabels(d));
      append(details, [checkedNote(d), isReference(d) ? referenceSection(d) : dailySection(d)]);
      if (isPuter(d)) append(details, el("p", {},
        "Four questions are a small sample and are not comparable with the 40-question tests."));
      append(details, el("p", {}, "These scores describe this fixed test. A rise or fall alone does not establish an " +
        "overall change in model quality. Not enough repeated tests to judge a change."));
      seriesDetails.appendChild(details);
      if (fromSelector) {                               // keep the open disclosure and the focus on the selector
        details.setAttribute("open", "");
        var again = document.getElementById("daily-setup");
        if (again) again.focus();
      }
    }
    if (list.length) showSeries(M.defaultIndex(list, setupId), false);
    append(more, seriesDetails);
    var routes = group.members.filter(measuredMember);
    if (routes.length > 1) {
      var access = el("select", { id: "model-service" }, routes.map(function (member) {
        return el("option", { value: member.id }, member.service_provider + " · " +
          (Dir.ACCESS_LABELS[member.access_kind] || member.access_kind));
      }));
      access.value = e.id;
      access.addEventListener("change", function () {
        pendingFocus = "model-service";
        go(Object.assign({}, state, { view: "model", id: group.id, service: access.value, route: "", setup: "" }), false);
      });
      append(more, el("details", { class: "evidence" }, [el("summary", {}, "Other routes for this model"),
        el("div", { class: "setup-choice" }, [el("label", { for: "model-service" }, "Access route"), access,
          el("p", { class: "sub" }, "Showing results for this route only. Other services may behave differently; their results are kept separate.")])]));
    }
    if ((rec.calibration || []).length) {             // open when it is the only scored result to read
      var setup = el("details", { class: "evidence" }, [el("summary", {}, "One-off setup test")].concat(setupSection(rec.calibration)));
      if (!measuredMember(e)) setup.setAttribute("open", "");
      append(more, setup);
    }
    append(more, el("details", { class: "evidence" }, [el("summary", {}, "Status and how these results were checked"),
      statusBlock(ownStatus(e)),
      el("p", { class: "note" }, ["These counts come from Baseline's private run records. Before publication they were " +
        "checked against stored file hashes, either by a person or automatically under a publication policy a person " +
        "approved. Prompts and raw responses stay private, so individual answers cannot be checked from this page. ",
        link("#how-we-test", "How we test")])]));
    append(more, el("details", { class: "evidence" }, [el("summary", {}, "Model details"), modelFacts(e)]));
    return parts;
  }

  // Why the home opened on this model, while it still applies: the existing focus wording for the shown series.
  function kickerText(d) {
    if (state.view !== "models") return "";
    var h = currentFocus();
    return h && h.series.series_id === d.series_id ? M.HEADINGS[h.kind] : "";
  }

  function contextView(e, d, obs) {
    var identity = isPuter(d) || isReference(d) ? (identityConfirmed(d) ? "model identity reported as requested"
      : "model identity not confirmed") : "";
    var size = isPuter(d) ? "Quick check: " + d.planned_items + " questions"
      : isReference(d) ? "Reference test: all " + d.planned_items + " questions, in batches" : testName(d);
    return el("p", { class: "context" }, [el("span", { class: "test-name" }, size),
      " · through " + serviceText(e) + " · requested model ", el("code", {}, e.exact_identifier),
      obs ? " · latest test " + dayText(obs.latest.date) : " · no scored result yet",
      identity ? [" · ", el("span", { class: "identity" }, identity)] : null]);
  }

  // The latest raw score next to what changed, never only below the graph or in a tooltip.
  function readoutView(d, obs) {
    if (!obs) return el("div", { class: "readout" }, el("p", { class: "observation" }, "No scored result yet in this setup."));
    var later = obs.later && obs.comparison.reason !== "later_attempt"
      ? "A later attempt, on " + dayText(obs.later.date) + ", has no score; the graph shows it." : "";
    return el("div", { class: "readout", "data-change": obs.comparison.eligible ? String(obs.change) : "" }, [
      el("p", { class: "score" }, [el("strong", {}, scoreText(obs.latest)),
        el("span", { class: "score-date" }, "correct · " + shortDay(obs.latest.date))]),
      el("div", { class: "readout-text" }, [
        el("p", { class: "observation" }, obs.text.replace(/\.?$/, ".")),
        obs.caution ? el("p", { class: "caution" }, obs.caution) : null,
        later ? el("p", { class: "caution" }, later) : null])]);
  }

  // Score and Change since first test. Change needs two fully gradeable results in this setup; the control says why
  // when it is unavailable. The visitor's choice is kept across models while it is valid.
  function modeControls(d, available, mode, onChange) {
    var count = M.comparableRows(d).length;
    var buttons = [["score", "Score"], ["change", "Change since first test"]].map(function (m) {
      var b = el("button", { type: "button", class: "mode", "data-mode": m[0], "aria-pressed": String(mode === m[0]) }, m[1]);
      if (m[0] === "change" && !available) {
        b.setAttribute("aria-disabled", "true");
        b.setAttribute("aria-describedby", "change-note");
      }
      b.addEventListener("click", function () {
        if (m[0] === "change" && !available) return;
        buttons.forEach(function (x) { x.setAttribute("aria-pressed", String(x === b)); });
        onChange(m[0]);
      });
      return b;
    });
    return el("div", { class: "modes" }, [el("div", { class: "mode-group", role: "group", "aria-label": "Graph view" }, buttons),
      available ? null : el("p", { id: "change-note", class: "mode-note" }, count === 1
        ? "Change view needs a second fully gradeable result in this setup."
        : "Change view needs two fully gradeable results in this setup; there are none yet.")]);
  }

  function caveatText(d) {
    if (isPuter(d)) {
      return "Quick check: " + d.planned_items + " fixed questions through " + d.route.service_provider + ". A small " +
        "sample, never compared with the 40-question tests or entered in movement highlights.";
    }
    if (isReference(d)) {
      return "All " + d.planned_items + " questions, sent through " + d.route.service_provider + " in batches. " +
        "Separate evaluations are never joined; the service does not confirm which model answered.";
    }
    return "One fixed set of " + d.panel_items + " questions through this route. A difference between tests can be " +
      "ordinary variation; it is not a verdict on the model.";
  }

  // The minute timer and a return to the tab call this. The selected model, setup, view and every control stay; only
  // the readout, the home's reason line and the movement links change, and only when their text would.
  function refreshLive() {
    if (live.readout && live.readout.node.parentNode) {
      var obs = M.observation(live.readout.series, Date.now());
      var key = obs ? obs.key : "";
      if (key !== live.readout.key) {
        var fresh = readoutView(live.readout.series, obs);
        live.readout.node.parentNode.replaceChild(fresh, live.readout.node);
        live.readout = { node: fresh, series: live.readout.series, key: key };
      }
    }
    if (live.kicker) {
      var text = kickerText(live.kicker.series);
      if (text !== live.kicker.node.textContent) live.kicker.node.textContent = text;
    }
    drawMoves();
  }

  // ------------------------------------------------------------------ Puter four-question series
  function isPuter(d) { return d && d.contract === "puter-subset-v1"; }
  function isReference(d) { return d && d.contract === "puter-reference-v1"; }
  // Which test a graph shows: the full reference set, or a separate quick check of a few of its questions.
  // The two are separate tests; a quick-check score is never shown as a share of the full set.
  function testName(d) {
    if (isReference(d)) {
      return "Reference test: all " + d.planned_items + " questions, through " + d.route.service_provider + ", in batches";
    }
    return isPuter(d) ? "Quick check: " + d.planned_items + " of the " + d.parent_panel_items + " reference questions, " +
      "through " + d.route.service_provider : "Reference test: all " + d.panel_items + " questions";
  }
  function puterSettingsText(x) {
    return "Puter SDK " + x.sdk_version + ", provider " + x.provider + ", output limit " + x.max_tokens + " tokens" +
      (x.reasoning_effort ? ", reasoning " + x.reasoning_effort : "") + ", no retries";
  }
  // Confirmed only when every attempted answer of every verified day reported the requested model.
  function identityConfirmed(d) {
    var verified = d.rows.filter(function (row) {        // reference records always carry verified counts
      return row.record && (row.record.evidence === "verified" || isReference(d)) && row.record.attempted; });
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
        : row.state === "paused" ? "no collection was authorized for this date; not a missed day"
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

  // A 40-question reference series (puter-reference-v1): one row per finished evaluation with its real start and
  // finish; partial, stopped and expired evaluations stay visible with their counts, never as scores.
  var EVALUATION_STATE = { complete: "Complete", partial: "Partial", stopped: "Stopped", expired: "Expired" };
  function intervalText(r) {
    var a = r.started_at.slice(0, 10), b = r.finished_at.slice(0, 10);
    return a === b ? dayText(a) + ", " + r.started_at.slice(11, 16) + "–" + r.finished_at.slice(11, 16) + " UTC"
      : dayText(a) + " " + r.started_at.slice(11, 16) + " to " + dayText(b) + " " + r.finished_at.slice(11, 16) + " UTC";
  }
  function referenceLabels(d) {
    return el("div", { class: "puter-labels" }, [
      d.synthetic ? el("p", { class: "notice synthetic", role: "note" }, "Synthetic preview — not real measurements") : null,
      el("p", { class: "labels" }, [el("strong", {}, d.route.label), " · ",
        el("span", { class: "tag", "data-kind": "sample" }, "Reference test: " + d.planned_items + " questions"),
        identityConfirmed(d) ? null : [" · ", el("span", { class: "tag", "data-kind": "identity" }, "Model identity not confirmed")]]),
      el("p", { class: "sub" }, "Requested route through " + d.route.service_provider + " (an intermediary): model " +
        d.route.exact_identifier + ", " + d.route.service_provider + " provider " + d.route.requested_provider + ". All " +
        d.planned_items + " questions of the set " + d.parent_panel_id + ", graded with " + d.grader_version + ", sent in " +
        d.batch_plan.length + " batches that may span hours or days; each evaluation shows when it started and finished. " +
        "These are responses for the requested Puter route, not verified " + d.route.maker + " model performance, and the " +
        "same questions do not make routes a fair ranking. A score needs every question answered; partial, stopped and " +
        "expired evaluations are listed with their counts.")
    ]);
  }
  function referenceSection(d) {
    var rows = d.rows.slice().reverse().map(function (row) {
      var r = row.record, ng = r.not_graded;
      return el("tr", {}, [
        el("td", { "data-label": "Evaluation" }, intervalText(r)),
        el("td", { "data-label": "Result" }, (EVALUATION_STATE[r.status] || r.status) + (row.eligible ? "" : " (not a score)")),
        el("td", { "data-label": "Correct" }, r.correct + " of " + r.planned_items),
        el("td", { "data-label": "Attempted" }, r.attempted + " of " + r.planned_items + ", " + r.not_sent + " not sent"),
        el("td", { "data-label": "Not graded or uncertain" }, String(ng.refusal + ng.error + ng.truncated + ng.missing_text +
          ng.malformed + ng.uncertain) + " (" + ng.uncertain + " uncertain)"),
        el("td", { "data-label": "Model identity" }, r.identity.reported_match === r.attempted && r.attempted
          ? "reported as requested" : "not confirmed (" + r.identity.unknown + " of " + r.attempted + " unknown)"),
        el("td", { "data-label": "Batches" }, String(r.batches))]);
    });
    return [el("p", {}, "Each evaluation sends all " + d.planned_items + " questions once, in batches; a question whose " +
      "outcome is uncertain is never sent again. Published results cover evaluations finished by " + dayText(d.as_of) + "."),
      el("details", { class: "evidence own-table" }, [el("summary", {}, "Evaluations as a table"),
        el("div", { class: "table-scroll" }, el("table", { class: "log own" }, [
          el("caption", {}, "Reference evaluations. Each row is one separate evaluation; rows are not joined into a trend."),
          el("thead", {}, el("tr", {}, ["Evaluation", "Result", "Correct", "Attempted", "Not graded or uncertain",
            "Model identity", "Batches"].map(function (h) { return el("th", { scope: "col" }, h); }))),
          el("tbody", {}, rows)]))])];
  }
  function dailySection(d) {
    var parts = [];
    var sch = d.schedule;
    var end = sch.window_start_utc.split(":").map(Number);
    var closes = end[0] * 60 + end[1] + sch.window_minutes;
    var hhmm = ("0" + Math.floor(closes / 60) % 24).slice(-2) + ":" + ("0" + closes % 60).slice(-2);
    var last = d.rows.length ? d.rows[d.rows.length - 1] : null;
    var segs = d.schedule_segments || [];
    var when = segs.length > 1
      ? "Scheduled in dated segments (the same questions, settings and identity throughout): " + segs.map(function (seg) {
          return dayText(seg.start_date) + " to " + dayText(seg.end_date) + ", " + Chart.segmentText(seg);
        }).join("; ") + ". A paused date is not a missed day."
      : "Scheduled once a day between " + sch.window_start_utc + " and " + hhmm + " UTC, " +
        dayText(sch.start_date) + " to " + dayText(sch.end_date) + ".";
    parts.push(el("p", {}, when + " Published results cover scheduled dates up to " +
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
  function modelView() {
    var e = entryById[state.id];
    if (!e) return notFound("There is no model with the id “" + state.id + "” on this site. It may have been renamed.");
    var group = groupByEntry[e.id];
    // An explicit service or old route link names one member; otherwise the entry itself. Never substituted.
    var chosen = group.members.filter(function (member) { return member.id === state.service; })[0];
    if (chosen) e = chosen;
    else if (state.route) {
      e = group.members.filter(function (member) { return member.route_ids.indexOf(state.route) !== -1; })[0] || e;
    }
    return monitorView({ entry: e, group: group, setup: state.setup });
  }

  // An entry without own records (an old catalogue, app or other-route link): an honest explanation, links to the
  // tested models, and never another model's, service's or app's results in its place.
  function unmeasuredContent(e, group) {
    var others = group.members.filter(function (member) { return member !== e && measuredMember(member); });
    var name = e.access_kind === "consumer_app" ? e.name : displayName(group);
    return [el("p", { class: "context" }, e.maker + " · " + accessText(e)),
      el("h1", { id: "model-title" }, name),
      el("div", { class: "status-block", "data-status": "not_tested" }, [
        el("p", { class: "status-label" }, Dir.STATUS.not_tested),
        el("p", {}, "Baseline has no scored test of " + name + " through " + serviceText(e) + " to show. This site shows " +
          "only Baseline's own measurements; catalogue listings and results published by others are no longer displayed.")]),
      others.length ? el("p", {}, ["Baseline has tested the same requested model through another service. Results " +
        "through different services may differ and are kept separate: ", others.map(function (member, i) {
          return [i ? " · " : "", link(entryLink(member, ""), name + " — " + accessText(member))];
        })]) : null,
      el("p", {}, link("#models", "See the models Baseline has tested")),
      el("details", { class: "evidence" }, [el("summary", {}, "Model details"), modelFacts(e)])];
  }

  function modelFacts(e) {
    return el("dl", { class: "facts" }, [
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
    ]);
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
      el("h2", {}, "Third-party measurement sources (not displayed)"),
      el("p", {}, "Results from these sources were copied earlier and stay in the project's evidence files with " +
        "their attribution. This site shows only Baseline's own measurements, so they are no longer displayed."),
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

  // The 40-question reference method, described only once a reference series is published.
  function referenceMethod() {
    var shown = Object.keys(TESTS.entries || {}).some(function (k) {
      return (TESTS.entries[k].daily_series || []).some(isReference); });
    if (!shown) return null;
    return [el("h2", {}, "Reference tests through Puter"),
      el("ul", {}, [
        el("li", {}, "A reference test sends all 40 questions of the set once, through Puter, in batches that may span " +
          "hours or days. Each evaluation shows when it started and finished."),
        el("li", {}, "No question is sent twice in one evaluation. A question whose outcome is uncertain, such as a lost " +
          "connection, is never resent; it is shown as uncertain and never counted as correct."),
        el("li", {}, "Only finished evaluations are published: complete, partial, stopped (a free-credit limit was " +
          "reached) or expired (the approved period ended). A score needs all 40 questions answered; the others are " +
          "listed with their counts, not as scores."),
        el("li", {}, "Separate evaluations are never joined into a line, and they are kept apart from the four-question " +
          "quick checks. They show responses for the requested Puter route, which does not confirm which model " +
          "answered, so they are not verified model performance.")])];
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
        ? "Baseline publishes results from its own repeated tests of a small set of exact models, and this site " +
          "shows only those. A model without a published Baseline result is not tested by Baseline and is not listed."
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
      referenceMethod(),
      el("h2", {}, "The highlighted movement"),
      el("ul", {}, [
        el("li", {}, "The home page shows the largest observed movement in our latest comparable tests: the biggest " +
          "change, in percentage points, between two complete 40-question results of one model on consecutive UTC " +
          "dates in one unchanged test setup (the same questions, grader, route and settings)."),
        el("li", {}, "The newer result must be no more than 48 hours old, and neither may report a different model " +
          "from the one requested; an unconfirmed identity stays visible. Rises and falls are chosen by the same " +
          "rule. Ties go to the newest result, then to the model's id."),
        el("li", {}, "It describes what we observed on a small fixed test, within one model's own history. It is not " +
          "a statistical test, not a verdict that a model changed, and not a ranking of models against each other. " +
          "Equal scores do not show that a model is stable."),
        el("li", {}, "Without such a pair, the home page shows the latest measurement instead. Four-question quick " +
          "checks and partial, failed, stale or setup-changed runs are never compared.")]),
      el("h2", {}, "Results published by others"),
      el("p", {}, "Earlier versions of this site also listed catalogue entries and showed results published by " +
        "others. It now shows only Baseline's own measurements. The copied third-party records stay in the " +
        "project's evidence files with their sources, but they are not displayed or compared here. A model " +
        "without a Baseline result has missing evidence, not a score of zero."),
      el("h2", {}, "Release dates"),
      el("p", {}, "The list can be sorted by release date. A release date is shown only when a maker's announcement, changelog or model page states it, and each date links to that page. Dates are never guessed from a model's name, from when we checked a page, or from when a test was run. Models without a cited date are listed last."),
      el("h2", {}, "Methods and decisions"),
      el("ul", { class: "plain" }, [
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
    refreshLive();
  }
  window.setInterval(tick, 60000);
  // Timers are slowed in background tabs: a return to the tab refreshes at once.
  if (document.addEventListener) {
    document.addEventListener("visibilitychange", function () { if (!document.hidden) tick(); });
  }
  window.BaselinePage = { tick: tick, state: function () { return state; } };
})();
