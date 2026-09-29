/* Freshness and age calculations. Pure functions; `now` is always passed in, so the
   page recomputes them from the viewer's clock and ages grow without a rebuild.
   Works as a browser global (BaselineFreshness) and as a CommonJS module for tests. */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.BaselineFreshness = factory();
})(this, function () {
  "use strict";
  var DAY_MS = 86400000;
  // Display thresholds for measurement age. A presentation convention (see Methods),
  // not a statistical test.
  var RECENT_DAYS = 7;
  var AGING_DAYS = 30;

  // "2025-10-03" -> day precision (timezone not stated by the source);
  // "2026-09-28T22:33:01Z" -> an instant.
  function parseMoment(value) {
    if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
      return { time: Date.parse(value + "T00:00:00Z"), precision: "day" };
    }
    if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$/.test(value)) {
      return { time: Date.parse(value), precision: "instant" };
    }
    return { time: NaN, precision: "unknown" };
  }

  function ageDays(value, now) {
    var m = parseMoment(value);
    return (now - m.time) / DAY_MS;
  }

  // Human wording. Day-precision dates are whole days with a one-day uncertainty,
  // so they are never shown in hours.
  function describeAge(value, now) {
    var m = parseMoment(value);
    if (isNaN(m.time)) return "unknown age";
    var days = (now - m.time) / DAY_MS;
    if (days < 0) return m.precision === "day" ? "dated today or later" : "in the future";
    if (m.precision === "day") {
      var whole = Math.floor(days);
      if (whole === 0) return "today (date only)";
      return "about " + whole + (whole === 1 ? " day" : " days") + " ago";
    }
    var hours = days * 24;
    if (hours < 1) return "under an hour ago";
    if (hours < 48) return Math.floor(hours) + (Math.floor(hours) === 1 ? " hour" : " hours") + " ago";
    return Math.floor(days) + " days ago";
  }

  function measurementStatus(value, now) {
    var days = ageDays(value, now);
    if (isNaN(days)) return { key: "unknown", label: "Unknown age" };
    if (days <= RECENT_DAYS) return { key: "recent", label: "Recent" };
    if (days <= AGING_DAYS) return { key: "aging", label: "Aging" };
    return { key: "stale", label: "Stale" };
  }

  function newest(values) {
    var best = null, bestTime = -Infinity;
    values.forEach(function (v) {
      var t = parseMoment(v).time;
      if (t > bestTime) { bestTime = t; best = v; }
    });
    return best;
  }

  // Longest stretch between consecutive measurements, in whole days.
  function longestGapDays(values) {
    var times = values.map(function (v) { return parseMoment(v).time; }).sort(function (a, b) { return a - b; });
    var gap = 0;
    for (var i = 1; i < times.length; i++) gap = Math.max(gap, (times[i] - times[i - 1]) / DAY_MS);
    return Math.round(gap);
  }

  return {
    DAY_MS: DAY_MS, RECENT_DAYS: RECENT_DAYS, AGING_DAYS: AGING_DAYS,
    parseMoment: parseMoment, ageDays: ageDays, describeAge: describeAge,
    measurementStatus: measurementStatus, newest: newest, longestGapDays: longestGapDays
  };
});
