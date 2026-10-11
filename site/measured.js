/* Baseline's own measurements: which exact models are measured, which test setup a page shows first, and the
   home page's descriptive comparison. Pure functions (no DOM, no fetching, no verdicts).
   Browser global BaselineMeasured; CommonJS for Node tests.

   A model is measured only when one of its admitted series has a scored result: an eligible row (a completed
   40-question daily run, a complete 40-question reference evaluation, or a complete 4-question quick check) with
   at least one gradeable answer. Gradeable means the grader's own categories: correct, incorrect or wrong
   format (review R1, 9 October 2026). A run whose every question failed operationally (request errors,
   timeouts, refusals, empty, cut-off or other-model answers) is a failure, shown as such, never a score of zero;
   forty incorrect answers remain a genuine zero. A scheduled setup, a gap, a partial or interrupted run, a
   one-off setup test, catalogue metadata and third-party observations are not scored measurements.

   The comparison is descriptive, never a statistical verdict. A movement needs two full (40-question) results
   on consecutive UTC dates in the same series (one fingerprint, question set, grader, route and settings), each
   with a gradeable answer to every question (so no request failure and no returned-model mismatch), the newer
   being the series' latest attempt and no older than 48 hours. Rises and falls use the same rule; equal scores
   are not a movement and never a stability claim. */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.BaselineMeasured = factory();
})(this, function () {
  "use strict";
  var DAY_MS = 86400000;
  var FULL_ITEMS = 40;
  var FRESH_MS = 48 * 3600000;
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  function dayNumber(date) { return Math.round(Date.parse(String(date).slice(0, 10) + "T00:00:00Z") / DAY_MS); }
  function dayText(date) {
    var p = String(date).slice(0, 10).split("-");
    return Number(p[2]) + " " + MONTHS[Number(p[1]) - 1] + " " + p[0];
  }

  // A 4-question quick check (puter-subset-v1) is a small sample; everything else here is a 40-question test.
  function isQuick(series) { return !!series && series.contract === "puter-subset-v1"; }
  function isFull(series) { return !!series && !isQuick(series) && series.panel_items === FULL_ITEMS; }
  function isReference(series) { return !!series && series.contract === "puter-reference-v1"; }

  function byDate(a, b) { return a.date < b.date ? -1 : a.date > b.date ? 1 : 0; }
  // Gradeable answers of a recorded run: correct, incorrect or wrong-format (the daily grader's outcomes, or the
  // Puter contracts' `answered`). Refusals, errors, empty, cut-off, unreadable and other-model answers are not.
  function gradeable(row) {
    var r = row.record;
    if (!r) return 0;
    var o = r.first_attempt_outcomes;
    if (o) return (o.correct || 0) + (o.incorrect || 0) + (o.format_error || 0);
    return typeof r.answered === "number" ? r.answered : 0;
  }
  function scoredRows(series) {
    return ((series && series.rows) || []).filter(function (row) {
      return row.eligible === true && !!row.record && gradeable(row) > 0;
    }).slice().sort(byDate);
  }
  // Every recorded attempt of a series up to its cutoff (scored, failed, partial, missed or open), oldest first.
  function attempts(series) { return ((series && series.rows) || []).slice().sort(byDate); }
  // A run that may be compared: scored, every question gradeable, and no returned-model mismatch.
  function comparable(series, row) {
    return !!row && row.eligible === true && !!row.record && gradeable(row) === series.panel_items && !identityMismatch(row);
  }
  // The series' newest attempt when it is later than its newest scored result (a failed, partial, missed or open
  // run), so captions can say that the latest attempt has no score.
  function laterAttempt(series) {
    var all = attempts(series), latest = latestScoredRow(series);
    var last = all[all.length - 1];
    return last && (!latest || last.date > latest.date) ? { date: last.date, state: last.state } : null;
  }
  function latestScoredRow(series) { var rows = scoredRows(series); return rows.length ? rows[rows.length - 1] : null; }
  function correct(row) {
    var r = row.record;
    return typeof r.first_attempt_correct === "number" ? r.first_attempt_correct : r.correct;
  }
  // When a result was measured. A reference evaluation has its finish time; a daily run has only its UTC date,
  // read as the start of that date so that freshness is never overstated.
  function measuredAt(row) {
    var r = row.record;
    return Date.parse(r && r.finished_at ? r.finished_at : String(row.date).slice(0, 10) + "T00:00:00Z");
  }
  function identityMismatch(row) {
    var r = row.record;
    if (r.identity) return (r.identity.mismatch || 0) > 0;
    return ((r.first_attempt_outcomes || {}).answered_identity_mismatch || 0) > 0;
  }
  function point(series, row) {
    return { date: row.date, correct: correct(row), total: series.panel_items, at: measuredAt(row),
             finished_at: row.record.finished_at || null, row: row };
  }
  function latestScored(series) {
    var rows = scoredRows(series);
    return rows.length ? point(series, rows[rows.length - 1]) : null;
  }
  function seriesList(rec) { return (rec && rec.daily_series) || []; }
  function isMeasured(rec) { return seriesList(rec).some(function (s) { return scoredRows(s).length > 0; }); }

  // Which setup a model page shows first. An explicit, valid ?setup= link is respected. Otherwise a full
  // 40-question series with a scored result (newest result first), then a quick check with one; a newer setup
  // without results never hides an older measured one. With no scored series, the newest setup (index 0).
  function defaultIndex(list, requested) {
    list = list || [];
    var asked = list.map(function (s) { return s.series_id; }).indexOf(requested);
    if (requested && asked !== -1) return asked;
    var best = -1, bestKey = null;
    list.forEach(function (s, i) {
      var latest = latestScored(s);
      if (!latest) return;
      var key = [isFull(s) ? 1 : 0, latest.at];
      if (best === -1 || key[0] > bestKey[0] || (key[0] === bestKey[0] && key[1] > bestKey[1])) { best = i; bestKey = key; }
    });
    return best === -1 ? 0 : best;
  }

  // The comparison within one series: { eligible, reason, latest, previous, change, days, hours }.
  // `change` is in percentage points (positive for a rise). Reasons: quick_check, no_result, one_result,
  // later_attempt (the newest attempt has no score: never compared through it), missing_day,
  // identity_mismatch, not_fully_graded (an operational failure or ungradeable answer in either run), stale.
  function comparison(series, nowMs) {
    var rows = scoredRows(series);
    var out = { eligible: false, reason: null, latest: null, previous: null, change: null };
    if (!isFull(series)) { out.reason = "quick_check"; return out; }
    if (!rows.length) { out.reason = "no_result"; return out; }
    var last = rows[rows.length - 1];
    out.latest = point(series, last);
    if (rows.length === 1) { out.reason = "one_result"; return out; }
    if (laterAttempt(series)) { out.reason = "later_attempt"; return out; }
    var before = attempts(series).filter(function (row) { return dayNumber(row.date) === dayNumber(last.date) - 1; })[0];
    if (!before || scoredRows({ rows: [before] }).length === 0) { out.reason = "missing_day"; return out; }
    out.previous = point(series, before);
    if (identityMismatch(last) || identityMismatch(before)) { out.reason = "identity_mismatch"; return out; }
    if (!comparable(series, last) || !comparable(series, before)) { out.reason = "not_fully_graded"; return out; }
    if (nowMs - out.latest.at > FRESH_MS) { out.reason = "stale"; return out; }
    out.eligible = true;
    out.change = Math.round(1000 * (out.latest.correct - out.previous.correct) / series.panel_items) / 10;
    out.days = dayNumber(out.latest.date) - dayNumber(out.previous.date);
    if (out.latest.finished_at && out.previous.finished_at) {
      out.hours = Math.round((Date.parse(out.latest.finished_at) - Date.parse(out.previous.finished_at)) / 3600000);
    }
    return out;
  }

  // The home page's focus, from `models` = [{ id, series: [...] }] (id: a stable model id):
  //   kind "movement": the largest absolute nonzero change among eligible comparisons (ties: newest result,
  //                    then model id);
  //   kind "latest" / "first": otherwise the newest scored full test ("first" when it is that series' only one);
  //   kind "quick": otherwise the newest quick check;
  //   null when nothing is measured.
  function highlight(models, nowMs) {
    var moves = [], fulls = [], quicks = [];
    (models || []).forEach(function (m) {
      (m.series || []).forEach(function (s) {
        var latest = latestScored(s);
        if (!latest) return;
        var item = { id: m.id, model: m, series: s, latest: latest, later: laterAttempt(s) };
        if (!isFull(s)) { quicks.push(item); return; }
        fulls.push(item);
        var c = comparison(s, nowMs);
        if (c.eligible && c.change !== 0) moves.push(Object.assign(item, { comparison: c }));
      });
    });
    function newest(a, b) { return b.latest.at - a.latest.at || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0); }
    if (moves.length) {
      moves.sort(function (a, b) { return Math.abs(b.comparison.change) - Math.abs(a.comparison.change) || newest(a, b); });
      return Object.assign(moves[0], { kind: "movement" });
    }
    if (fulls.length) {
      fulls.sort(newest);
      return Object.assign(fulls[0], { kind: scoredRows(fulls[0].series).length === 1 ? "first" : "latest" });
    }
    if (quicks.length) {
      quicks.sort(newest);
      return Object.assign(quicks[0], { kind: "quick" });
    }
    return null;
  }

  var HEADINGS = {
    movement: "Largest observed movement in our latest comparable tests",
    latest: "Latest measurement", first: "First measurement", quick: "Latest quick check"
  };

  function score(p) { return p.correct + " of " + p.total + " correct on " + dayText(p.date); }
  // A failed, partial, missed or open attempt after the shown result stays visible in the caption.
  function laterText(h) {
    return h.later ? " A later attempt on " + dayText(h.later.date) + " has no score; the graph shows it." : "";
  }
  function gapText(c) {
    if (typeof c.hours === "number") return c.hours === 1 ? "1 hour apart" : c.hours + " hours apart";
    return c.days === 1 ? "one UTC day apart" : c.days + " UTC days apart";
  }
  // A short descriptive caption for the focus; never a verdict about the model.
  function caption(h) {
    if (!h) return "";
    if (h.kind === "movement") {
      var c = h.comparison, size = Math.abs(c.change);
      return (c.change > 0 ? "Up " : "Down ") + size + (size === 1 ? " percentage point" : " percentage points") +
        ": " + score(c.previous) + ", then " + score(c.latest) + " (" + gapText(c) + "). Two runs of a " +
        h.latest.total + "-question test are a small sample; this describes what we observed, not a confirmed change.";
    }
    if (h.kind === "first") {
      return score(h.latest) + ". This is the first result of this test setup, so there is no earlier result to " +
        "compare with yet." + laterText(h);
    }
    if (h.kind === "latest") {
      return score(h.latest) + ", the newest scored " + h.latest.total + "-question test. No comparable pair of " +
        "recent results shows a movement now; that does not mean the model is stable." + laterText(h);
    }
    return score(h.latest) + ". A " + h.latest.total + "-question quick check is a small sample, not a full test." +
      laterText(h);
  }

  // A mini history for the measured list: scored results only, on the full 0 to total scale, joined only on
  // consecutive days (reference evaluations are never joined). One result is one point, never a line.
  function sparkline(series, width, height) {
    var rows = scoredRows(series), total = series.panel_items, pad = 4;
    var w = width || 120, h = height || 36;
    if (!rows.length) return { width: w, height: h, points: [], segments: [] };
    var first = dayNumber(rows[0].date), span = Math.max(dayNumber(rows[rows.length - 1].date) - first, 1);
    var points = rows.map(function (row) {
      var c = correct(row);
      return { date: row.date, correct: c, total: total,
               x: rows.length === 1 ? w / 2 : pad + (dayNumber(row.date) - first) / span * (w - 2 * pad),
               y: pad + (1 - c / total) * (h - 2 * pad) };
    });
    var segments = [], current = null;
    if (!isReference(series)) {
      points.forEach(function (p, i) {
        if (i && dayNumber(p.date) === dayNumber(points[i - 1].date) + 1) current.push(p);
        else { current = [p]; segments.push(current); }
      });
    }
    return { width: w, height: h, points: points, segments: segments.filter(function (s) { return s.length > 1; }) };
  }

  return { FULL_ITEMS: FULL_ITEMS, FRESH_MS: FRESH_MS, HEADINGS: HEADINGS, isQuick: isQuick, isFull: isFull,
           isReference: isReference, scoredRows: scoredRows, latestScored: latestScored, isMeasured: isMeasured,
           gradeable: gradeable, laterAttempt: laterAttempt,
           defaultIndex: defaultIndex, comparison: comparison, highlight: highlight, caption: caption,
           sparkline: sparkline, dayText: dayText };
});
