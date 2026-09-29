/* Renders window.BASELINE_DATA. All text goes through textContent; ages and the
   chart's "no recorded evidence" band are recomputed from the viewer's clock every minute. */
(function () {
  "use strict";
  var D = window.BASELINE_DATA;
  var F = window.BaselineFreshness;
  var app = document.getElementById("app");
  var SVGNS = "http://www.w3.org/2000/svg";

  if (!D || !F) {
    app.appendChild(el("p", { class: "notice" }, "The data file is missing. Run scripts/build_site.py, then reload."));
    return;
  }

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
  function link(href, text) { return el("a", { href: href, rel: "noopener noreferrer" }, text); }
  function pct(m) { return (100 * m.numerator / m.denominator).toFixed(1) + "%"; }
  function utc(value) { return value.replace("T", " ").replace("Z", " UTC"); }
  function dateText(o) { return o.precision === "day" ? o.observed_at + " (date only)" : utc(o.observed_at); }

  // Live age spans: data-moment holds the timestamp, updated by tick().
  function liveAge(value) { return el("span", { "data-age": value, class: "live" }, F.describeAge(value, Date.now())); }
  function liveStatus(value) {
    var st = F.measurementStatus(value, Date.now());
    return el("span", { class: "badge", "data-status-of": value, "data-status": st.key }, st.label);
  }

  var sources = {};
  D.sources.forEach(function (src) { sources[src.id] = src; });
  var allDates = [];
  D.routes.forEach(function (r) { r.observations.forEach(function (o) { allDates.push(o.observed_at); }); });
  var newestOverall = F.newest(allDates);

  // Hero: the thesis is the age of the newest evidence.
  var numericSources = D.sources.filter(function (x) { return x.reuse_decision === "numeric_republication_permitted"; });
  append(app, [
    el("h1", {}, newestOverall ? ["Newest evidence here is ", liveAge(newestOverall), "."] : "No measurements recorded yet."),
    el("p", { class: "lede" }, [
      "These are historical results published by a third party, copied with permission and linked to the exact source line. ",
      "Baseline has not measured these routes itself and runs no independent tests of any model. " +
      "Figures change only when a listed source publishes results that Baseline then copies."
    ]),
    el("p", { class: "notice" }, [
      el("strong", {}, "Read before comparing. "),
      "Each dot is one run with its own test setup. Runs are never joined into a line, because the test tool, ",
      "its version and the model behind the requested name changed between them. ",
      "A higher or lower dot is not, by itself, evidence that a provider changed a model on purpose."
    ])
  ]);

  // Route index as specimen labels.
  var labels = el("ul", { class: "labels", id: "routes", "aria-label": "Routes" });
  D.routes.forEach(function (r) {
    var dates = r.observations.map(function (o) { return o.observed_at; });
    var newest = F.newest(dates);
    var first = dates.slice().sort()[0];
    labels.appendChild(el("li", { class: "label", "data-status": newest ? F.measurementStatus(newest, Date.now()).key : "unknown", "data-status-of": newest || "" }, [
      el("p", { class: "label-title" }, link("#" + r.id, r.requested_model)),
      el("dl", { class: "fields" }, [
        el("dt", {}, "Provider"), el("dd", {}, r.model.provider + " · " + r.access_type.replace("_", " ")),
        el("dt", {}, "Runs"), el("dd", {}, r.observations.length + " runs in " + r.series.length + " separate setups"),
        el("dt", {}, "Span"), el("dd", {}, first ? first + " → " + newest : "none"),
        el("dt", {}, "Newest"), el("dd", {}, newest ? [liveAge(newest), liveStatus(newest)] : "no measurements"),
        el("dt", {}, "Own testing"), el("dd", {}, "none by Baseline")
      ])
    ]));
  });
  app.appendChild(el("h2", {}, "Routes"));
  app.appendChild(labels);

  D.routes.forEach(function (r) { app.appendChild(routeSection(r)); });
  app.appendChild(sourcesSection());
  app.appendChild(methodsSection());
  app.appendChild(logSection());
  document.body.appendChild(el("footer", {}, [
    "Data built " + utc(D.generated_at) + " from registry schema v" + D.schema_version + ". ",
    "Ages are worked out from your device clock each minute, so they stay current without a rebuild. ",
  ]));

  function routeSection(r) {
    var dates = r.observations.map(function (o) { return o.observed_at; });
    var newest = F.newest(dates);
    var newestObs = r.observations.filter(function (o) { return o.observed_at === newest; })[0];
    var firstRetrieved = r.observations.map(function (o) { return o.retrieved_at; }).sort()[0];
    var src = sources[r.source_ids[0]] || {};
    var sorted = dates.slice().sort();

    var section = el("section", { class: "route", id: r.id, "aria-labelledby": r.id + "-title" }, [
      el("div", { class: "route-head" }, [
        el("h2", { id: r.id + "-title" }, r.requested_model),
        el("span", { class: "muted" }, "requested API model name")
      ]),
      el("p", {}, [
        r.service + ". ",
        "Tier and region are not stated by the source. ",
        Object.keys(r.settings).length ? "Settings: " + JSON.stringify(r.settings) + ". " : "No extra settings recorded. ",
        el("span", { class: "muted" }, "The name may be an alias: the source labels these runs as different models over time.")
      ]),
      el("div", { class: "panel" }, el("dl", { class: "fresh" }, [
        el("div", {}, [el("dt", {}, "Newest measurement"), el("dd", {}, newest ? [
          el("span", { class: "big" }, liveAge(newest)), dateText(newestObs), liveStatus(newest)] : "none")]),
        el("div", {}, [el("dt", {}, "Copied by Baseline"), el("dd", {}, firstRetrieved ? [
          el("span", { class: "big" }, liveAge(firstRetrieved)), utc(firstRetrieved),
          el("br"), el("span", { class: "muted" }, "When we saved the source, not when it was measured.")] : "never")]),
        el("div", {}, [el("dt", {}, "Source last checked"), el("dd", {}, src.last_successful_check ? [
          el("span", { class: "big" }, liveAge(src.last_successful_check)), utc(src.last_successful_check),
          el("br"), el("span", { class: "muted" }, "The latest successful check of the source for new results.")] : "never checked")]),
        el("div", {}, [el("dt", {}, "Independent testing"), el("dd", {}, [
          el("span", { class: "big" }, "None"), "Baseline has not run its own tests on this route."])])
      ])),
      el("h3", {}, "Pass rate by run"),
      el("p", { class: "scroll-hint" }, "Scroll the chart sideways to reach today."),
      el("div", { class: "chart-scroll" }, chart(r)),
      el("p", { class: "chart-caption" }, [
        r.observations.length + " runs between " + sorted[0] + " and " + sorted[sorted.length - 1] + ". ",
        "Longest gap between runs: " + F.longestGapDays(dates) + " days. ",
        "No observations are recorded here between these runs or after the latest one; the hatched band marks that span up to today. " +
        "This covers only the evidence Baseline holds: other measurements may exist elsewhere, and the source may have runs it did not publish."
      ]),
      el("h3", {}, "Runs"),
      el("p", { class: "chart-caption", id: r.id + "-table-note" },
        "Pass rate counts exercises passed within two tries, out of those run. “Not run” counts exercises missing from the run."),
      el("div", { class: "table-scroll" }, table(r)),
      el("h3", {}, "What changed between runs"),
      breaks(r)
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
    // Quarter ticks.
    var d = new Date(t0); d = new Date(Date.UTC(d.getUTCFullYear(), Math.floor(d.getUTCMonth() / 3) * 3 + 3, 1));
    var months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    while (d.getTime() < t1) {
      var tx = x(d.getTime());
      svg.appendChild(s("line", { x1: tx, x2: tx, y1: H - B, y2: H - B + 5, class: "axis" }));
      svg.appendChild(s("text", { x: tx, y: H - B + 18, "text-anchor": "middle" }, months[d.getUTCMonth()] + " " + d.getUTCFullYear()));
      d = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 3, 1));
    }
    svg.appendChild(s("line", { x1: L, x2: W - R, y1: H - B, y2: H - B, class: "axis" }));

    // Span with no observations in this registry, from the latest run to today.
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

    // One dashed break per run (each is its own setup), then the unconnected points.
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
      var cells = [
        el("span", { class: "letter-chip" }, o.series_letter),
        dateText(o),
        o.source_label || "not stated",
        o.metric.numerator + " / " + o.metric.denominator,
        pct(o.metric),
        String(o.exclusions.missing || 0),
        series.harness,
        (sd.edit_format || "not stated"),
        link(o.evidence_url, "source line ↗")
      ];
      var tr = el("tr");
      cells.forEach(function (c, i) {
        tr.appendChild(el("td", { "data-label": head[i], class: i >= 3 && i <= 5 ? "num" : "" }, c));
      });
      tbody.appendChild(tr);
    });
    return el("table", { "aria-describedby": r.id + "-table-note" }, [
      el("thead", {}, el("tr", {}, head.map(function (h) { return el("th", { scope: "col" }, h); }))),
      tbody
    ]);
  }

  function breaks(r) {
    var list = el("ul", { class: "breaks" });
    r.observations.forEach(function (o, i) {
      if (i === 0) return;
      var prev = r.observations[i - 1];
      var items = o.breaks.map(function (b) {
        return el("span", { class: "change" }, b.field + ": " + fmt(b.from) + " → " + fmt(b.to));
      });
      var li = el("li", {}, [el("strong", {}, prev.series_letter + " → " + o.series_letter + ": ")]);
      if (!items.length) append(li, "same setup (runs join one series)");
      items.forEach(function (it, k) { append(li, [k ? "; " : "", it]); });
      list.appendChild(li);
    });
    if (!list.children.length) list.appendChild(el("li", {}, "Only one run; nothing to compare."));
    return list;
  }
  function fmt(v) { return v === null || v === undefined ? "not stated" : typeof v === "object" ? JSON.stringify(v) : String(v); }

  function sourcesSection() {
    var sec = el("section", { class: "section", id: "sources" }, el("h2", {}, "Sources and attribution"));
    D.sources.forEach(function (src) {
      var numeric = src.reuse_decision === "numeric_republication_permitted";
      sec.appendChild(el("div", { class: "source" }, [
        el("h3", {}, [link(src.url, src.author), numeric ? "" : el("span", { class: "badge" }, "link only")]),
        el("p", {}, src.method),
        numeric && src.licence ? el("p", {}, [
          "Numbers reused under the ", link(src.licence.upstream_url, src.licence.name),
          " (", link(src.licence.file, "copy of the licence"), "), from commit ",
          el("code", {}, (src.revision || "").slice(0, 12)), ". Only results are reused; benchmark exercises are not copied."
        ]) : el("p", {}, "No reuse permission for its numbers, so none are shown here. Follow the link to read it at the source."),
        el("p", { class: "muted" }, [
          "Last checked: ", src.last_successful_check ? [utc(src.last_successful_check), " (", liveAge(src.last_successful_check), ")"] : "never",
          ". Update schedule: ", src.expected_update_cadence || "not stated by the source", "."
        ])
      ]));
    });
    return sec;
  }

  function methodsSection() {
    return el("section", { class: "section", id: "methods" }, [
      el("h2", {}, "How to read this"),
      el("ul", {}, [
        el("li", {}, "Each lettered setup is one exact configuration: route, test tool version and commit, edit format and suite size. A different letter means results are not directly comparable, so points are never joined."),
        el("li", {}, "Measured dates are shown as the source gives them. This source gives a date only, with no time or timezone, so ages are about a day either way."),
        el("li", {}, "Freshness labels use the newest measurement's age: Recent up to " + F.RECENT_DAYS + " days, Aging up to " + F.AGING_DAYS + " days, Stale after that. This is a display convention, not a statistical test."),
        el("li", {}, "“Copied by Baseline” is when we saved the source. A copy made today of an old result is still an old result."),
        el("li", {}, "No confidence intervals are shown: the source reports one run per setup, which is not enough to estimate run-to-run variation."),
        el("li", {}, "Rises and falls are shown the same way. Nothing here says whether a provider changed a model deliberately.")
      ])
    ]);
  }

  function logSection() {
    var rows = D.runs.map(function (run) {
      return el("tr", { class: run.superseded ? "superseded-row" : "" }, [
        el("td", { "data-label": "Started" }, utc(run.started_at)),
        el("td", { "data-label": "Source" }, run.source_id),
        el("td", { "data-label": "Result" }, run.superseded ? el("span", { class: "superseded" }, run.status) : run.status),
        el("td", { "data-label": "Problems" }, run.problem_types.join(", ") || "none"),
        el("td", { "data-label": "Note" }, run.superseded ? "Superseded development run; its records were replaced before first commit." : "")
      ]);
    });
    return el("section", { class: "section", id: "log" }, el("details", {}, [
      el("summary", {}, "Ingestion log (" + D.runs.length + " runs, " + D.runs.filter(function (x) { return x.status === "failed"; }).length + " failed)"),
      el("p", { class: "muted" }, "Every attempt to copy a source is kept, including failures. Superseded runs stay listed but are not evidence."),
      el("div", { class: "table-scroll" }, el("table", { class: "log" }, [
        el("thead", {}, el("tr", {}, ["Started", "Source", "Result", "Problems", "Note"].map(function (h) { return el("th", { scope: "col" }, h); }))),
        el("tbody", {}, rows)
      ]))
    ]));
  }

  // Keep ages, badges and the no-recorded-evidence band current.
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
    D.routes.forEach(function (r) {
      var old = document.querySelector('[data-chart-for="' + r.id + '"]');
      if (old) old.parentNode.replaceChild(chart(r), old);
    });
  }
  window.setInterval(tick, 60000);
  window.BaselinePage = { tick: tick };
})();
