/* Baseline's own daily test scores: pure graph layout (T13). No DOM, no fetching, no verdicts.
   Browser global BaselineResultsChart; CommonJS for Node tests.

   One layout per daily series (one fixed test setup). Calendar dates run along x with
   spacing by elapsed days across the whole scheduled campaign; y is the full 0 to
   panel_items scale (never cropped). Only eligible rows (verified, completed, every
   question attempted) become points. A line joins two points only on consecutive
   calendar days of the same series; any gap, missing record, partial or unavailable
   result breaks it. Rows without a score are marks in a separate "no score" lane, so
   they can never be read as a zero. Nothing is interpolated or carried forward. */
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
    pending: "Not yet tested or not yet published"
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

  // Row kind for drawing: "point" or one of the MARK_LABELS keys.
  function rowKind(row) {
    if (row.eligible) return "point";
    if (row.state === "gap") return "gap";
    if (row.state === "open") return "open";
    if (row.state === "no_record" || !row.record) return "no_record";
    if (row.record.evidence !== "verified") return "unavailable";
    return "partial";
  }

  function details(row) {
    var r = row.record;
    var kind = rowKind(row);
    var out = { date: row.date, kind: kind, status: row.state };
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

  // Plain sentence for screen readers and the details panel. Never a verdict.
  function describe(d) {
    var head = fullDay(d.date) + ": ";
    if (d.kind === "point") {
      return head + d.correct + " of " + d.scheduled + " correct on the first attempt; all " + d.attempted +
        " questions attempted; " + d.refusals + " refused, " + d.request_errors + " request errors" +
        (d.answer_problems ? ", " + d.answer_problems + " cut off or unreadable" : "") +
        (d.retry_correct ? "; " + d.retry_correct + " more correct on a retry (not counted)" : "") + ".";
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
    var span = Math.max(last - first, 1);
    var plotBottom = H - B;
    function x(date) { return L + (dayNumber(date) - first) / span * (W - L - R); }
    function y(score) { return T + (1 - score / max) * (plotBottom - T); }

    var step = niceStep(max), yTicks = [];
    for (var v = 0; v < max; v += step) yTicks.push({ value: v, y: y(v) });
    yTicks.push({ value: max, y: y(max) });

    var xTicks = [];
    for (var n = first; n <= last; n += 7) {
      var iso = new Date(n * DAY_MS).toISOString().slice(0, 10);
      xTicks.push({ date: iso, x: x(iso), label: dayLabel(iso) });
    }
    if (xTicks[xTicks.length - 1].date !== series.schedule.end_date && last - first >= 4) {
      xTicks.push({ date: series.schedule.end_date, x: x(series.schedule.end_date), label: dayLabel(series.schedule.end_date) });
    }

    var points = [], marks = [], segments = [], current = null, previous = null;
    (series.rows || []).forEach(function (row) {
      var d = details(row);
      d.x = x(row.date);
      d.label = describe(d);
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
      marks.push({ date: date, kind: "pending", x: x(date), label: fullDay(date) + ": " + MARK_LABELS.pending + "." });
    });
    marks.sort(function (a, b) { return a.date < b.date ? -1 : a.date > b.date ? 1 : 0; });

    var message = points.length === 0 ? "Waiting for daily results"
      : points.length === 1 ? "One daily test; more days are needed to show a pattern" : null;
    return {
      width: W, height: H, left: L, right: W - R, top: T, plotBottom: plotBottom, laneY: plotBottom + 40,
      max: max, yTicks: yTicks, xTicks: xTicks, points: points,
      segments: segments.filter(function (s) { return s.length > 1; }),
      marks: marks, message: message, MARK_LABELS: MARK_LABELS
    };
  }

  return { layout: layout, describe: describe, rowKind: rowKind, dayLabel: dayLabel, fullDay: fullDay,
           MARK_LABELS: MARK_LABELS };
});
