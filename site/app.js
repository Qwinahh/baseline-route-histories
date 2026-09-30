/* Baseline: model directory, model detail, sources and about views (T07).
   Renders window.BASELINE_DATA. All text goes through textContent. Ages, badges and the
   chart's "no recorded evidence" band are recomputed from the viewer's clock every minute.
   URL state lives in the hash (site/directory.js), so back/forward and shared links work. */
(function () {
  "use strict";
  var D = window.BASELINE_DATA;
  var F = window.BaselineFreshness;
  var Dir = window.BaselineDirectory;
  var app = document.getElementById("app");
  var SVGNS = "http://www.w3.org/2000/svg";
  var REPO = "https://github.com/Qwinahh/baseline-route-histories/blob/main/";
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

  if (!D || !F || !Dir) {
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
    else if (state.view === "about") app.appendChild(aboutView());
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
        el("h1", { id: "directory-title" }, "Find your model. Follow its history."),
        el("p", { class: "lede" }, [
          entries.length + " model and app entries from " + makers.length + " makers. " +
          measured.length + " have dated measurements from the third-party sources listed under Sources, each shown with its measurement date. " +
          "Baseline runs no independent tests of any model."
        ])
      ]),
      el("pre", { class: "ascii", "aria-hidden": "true" }, ASCII)
    ]));

    var search = el("input", { type: "search", id: "q", name: "q", autocomplete: "off", spellcheck: "false",
                               placeholder: "Search models or providers", value: state.q });
    search.value = state.q;
    var controls = el("form", { class: "controls", role: "search", "aria-label": "Find models" }, [
      el("div", { class: "search" }, [el("label", { for: "q" }, "Search"), search]),
      filterPanel([
        select("provider", "Provider", [["", "All makers"]].concat(makers.map(function (m) { return [m, m]; }))),
        select("access", "Access", [["", "All access types"]].concat(Object.keys(Dir.ACCESS_LABELS).filter(function (k) {
          return entries.some(function (e) { return e.access_kind === k; });
        }).map(function (k) { return [k, Dir.ACCESS_LABELS[k]]; }))),
        select("evidence", "Evidence", [["", "Any evidence"], ["measured", "Has measurements"], ["none", "No measurements"]]),
        select("availability", "Availability", [["", "Any availability"], ["available", "Available"],
                                                ["retired", "Retired"], ["unknown", "Unknown"]]),
        select("sort", "Sort", [["name", "Name (A–Z)"], ["provider", "Maker"], ["date", "Newest measurement"]])
      ])
    ]);
    controls.addEventListener("submit", function (ev) { ev.preventDefault(); });
    search.addEventListener("input", function () { update({ q: search.value }); });
    var status = el("p", { class: "result-count", role: "status", "aria-live": "polite" });
    var results = el("div", { class: "results" });
    append(wrap, [controls, status, results]);
    append(wrap, el("p", { class: "fine" }, [
      "Consumer apps (" + counts.apps + ") are listed separately from APIs; API results are never shown as app results. ",
      "Coverage is limited to the sources listed under ", link("#sources", "Sources"), ". This is not an exhaustive list."
    ]));
    drawResults(results, status);

    // One labelled disclosure: open on wide screens or when a filter is set (small screens
    // keep results near the top).
    function filterPanel(fields) {
      var active = ["provider", "access", "evidence", "availability"].some(function (k) { return state[k]; }) || state.sort !== "name";
      var wide = window.matchMedia ? window.matchMedia("(min-width: 721px)").matches : true;
      var panel = el("details", { class: "filter-panel" }, [el("summary", {}, "Filters and sorting"), el("div", { class: "filters" }, fields)]);
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
      node.value = state[key] || (key === "sort" ? "name" : "");
      node.addEventListener("change", function () { var patch = {}; patch[key] = node.value; update(patch); });
      return el("div", { class: "field" }, [el("label", { for: id }, label), node]);
    }
    function update(patch) {
      Object.keys(patch).forEach(function (k) { state[k] = patch[k]; });
      go(state, true);
      drawResults(results, status);
    }
    return wrap;
  }

  function drawResults(results, status) {
    while (results.firstChild) results.removeChild(results.firstChild);
    var list = Dir.filterEntries(entries, state, Date.now());
    status.textContent = list.length === 1 ? "1 entry" : list.length + " entries";
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
                  ["Model / version", "Maker", "Access", "Evidence"].map(function (h) { return el("span", {}, h); }));
    var ul = el("ul", { class: "rows", "aria-label": "Models" });
    list.forEach(function (e) {
      var cov = Dir.coverage(e, Date.now());
      var target = Dir.encodeState({ view: "model", id: e.id, route: "", q: state.q, provider: state.provider,
                                     access: state.access, evidence: state.evidence,
                                     availability: state.availability, sort: state.sort });
      ul.appendChild(el("li", { class: "row" }, [
        el("span", { class: "cell name" }, [link(target, e.name),
          e.identity_kind === "exact" ? null : el("span", { class: "sub" }, e.identity_kind === "automatic"
            ? "model chosen by the app" : "family entry, exact version not verified")]),
        el("span", { class: "cell", "data-label": "Maker" }, [e.maker,
          e.access_kind === "intermediary" ? el("span", { class: "sub" }, "via " + e.service_provider) : null]),
        el("span", { class: "cell", "data-label": "Access" }, Dir.ACCESS_LABELS[e.access_kind] || e.access_kind),
        el("span", { class: "cell", "data-label": "Evidence" }, [
          el("span", { class: "tag", "data-kind": cov.kind }, cov.label),
          cov.newest ? el("span", { class: "sub" }, "newest " + cov.newest) : null])
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

  function modelView() {
    var e = entryById[state.id];
    if (!e) return notFound("There is no entry with the id “" + state.id + "”. It may have been renamed.");
    var routes = e.routes.slice().sort(function (a, b) { return settingsText(a.settings) < settingsText(b.settings) ? -1 : 1; });
    var route = routes.filter(function (r) { return r.id === state.route; })[0] || routes[0];
    var wrap = el("article", { class: "detail", "aria-labelledby": "model-title" }, backLink());
    append(wrap, el("header", { class: "identity" }, [
      el("p", { class: "eyebrow" }, e.maker + " · " + (Dir.ACCESS_LABELS[e.access_kind] || e.access_kind)),
      el("h1", { id: "model-title" }, e.name),
      el("dl", { class: "facts" }, [
        el("dt", {}, "Identity"), el("dd", {}, e.identity_kind === "exact" ? el("code", {}, e.exact_identifier)
          : e.identity_kind === "automatic" ? "Chosen by the app; not an exact model version" : "Family entry; exact version not verified"),
        el("dt", {}, "Service"), el("dd", {}, e.service_provider + (e.access_kind === "intermediary" ? " (made by " + e.maker + ")" : "")),
        el("dt", {}, "Availability"), el("dd", {}, e.availability === "unknown" ? "Unknown" : e.availability === "retired" ? "Retired" : "Available"),
        el("dt", {}, "Listed from"), el("dd", {}, e.sources.map(function (src, i) {
          return [i ? " · " : "", link(src.url, src.claim), el("span", { class: "sub" }, " (checked " + src.checked_at.slice(0, 10) + ")")];
        }))
      ]),
      e.notes ? el("p", { class: "note" }, e.notes) : null
    ]));
    if (!route) {
      append(wrap, el("section", { class: "panel none" }, [
        el("h2", {}, "No measurements recorded here"),
        el("p", {}, e.access_kind === "consumer_app"
          ? "Baseline holds no reusable measurements of this app. Results for the maker's API models are listed as separate entries and are never shown as app results."
          : "Baseline holds no reusable measurements for this entry. That is missing evidence, not a score of zero and not evidence of stability."),
        el("p", {}, "Baseline has not run its own tests on this route.")
      ]));
      return wrap;
    }
    if (routes.length > 1) {
      var nav = el("nav", { class: "routes", "aria-label": "Setup" }, el("span", { class: "label" }, "Setup:"));
      routes.forEach(function (r) {
        var target = Dir.encodeState({ view: "model", id: e.id, route: r.id, q: state.q, provider: state.provider,
                                       access: state.access, evidence: state.evidence, availability: state.availability, sort: state.sort });
        var a = link(target, settingsText(r.settings));
        if (r === route) a.setAttribute("aria-current", "true");
        nav.appendChild(a);
      });
      append(wrap, nav);
    }
    append(wrap, history(route));
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
            : "The latest successful check of the source for new results.")] : "never checked")]),
        el("div", {}, [el("dt", {}, "Independent testing"), el("dd", {}, [
          el("span", { class: "big" }, "None"), "Baseline has not run its own tests on this route."])])
      ])),
      el("div", { class: "limits", role: "note" }, [
        el("strong", {}, "Read before comparing. "),
        "These results come from " + (src.author || "a third-party source") + ", measured through " +
        r.service.split(",")[0] + ", not by Baseline. " + AGE_NOTE[F.measurementStatus(newest, Date.now()).key] + " " +
        r.observations.length + (r.observations.length === 1 ? " run" : " runs") +
        " recorded; each lettered setup is a separate configuration, so points are never joined into a trend."
      ]),
      el("h2", {}, "Pass rate by run"),
      el("p", { class: "scroll-hint" }, "Scroll the chart sideways to reach today."),
      el("div", { class: "chart-scroll" }, chart(r)),
      el("p", { class: "caption" }, [
        r.observations.length + (r.observations.length === 1 ? " run on " + sorted[0] + ". " :
          " runs between " + sorted[0] + " and " + sorted[sorted.length - 1] + ". Longest gap between runs: " +
          F.longestGapDays(dates) + " days. "),
        "No observations are recorded here between these runs or after the latest one; the hatched band marks that span up to today. " +
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
    var months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    while (d.getTime() < t1) {
      var tx = x(d.getTime());
      svg.appendChild(s("line", { x1: tx, x2: tx, y1: H - B, y2: H - B + 5, class: "axis" }));
      svg.appendChild(s("text", { x: tx, y: H - B + 18, "text-anchor": "middle" }, months[d.getUTCMonth()] + " " + d.getUTCFullYear()));
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
      e.sources.forEach(function (src) {
        if (/github\.com\/Aider-AI/.test(src.url)) return;
        (byMaker[e.maker] = byMaker[e.maker] || {})[src.url] = src.checked_at;
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
      el("p", {}, "Model and app entries were taken from each maker's official model listing. A listing shows what exists, not how a model performs."),
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

  function aboutView() {
    return el("section", { class: "page", "aria-labelledby": "about-title" }, [
      el("h1", { id: "about-title" }, "About Baseline"),
      el("p", {}, "Baseline is a directory of AI models and the ways people use them, with dated, source-linked measurement history where reusable evidence exists."),
      el("h2", {}, "How to read this"),
      el("ul", {}, [
        el("li", {}, "Apps, direct APIs, third-party hosts and open weights are separate entries. A measurement belongs only to the exact route it was taken on."),
        el("li", {}, "Each lettered setup is one exact configuration: route, settings, test tool version and commit, edit format and suite size. Different setups are not directly comparable, so points are never joined."),
        el("li", {}, "Measured dates are shown as the source gives them. This source gives a date only, with no time or timezone, so ages are about a day either way."),
        el("li", {}, "Freshness labels use the newest measurement's age: Recent up to " + F.RECENT_DAYS + " days, Aging up to " + F.AGING_DAYS + " days, Stale after that. This is a display convention, not a statistical test."),
        el("li", {}, "“Copied by Baseline” is when we saved the source. A copy made today of an old result is still an old result."),
        el("li", {}, "No confidence intervals are shown: the source reports one run per setup, which is not enough to estimate run-to-run variation."),
        el("li", {}, "Rises and falls are shown the same way. Nothing here says whether a provider changed a model deliberately."),
        el("li", {}, "An entry with no measurements has missing evidence, not a score of zero.")
      ]),
      el("h2", {}, "Methods and decisions"),
      el("ul", { class: "plain" }, [
        el("li", {}, link(REPO + "docs/AIDER_ROUTE_REVIEW.md", "Which benchmark rows are included, and why others are excluded")),
        el("li", {}, link(REPO + "docs/CATALOG_SOURCES.md", "How the model list was checked")),
        el("li", {}, link(REPO + "docs/SOURCES.md", "Source reuse permissions")),
        el("li", {}, link(REPO + "docs/DATA_CONTRACT.md", "Data rules"))
      ])
    ]);
  }

  // ------------------------------------------------------------------ start
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
