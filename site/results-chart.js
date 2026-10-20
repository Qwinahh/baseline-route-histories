/* Baseline's own daily test scores: pure graph layout (T13). No DOM, no fetching, no verdicts.
   Browser global BaselineResultsChart; CommonJS for Node tests.

   One layout per daily series (one fixed test setup). Calendar dates run along x with
   spacing by elapsed days across the whole scheduled campaign; y is the full 0 to
   panel_items scale (never cropped). Only eligible rows (verified, completed, every
   question attempted) become points. A line joins two points only on consecutive
   calendar days of the same series; any gap, missing record, partial or unavailable
   result breaks it. Rows without a score are marks in a separate "no score" lane, so
   they can never be read as a zero. Nothing is interpolated or carried forward.

   changeLayout (the monitor, 11 October 2026): the same dates and marks, with each fully gradeable result drawn as
   its correct count minus the first fully gradeable result's (the anchor, labelled with its date and score). The
   vertical range is symmetric about a zero line: at least plus or minus a tenth of the panel (4 answers of 40, 1 of 4),
   widened symmetrically to fit larger differences, with signed integer ticks. A scored run that is not fully
   gradeable is a mark, never a change point or the anchor. Lines still join consecutive days only.

   opts.trim (the measured site, 9 October 2026): the x axis ends at the latest checked date (the newest row or
   as_of, at least a week after the start) instead of the campaign's last scheduled date, so recorded history
   fills the graph. Later scheduled dates are not drawn; the page lists how many are not yet due.

   Puter four-question series (contract puter-subset-v1): the scale is 0 to 4, a point needs all
   four questions attempted and gradeable with no identity mismatch, and every description says
   whether the returned model identity was confirmed. Grading and identity stay separate. */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.BaselineResultsChart = factory();
})(this, function () {
  "use strict";
  var DAY_MS = 86400000;
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  var MARK_LABELS = {
    gap: "Missed: no run took place (recorded gap)",
    no_record: "Missed: nothing was recorded for this date",
    partial: "Incomplete run: not every question was attempted",
    unavailable: "Run evidence unavailable: no score shown",
    open: "Run still open or unresolved when last checked: no score yet",
    pending: "Not yet tested or not yet published",
    failed: "Run finished without a gradeable answer (every question failed or was not answered): no score shown",
    not_comparable: "Scored, but not every answer was gradeable or the returned model differed: not a change point",
    paused: "Paused: no collection was authorized for this date (not a missed day)"
  };
  var REQUEST_ERRORS = ["timeout", "provider_error", "rate_limited", "auth_error", "client_error"];
  var ANSWER_PROBLEMS = ["truncated", "empty", "malformed", "answered_identity_mismatch", "answered_identity_unknown"];

  function dayNumber(date) {
    return Math.round(Date.parse(String(date).slice(0, 10) + "T00:00:00Z") / DAY_MS);
  }
  function dayLabel(date) {
    var p = String(date).slice(0, 10).split("-");
    return Number(p[2]) + " " + MONTHS[Number(p[1]) - 1];
  }
  function fullDay(date) {
    return dayLabel(date) + " " + String(date).slice(0, 4);
  }
  function sum(o, keys) {
    return keys.reduce(function (n, k) { return n + ((o && o[k]) || 0); }, 0);
  }

  // Gradeable answers: correct, incorrect or wrong format (review R1); refusals and failures are not.
  function gradeable(r) {
    var o = r.first_attempt_outcomes;
    if (o) return (o.correct || 0) + (o.incorrect || 0) + (o.format_error || 0);
    return typeof r.answered === "number" ? r.answered : 0;
  }

  // Row kind for drawing: "point" or one of the MARK_LABELS keys. An eligible run with no gradeable answer is a
  // failure (for example every request failed), never a score of zero; forty wrong answers stay a real zero.
  function rowKind(row) {
    if (row.eligible) return row.record && gradeable(row.record) === 0 ? "failed" : "point";
    if (row.state === "gap") return "gap";
    if (row.state === "open") return "open";
    if (row.state === "paused") return "paused";             // dated schedule segments: never a missed day
    if (row.state === "no_record" || !row.record) return "no_record";
    if (row.record.evidence !== "verified" && !row.record.started_at) return "unavailable";   // reference: always counted
    return "partial";
  }

  function windowText(seg) {
    var start = seg.window_start_utc.split(":").map(Number);
    var closes = start[0] * 60 + start[1] + seg.window_minutes;
    return seg.window_start_utc + "\u2013" + ("0" + Math.floor(closes / 60) % 24).slice(-2) + ":" +
      ("0" + closes % 60).slice(-2) + " UTC";
  }
  // Where a dated schedule changes (a new configuration, window or a pause), from the series' own segments.
  function segmentText(seg) {
    return seg.state === "pause" ? "paused, no collection authorized"
      : "daily " + windowText(seg) + (seg.configuration ? ", configuration " + seg.configuration : "");
  }

  function puterDetails(r, out) {
    var ng = r.not_graded, id = r.identity;
    out.puter = true;
    if (r.started_at) out.interval = [r.started_at, r.finished_at];   // a reference evaluation's real interval
    out.correct = r.correct;
    out.scheduled = r.planned_items;
    out.attempted = r.attempted;
    out.answered = r.answered;
    out.refusals = ng.refusal;
    out.request_errors = ng.error;
    out.answer_problems = ng.truncated + ng.missing_text + ng.malformed + ng.uncertain;
    out.identity_confirmed = id.reported_match === r.attempted && r.attempted > 0;
    out.identity_mismatch = id.mismatch;
    return out;
  }

  // Every question graded and no returned-model mismatch: a result the Change view may plot.
  function fullyGraded(r, max) {
    if (!r) return false;
    var mismatch = r.identity ? r.identity.mismatch : (r.first_attempt_outcomes || {}).answered_identity_mismatch;
    return gradeable(r) === max && !mismatch;
  }

  function details(row) {
    var r = row.record;
    var kind = rowKind(row);
    var out = { date: row.date, kind: kind, status: row.state };
    if (r && (r.evidence === "verified" || r.started_at) && r.record_version !== undefined) return puterDetails(r, out);
    if (r && r.evidence === "verified") {
      var o = r.first_attempt_outcomes;
      out.correct = r.first_attempt_correct;
      out.scheduled = r.scheduled_items;
      out.attempted = r.attempted_items;
      out.refusals = o.refusal || 0;
      out.request_errors = sum(o, REQUEST_ERRORS);
      out.answer_problems = sum(o, ANSWER_PROBLEMS);
      out.retry_correct = r.retry_recovered ? r.retry_recovered.correct : 0;
    }
    return out;
  }

  function identityText(d) {
    if (d.identity_mismatch) return "the returned model differed from the requested model for " + d.identity_mismatch +
      (d.identity_mismatch === 1 ? " answer" : " answers");
    return d.identity_confirmed ? "returned model reported as requested" : "Model identity not confirmed";
  }

  function intervalHead(d) {
    var a = d.interval[0], b = d.interval[1];
    return "Evaluation " + fullDay(a.slice(0, 10)) + " " + a.slice(11, 16) + " to " +
      (a.slice(0, 10) === b.slice(0, 10) ? "" : fullDay(b.slice(0, 10)) + " ") + b.slice(11, 16) + " UTC: ";
  }

  function describePuter(d, head) {
    if (d.interval) head = intervalHead(d);
    var counts = d.refusals + " refused, " + d.request_errors + " errors" +
      (d.answer_problems ? ", " + d.answer_problems + " cut off, missing or unreadable" : "");
    if (d.kind === "point") {
      return head + d.correct + " of " + d.scheduled + " correct; all " + d.attempted + " questions attempted; " +
        counts + "; " + identityText(d) + ".";
    }
    return head + "not plotted as a daily score (" + d.status + "): " + d.attempted + " of " + d.scheduled +
      " questions attempted, " + d.answered + " gradeable, " + d.correct + " of " + d.scheduled + " correct; " +
      counts + "; " + identityText(d) + ".";
  }

  // Plain sentence for screen readers and the details panel. Never a verdict.
  function describe(d) {
    var head = fullDay(d.date) + ": ";
    if (d.puter) return describePuter(d, head);
    if (d.kind === "point") {
      return head + d.correct + " of " + d.scheduled + " correct on the first attempt; all " + d.attempted +
        " questions attempted; " + d.refusals + " refused, " + d.request_errors + " request errors" +
        (d.answer_problems ? ", " + d.answer_problems + " cut off or unreadable" : "") +
        (d.retry_correct ? "; " + d.retry_correct + " more correct on a retry (not counted)" : "") + ".";
    }
    if (d.kind === "failed") {
      return head + "no gradeable answer: " + d.request_errors + " request errors, " + d.refusals + " refused" +
        (d.answer_problems ? ", " + d.answer_problems + " cut off, missing or unreadable" : "") + ". Not plotted as a score.";
    }
    if (d.kind === "partial") {
      return head + "incomplete run (" + d.status + "): " + d.attempted + " of " + d.scheduled +
        " questions attempted, " + d.correct + " correct. Not plotted as a daily score.";
    }
    return head + MARK_LABELS[d.kind] + ".";
  }

  function niceStep(max) {
    if (max <= 5) return 1;
    if (max <= 10) return 2;
    if (max <= 25) return 5;
    if (max <= 50) return 10;
    return Math.ceil(max / 5 / 10) * 10;
  }

  function layout(series, opts) {
    opts = opts || {};
    var W = opts.width || 720, H = opts.height || 250;
    var L = 58, R = 16, T = 18, B = 62;                 // left room for the "no score" lane label; bottom for dates and lane
    var max = series.panel_items;
    var first = dayNumber(series.schedule.start_date), last = dayNumber(series.schedule.end_date);
    if (opts.trim) {
      var seen = (series.rows || []).reduce(function (n, row) { return Math.max(n, dayNumber(row.date)); }, first);
      if (series.as_of) seen = Math.max(seen, dayNumber(series.as_of));
      last = Math.min(last, Math.max(seen, first + 6));
    }
    var endDate = new Date(last * DAY_MS).toISOString().slice(0, 10);
    var span = Math.max(last - first, 1);
    var plotBottom = H - B;
    function x(date) { return L + (dayNumber(date) - first) / span * (W - L - R); }
    function y(score) { return T + (1 - score / max) * (plotBottom - T); }

    var step = niceStep(max), yTicks = [];
    for (var v = 0; v < max; v += step) yTicks.push({ value: v, y: y(v) });
    yTicks.push({ value: max, y: y(max) });

    // Weekly date ticks; a trimmed axis spaces them to fit its width (about 64px per label) so short histories show
    // their days without labels running into each other.
    var every = 7;
    if (opts.trim) {
      var fit = Math.max(2, Math.floor((W - L - R) / 64));
      every = [1, 2, 3, 7, 14, 28].filter(function (n) { return Math.floor((last - first) / n) + 1 <= fit; })[0] || 28;
    }
    var xTicks = [];
    for (var n = first; n <= last; n += every) {
      var iso = new Date(n * DAY_MS).toISOString().slice(0, 10);
      xTicks.push({ date: iso, x: x(iso), label: dayLabel(iso) });
    }
    if (xTicks[xTicks.length - 1].date !== endDate && last - first >= 4) {
      var room = opts.trim ? Math.max(2, Math.ceil(every / 2)) : 3;
      if (last - dayNumber(xTicks[xTicks.length - 1].date) < room) xTicks.pop();   // never two labels on top of each other
      xTicks.push({ date: endDate, x: x(endDate), label: dayLabel(endDate) });
    }

    var points = [], marks = [], segments = [], current = null, previous = null;
    (series.rows || []).forEach(function (row) {
      var d = details(row);
      d.x = x(row.date);
      d.label = describe(d);
      d.fullyGraded = d.kind === "point" && fullyGraded(row.record, max);
      if (d.kind === "point") {
        d.y = y(d.correct);
        points.push(d);
        if (current && previous === dayNumber(row.date) - 1) current.push(d);
        else { current = [d]; segments.push(current); }
        previous = dayNumber(row.date);
      } else {
        marks.push(d);
        current = null; previous = null;              // any non-point row breaks the line
      }
    });
    (series.pending_dates || []).forEach(function (date) {
      if (dayNumber(date) > last) return;                 // beyond a trimmed axis: listed on the page, not drawn
      marks.push({ date: date, kind: "pending", x: x(date), label: fullDay(date) + ": " + MARK_LABELS.pending + "." });
    });
    marks.sort(function (a, b) { return a.date < b.date ? -1 : a.date > b.date ? 1 : 0; });
    var transitions = (series.schedule_segments || []).slice(1).filter(function (seg) {
      return dayNumber(seg.start_date) <= last;
    }).map(function (seg) {
      return { date: seg.start_date, x: x(seg.start_date) - (W - L - R) / span / 2, state: seg.state,
               label: "From " + fullDay(seg.start_date) + ": " + segmentText(seg) + "." };
    });

    var puter = series.contract === "puter-subset-v1";
    var reference = series.contract === "puter-reference-v1";
    if (reference) segments = [];                     // separate evaluations are never joined into a line
    var message = points.length === 0 ? (reference ? "No complete reference evaluation yet" : puter ? "No daily results yet"
      : "Waiting for daily results")
      : points.length === 1 ? (puter || reference ? "Not enough history to show change"
        : "One daily test; more days are needed to show a pattern")
      : null;
    return {
      width: W, height: H, left: L, right: W - R, top: T, plotBottom: plotBottom, laneY: plotBottom + 40,
      max: max, yTicks: yTicks, xTicks: xTicks, points: points,
      segments: segments.filter(function (s) { return s.length > 1; }),
      marks: marks, transitions: transitions, message: message, MARK_LABELS: MARK_LABELS
    };
  }

  // Pointer targets for the selectable dates of a graph (page audit, 21 October 2026): one vertical band per date,
  // split at the midpoints between neighbouring dates, at most `half` px either side of its date and inside
  // [lo, hi]. Bands never overlap, whatever the width; where dates are closer than a comfortable target, the page
  // also offers Previous/Next test buttons and arrow keys (an equivalent control), never smaller hidden circles.
  function hitRegions(xs, lo, hi, half) {
    half = half || 20;
    var sorted = xs.slice().sort(function (a, b) { return a - b; });
    return sorted.map(function (x, i) {
      var left = i ? (sorted[i - 1] + x) / 2 : lo, right = i < sorted.length - 1 ? (x + sorted[i + 1]) / 2 : hi;
      return { x: x, x0: Math.max(left, x - half, lo), x1: Math.min(right, x + half, hi) };
    });
  }

  function signed(n) { return n > 0 ? "+" + n : n < 0 ? "\u2212" + Math.abs(n) : "0"; }

  // The Change view of a series: { unavailable: reason } with fewer than two fully gradeable results, otherwise the
  // score layout's dates and marks with change points, signed ticks, the zero line and the anchor.
  function changeLayout(series, opts) {
    var lay = layout(series, opts);
    var max = series.panel_items;
    var graded = lay.points.filter(function (p) { return p.fullyGraded; });
    if (graded.length < 2) {
      return { unavailable: graded.length === 1 ? "one" : "none", count: graded.length };
    }
    var anchor = graded[0];
    var deltas = graded.map(function (p) { return p.correct - anchor.correct; });
    var extent = Math.max(Math.max(1, Math.round(max / 10)), Math.max.apply(null, deltas.map(Math.abs)));
    var T = lay.top, plotBottom = lay.plotBottom;
    function y(delta) { return T + (extent - delta) / (2 * extent) * (plotBottom - T); }
    var step = extent <= 5 ? 1 : extent <= 10 ? 2 : extent <= 25 ? 5 : 10;
    var yTicks = [];
    for (var v = -Math.floor(extent / step) * step; v <= extent; v += step) yTicks.push({ value: v, y: y(v), label: signed(v) });
    var points = [], segments = [], current = null, previous = null;
    var marks = lay.marks.slice();
    var gradedDates = {};
    graded.forEach(function (p) { gradedDates[p.date] = true; });
    lay.points.forEach(function (p) {
      if (!gradedDates[p.date]) {
        marks.push({ date: p.date, kind: "not_comparable", x: p.x,
                     label: p.label + " " + MARK_LABELS.not_comparable + "." });
        current = null; previous = null;
        return;
      }
      var delta = p.correct - anchor.correct;
      var point = Object.assign({}, p, { delta: delta, y: y(delta),
        label: p.label + " Change from " + fullDay(anchor.date) + " (" + anchor.correct + " of " + max + "): " +
          signed(delta) + (Math.abs(delta) === 1 ? " correct answer." : " correct answers.") });
      points.push(point);
      if (current && previous === dayNumber(p.date) - 1) current.push(point);
      else { current = [point]; segments.push(current); }
      previous = dayNumber(p.date);
    });
    if (series.contract === "puter-reference-v1") segments = [];
    marks.sort(function (a, b) { return a.date < b.date ? -1 : a.date > b.date ? 1 : 0; });
    return Object.assign({}, lay, {
      mode: "change", yTicks: yTicks, points: points, marks: marks, extent: extent, zeroY: y(0), message: null,
      segments: segments.filter(function (s) { return s.length > 1; }),
      anchor: { date: anchor.date, correct: anchor.correct, total: max }
    });
  }

  return { layout: layout, changeLayout: changeLayout, describe: describe, rowKind: rowKind, dayLabel: dayLabel,
           fullDay: fullDay, signed: signed, segmentText: segmentText, hitRegions: hitRegions, MARK_LABELS: MARK_LABELS };
});
