// The measured set, default setup and descriptive comparison (site/measured.js), from labelled synthetic series.
"use strict";
const assert = require("node:assert/strict");
const M = require("../site/measured.js");

const NOW = Date.parse("2026-10-09T12:00:00Z");
// First-attempt outcome counts as the daily contract records them: `over` sets other categories, and the rest of
// the questions are incorrect unless `over` says otherwise.
function outcomes(correct, items, over = {}) {
  const o = Object.assign({ correct }, over);
  if (!("incorrect" in over)) {
    o.incorrect = items - correct - Object.entries(over).reduce((n, [k, v]) => n + (k === "correct" ? 0 : v), 0);
  }
  return o;
}
// A 40-question daily series: rows [date, correct | null (not scored), extra]. extra.outcomes overrides outcome
// categories, extra.eligible the published eligibility, extra.state the row state.
function daily(id, rows, opts = {}) {
  const items = opts.items || 40;
  return { series_id: id, panel_items: items, contract: opts.contract,
    rows: rows.map(([date, correct, extra = {}]) => correct === null
      ? { date, state: extra.state || "gap", eligible: false, record: null }
      : { date, state: extra.state || "completed", eligible: extra.eligible !== false,
          record: { date, evidence: "verified", status: "completed", scheduled_items: items, attempted_items: items,
                    first_attempt_correct: correct, first_attempt_outcomes: outcomes(correct, items, extra.outcomes),
                    retry_recovered: { correct: 0 } } }) };
}
function quick(id, rows) {
  return { series_id: id, panel_items: 4, contract: "puter-subset-v1",
    rows: rows.map(([date, correct]) => ({ date, state: "completed", eligible: true,
      record: { date, record_version: 1, evidence: "verified", status: "completed", correct, answered: 4, attempted: 4,
                planned_items: 4, not_sent: 0, not_graded: { refusal: 0, error: 0, truncated: 0, missing_text: 0, malformed: 0,
                uncertain: 0 }, identity: { unknown: 4, reported_match: 0, mismatch: 0 } } })) };
}
function reference(id, evaluations) {
  return { series_id: id, panel_items: 40, contract: "puter-reference-v1",
    rows: evaluations.map(([finished, correct, status, mismatch]) => ({ date: finished.slice(0, 10), state: status || "complete",
      eligible: (status || "complete") === "complete" && !mismatch,
      record: { date: finished.slice(0, 10), finished_at: finished, correct, answered: 40,
                identity: { unknown: 40, mismatch: mismatch || 0 } } })) };
}

// ---------------------------------------------------------------- measured set
assert.equal(M.isMeasured({ daily_series: [daily("a", [["2026-10-08", 0]])] }), true);        // a scored zero counts
assert.equal(M.isMeasured({ daily_series: [daily("a", [["2026-10-08", null]])] }), false);    // a gap does not
assert.equal(M.isMeasured({ daily_series: [daily("a", [["2026-10-08", 30, { eligible: false }]])] }), false);  // partial
assert.equal(M.isMeasured({ daily_series: [{ series_id: "s", panel_items: 40, rows: [] }] }), false);  // schedule only
assert.equal(M.isMeasured({ daily_series: [], calibration: [{ first_attempt_correct: 31 }] }), false); // setup test only
assert.equal(M.isMeasured(null), false);
assert.equal(M.isMeasured({ daily_series: [reference("r", [["2026-10-08T05:00:00Z", 12, "expired"]])] }), false);
assert.equal(M.isMeasured({ daily_series: [reference("r", [["2026-10-08T05:00:00Z", 35]])] }), true);   // reference only
assert.equal(M.isMeasured({ daily_series: [quick("q", [["2026-10-08", 3]])] }), true);

// ---------------------------------------------------------------- default setup
const emptyNew = { series_id: "new", panel_items: 40, rows: [] };
const older = daily("old", [["2026-10-01", 30], ["2026-10-02", 31]]);
const sample = quick("q", [["2026-10-08", 4]]);
assert.equal(M.defaultIndex([emptyNew, older]), 1);                       // a new empty setup never hides results
assert.equal(M.defaultIndex([emptyNew, older], "new"), 0);                // an explicit valid link is respected
assert.equal(M.defaultIndex([emptyNew, older], "no-such-setup"), 1);
assert.equal(M.defaultIndex([sample, older]), 1);                         // a 40-question series before a sample
assert.equal(M.defaultIndex([sample, emptyNew]), 0);                      // otherwise the labelled quick check
assert.equal(M.defaultIndex([emptyNew]), 0);
assert.equal(M.defaultIndex([older, daily("newer", [["2026-10-05", 20]])]), 1);   // the newest result first

// ---------------------------------------------------------------- one series: the comparison rule
const rise = daily("rise", [["2026-10-07", 36], ["2026-10-08", 37]]);
let c = M.comparison(rise, NOW);
assert.deepEqual([c.eligible, c.change, c.days, c.previous.correct, c.latest.correct], [true, 2.5, 1, 36, 37]);
c = M.comparison(daily("fall", [["2026-10-07", 37], ["2026-10-08", 33]]), NOW);
assert.deepEqual([c.eligible, c.change], [true, -10]);                    // a fall, by the same rule
c = M.comparison(daily("equal", [["2026-10-07", 37], ["2026-10-08", 37]]), NOW);
assert.deepEqual([c.eligible, c.change], [true, 0]);                      // equal: no movement, no verdict
assert.equal(M.comparison(daily("gap", [["2026-10-06", 30], ["2026-10-07", null], ["2026-10-08", 37]]), NOW).reason,
             "missing_day");
assert.equal(M.comparison(daily("skip", [["2026-10-06", 30], ["2026-10-08", 37]]), NOW).reason, "missing_day");
assert.equal(M.comparison(daily("partial", [["2026-10-07", 20, { eligible: false }], ["2026-10-08", 37]]), NOW).reason,
             "one_result");                                               // a partial run is never compared
assert.equal(M.comparison(daily("stale", [["2026-10-05", 30], ["2026-10-06", 37]]), NOW).reason, "stale");
assert.equal(M.comparison(daily("edge", [["2026-10-06", 30], ["2026-10-07", 37]]), Date.parse("2026-10-09T00:00:00Z"))
             .eligible, true);                                            // exactly 48 hours after 7 Oct 00:00
assert.equal(M.comparison(daily("edge", [["2026-10-06", 30], ["2026-10-07", 37]]), Date.parse("2026-10-09T00:00:01Z"))
             .reason, "stale");
assert.equal(M.comparison(daily("one", [["2026-10-08", 37]]), NOW).reason, "one_result");
assert.equal(M.comparison(quick("q", [["2026-10-07", 2], ["2026-10-08", 4]]), NOW).reason, "quick_check");   // 4 vs 40
assert.equal(M.comparison(daily("mismatch", [["2026-10-07", 36],
  ["2026-10-08", 37, { outcomes: { answered_identity_mismatch: 1 } }]]), NOW).reason, "identity_mismatch");
// The daily contract grades an answer of unconfirmed identity as its own outcome, not as correct or incorrect: such
// a run stays scored and visible but is not fully gradeable, so it is not promoted.
c = M.comparison(daily("unknown", [["2026-10-07", 36],
  ["2026-10-08", 37, { outcomes: { answered_identity_unknown: 3 } }]]), NOW);
assert.deepEqual([c.eligible, c.reason], [false, "not_fully_graded"]);
c = M.comparison(reference("ref", [["2026-10-07T20:00:00Z", 30], ["2026-10-08T22:00:00Z", 34]]), NOW);
assert.deepEqual([c.eligible, c.change, c.hours], [true, 10, 26]);        // reference: real finish times
assert.equal(M.comparison(reference("ref", [["2026-10-07T20:00:00Z", 30], ["2026-10-08T22:00:00Z", 34, "complete", 1]]),
                          NOW).reason, "one_result");                     // a mismatched evaluation is not scored

// ---------------------------------------------------------------- across models
const models = (list) => list.map(([id, series]) => ({ id, series }));
let h = M.highlight(models([["a", [rise]], ["b", [daily("b", [["2026-10-07", 30], ["2026-10-08", 26]])]]]), NOW);
assert.deepEqual([h.kind, h.id, h.comparison.change], ["movement", "b", -10]);   // the largest absolute change
h = M.highlight(models([["a", [daily("up", [["2026-10-07", 30], ["2026-10-08", 34]])]],
                         ["b", [daily("down", [["2026-10-07", 30], ["2026-10-08", 29]])]]]), NOW);
assert.deepEqual([h.kind, h.id, h.comparison.change], ["movement", "a", 10]);    // a larger rise beats a smaller fall
h = M.highlight(models([["b", [daily("b", [["2026-10-07", 30], ["2026-10-08", 31]])]], ["a", [rise]]]), NOW);
assert.deepEqual([h.kind, h.id], ["movement", "a"]);                      // a tie: same date, then the model id
h = M.highlight(models([["a", [rise]], ["z", [daily("z", [["2026-10-08", 36], ["2026-10-09", 37]])]]]), NOW);
assert.equal(h.id, "z");                                                  // a tie: the newest result first
h = M.highlight(models([["a", [daily("e", [["2026-10-07", 37], ["2026-10-08", 37]])]]]), NOW);
assert.equal(h.kind, "latest");                                           // equal scores: no movement claimed
assert.match(M.caption(h), /does not mean the model is stable/);
h = M.highlight(models([["a", [daily("one", [["2026-10-08", 37]])]], ["q", [sample]]]), NOW);
assert.deepEqual([h.kind, h.id], ["first", "a"]);                         // a full test before a quick check
assert.match(M.caption(h), /first result of this test setup/);
h = M.highlight(models([["q", [sample]]]), NOW);
assert.equal(h.kind, "quick");
assert.match(M.caption(h), /4-question quick check is a small sample/);
assert.equal(M.highlight(models([["a", [emptyNew]]]), NOW), null);
h = M.highlight(models([["a", [daily("stale", [["2026-10-05", 30], ["2026-10-06", 37]])]]]), NOW);
assert.equal(h.kind, "latest");                                           // stale: never a movement
h = M.highlight(models([["a", [older, daily("new", [["2026-10-08", 20]])]]]), NOW);
assert.deepEqual([h.kind, h.series.series_id], ["first", "new"]);         // a setup change is never joined
h = M.highlight(models([["a", [rise]]]), NOW);
assert.equal(M.caption(h), "Up 2.5 percentage points: 36 of 40 correct on 7 Oct 2026, then 37 of 40 correct on " +
  "8 Oct 2026 (one UTC day apart). Two runs of a 40-question test are a small sample; this describes what we " +
  "observed, not a confirmed change.");
for (const text of [M.caption(h), Object.values(M.HEADINGS).join(" ")]) {
  for (const banned of ["nerf", "best model", "confirmed decline", "significan", "worse", "better"]) {
    assert.ok(!text.toLowerCase().includes(banned), banned);
  }
}

// ---------------------------------------------------------------- review R1: failures are never scores
const errorsOnly = { outcomes: { incorrect: 0, provider_error: 40 } };
assert.equal(M.gradeable(daily("e", [["2026-10-09", 0, errorsOnly]]).rows[0]), 0);
assert.equal(M.isMeasured({ daily_series: [daily("e", [["2026-10-09", 0, errorsOnly]])] }), false);   // not measured
assert.equal(M.isMeasured({ daily_series: [daily("z", [["2026-10-09", 0]])] }), true);   // 40 incorrect: a real zero
for (const failed of [{ outcomes: { incorrect: 0, timeout: 40 } }, { outcomes: { incorrect: 0, refusal: 40 } },
                      { outcomes: { incorrect: 0, answered_identity_mismatch: 40 } }, { outcomes: { incorrect: 0, empty: 40 } }]) {
  assert.equal(M.isMeasured({ daily_series: [daily("f", [["2026-10-09", 0, failed]])] }), false, JSON.stringify(failed));
}
const outage = daily("outage", [["2026-10-07", 30], ["2026-10-08", 36], ["2026-10-09", 0, errorsOnly]]);
c = M.comparison(outage, Date.parse("2026-10-10T06:00:00Z"));
assert.deepEqual([c.eligible, c.reason, c.latest.date], [false, "later_attempt", "2026-10-08"]);   // never -90
h = M.highlight([{ id: "g", series: [outage] }], Date.parse("2026-10-10T06:00:00Z"));
assert.equal(h.kind, "latest");                                           // never the 7-8 Oct movement
assert.match(M.caption(h), /A later attempt on 9 Oct 2026 has no score; the graph shows it\./);
c = M.comparison(daily("zero", [["2026-10-08", 36], ["2026-10-09", 0]]), Date.parse("2026-10-10T06:00:00Z"));
assert.deepEqual([c.eligible, c.change], [true, -90]);                    // a genuine, fully graded zero
c = M.comparison(daily("mixed", [["2026-10-08", 36], ["2026-10-09", 30, { outcomes: { timeout: 10, incorrect: 0 } }]]),
                 Date.parse("2026-10-10T06:00:00Z"));
assert.deepEqual([c.eligible, c.reason], [false, "not_fully_graded"]);    // visible, never promoted
c = M.comparison(daily("mixed-before", [["2026-10-08", 30, { outcomes: { provider_error: 2 } }], ["2026-10-09", 36]]),
                 Date.parse("2026-10-10T06:00:00Z"));
assert.equal(c.reason, "not_fully_graded");
c = M.comparison(daily("refused", [["2026-10-08", 36], ["2026-10-09", 35, { outcomes: { refusal: 1 } }]]),
                 Date.parse("2026-10-10T06:00:00Z"));
assert.equal(c.reason, "not_fully_graded");                               // a refusal is not a graded answer
c = M.comparison(daily("format", [["2026-10-08", 36], ["2026-10-09", 35, { outcomes: { format_error: 5, incorrect: 0 } }]]),
                 Date.parse("2026-10-10T06:00:00Z"));
assert.deepEqual([c.eligible, c.change], [true, -2.5]);                   // wrong format is graded (strict grader)
for (const later of [[null, { state: "gap" }], [null, { state: "no_record" }], [null, { state: "open" }],
                     [20, { eligible: false, state: "stopped" }], [0, errorsOnly]]) {
  const s = daily("later", [["2026-10-07", 30], ["2026-10-08", 34], ["2026-10-09", later[0], later[1]]]);
  c = M.comparison(s, Date.parse("2026-10-09T12:00:00Z"));
  assert.deepEqual([c.eligible, c.reason], [false, "later_attempt"], JSON.stringify(later));   // no older headline
}
c = M.comparison(daily("prev-error", [["2026-10-07", 30], ["2026-10-08", 0, errorsOnly], ["2026-10-09", 36]]), NOW);
assert.equal(c.reason, "missing_day");                                    // a failed previous day is not a result
assert.equal(M.laterAttempt(outage).date, "2026-10-09");
assert.equal(M.laterAttempt(rise), null);

// ---------------------------------------------------------------- mini history
let sp = M.sparkline(daily("s", [["2026-10-01", 40], ["2026-10-02", 0], ["2026-10-04", 20]]), 100, 30);
assert.equal(sp.points.length, 3);
assert.equal(sp.segments.length, 1);                                      // joined only on consecutive days
assert.deepEqual([sp.points[0].y, sp.points[1].y], [4, 26]);              // the full 0 to 40 scale
sp = M.sparkline(daily("one", [["2026-10-08", 37]]), 100, 30);
assert.deepEqual([sp.points.length, sp.segments.length, sp.points[0].x], [1, 0, 50]);   // one point, never a line
sp = M.sparkline(reference("r", [["2026-10-07T20:00:00Z", 30], ["2026-10-08T22:00:00Z", 34]]), 100, 30);
assert.equal(sp.segments.length, 0);                                      // evaluations are never joined
// ---------------------------------------------------------------- the trimmed graph axis (site/results-chart.js)
const C = require("../site/results-chart.js");
// review R1 in the graph: an eligible run with no gradeable answer is a failure mark, never a point at zero
const failedLayout = C.layout(Object.assign(daily("g", [["2026-10-02", 36], ["2026-10-03", 0, errorsOnly], ["2026-10-04", 0]]), {
  as_of: "2026-10-04T12:00:00Z", schedule: { start_date: "2026-10-02", end_date: "2026-10-08" } }), {});
assert.deepEqual(failedLayout.points.map((p) => [p.date, p.correct]), [["2026-10-02", 36], ["2026-10-04", 0]]);
assert.equal(failedLayout.segments.length, 0);                            // the failure breaks the line
const failedMark = failedLayout.marks.find((m) => m.kind === "failed");
assert.ok(failedMark && failedMark.label.startsWith("3 Oct 2026: no gradeable answer"), failedMark && failedMark.label);
const campaign = Object.assign(daily("c", [["2026-10-02", 37], ["2026-10-03", 36]]), {
  as_of: "2026-10-09T12:00:00Z", schedule: { start_date: "2026-10-02", end_date: "2026-10-29" },
  pending_dates: ["2026-10-10", "2026-10-20"] });
const full = C.layout(campaign, { width: 960, height: 320 });
const trimmed = C.layout(campaign, { width: 960, height: 320, trim: true });
assert.equal(full.xTicks[full.xTicks.length - 1].label, "29 Oct");                // the default is unchanged
assert.equal(trimmed.xTicks[trimmed.xTicks.length - 1].label, "9 Oct");           // ends at the checked date
assert.equal(trimmed.marks.filter((m) => m.kind === "pending").length, 0);        // later dates are not drawn
assert.deepEqual(trimmed.yTicks.map((t) => t.value), [0, 10, 20, 30, 40]);         // the full scale, never cropped
assert.ok(trimmed.points[1].x - trimmed.points[0].x > full.points[1].x - full.points[0].x);
const short = Object.assign({}, campaign, { as_of: "2026-10-03T12:00:00Z" });
assert.equal(C.layout(short, { trim: true }).xTicks.slice(-1)[0].label, "8 Oct");   // at least a week is shown
// ---------------------------------------------------------------- the monitor readout (11 October 2026)
let o = M.observation(daily("r", [["2026-10-08", 36], ["2026-10-09", 37]]), Date.parse("2026-10-10T06:00:00Z"));
assert.equal(o.text, "1 more correct answer than the previous test (8 Oct 2026)");
assert.match(o.caution, /^Not enough evidence of a lasting improvement/);
o = M.observation(daily("f", [["2026-10-08", 36], ["2026-10-09", 33]]), Date.parse("2026-10-10T06:00:00Z"));
assert.equal(o.text, "3 fewer correct answers than the previous test (8 Oct 2026)");
assert.match(o.caution, /^Not enough evidence of a lasting decline/);
o = M.observation(daily("e", [["2026-10-08", 36], ["2026-10-09", 36]]), Date.parse("2026-10-10T06:00:00Z"));
assert.equal(o.text, "Same score on these two tests (8 Oct 2026 and 9 Oct 2026)");        // never "stable"
assert.match(o.caution, /does not mean the model is stable/);
assert.equal(M.observation(daily("one", [["2026-10-09", 37]]), NOW).text, "First result—no history yet.");
assert.equal(M.observation(quick("q", [["2026-10-08", 2], ["2026-10-09", 4]]), NOW).text,
             "Quick check: 4 questions, too small to compare as a full test.");          // 4 never compared
assert.equal(M.observation(outage, Date.parse("2026-10-10T06:00:00Z")).text,
             "The latest attempt, on 9 Oct 2026, has no score, so no comparison is shown.");
assert.equal(M.observation({ series_id: "s", panel_items: 40, rows: [] }, NOW), null);
const key1 = M.observation(rise, Date.parse("2026-10-09T12:00:00Z")).key;
assert.notEqual(key1, M.observation(rise, Date.parse("2026-10-11T00:00:01Z")).key);    // the live refresh can see expiry
assert.equal(key1, M.observation(rise, Date.parse("2026-10-09T13:00:00Z")).key);       // and nothing changes within it

// ---------------------------------------------------------------- movement links and Change availability
const mv = M.movements(models([["a", [rise]], ["b", [daily("b", [["2026-10-07", 30], ["2026-10-08", 26]])]],
                               ["c", [daily("c", [["2026-10-07", 30], ["2026-10-08", 30]])]], ["q", [sample]]]), NOW);
assert.deepEqual(mv.map((m) => [m.id, m.comparison.change]), [["b", -10], ["a", 2.5]]);   // nonzero, largest first
assert.equal(M.highlight(models([["a", [rise]], ["b", [daily("b", [["2026-10-07", 30], ["2026-10-08", 26]])]]]), NOW).id,
             mv[0].id);                                                   // the same choice as the home's selection
assert.equal(M.changeAvailable(rise), true);
assert.equal(M.changeAvailable(daily("one", [["2026-10-09", 37]])), false);
assert.equal(M.changeAvailable(daily("m", [["2026-10-08", 36], ["2026-10-09", 30, { outcomes: { timeout: 10, incorrect: 0 } }]])),
             false);                                                      // a mixed run is never a change point
assert.equal(M.comparableRows(outage).length, 2);                          // the outage day is excluded

// ---------------------------------------------------------------- Change view layout (site/results-chart.js)
const Cx = require("../site/results-chart.js");
function dated(s) { return Object.assign(s, { as_of: "2026-10-10T12:00:00Z", schedule: { start_date: s.rows[0].date, end_date: "2026-10-29" } }); }
let ch = Cx.changeLayout(dated(daily("c1", [["2026-10-03", 37], ["2026-10-04", 37], ["2026-10-05", 38], ["2026-10-06", null],
  ["2026-10-07", 36], ["2026-10-08", 30, { outcomes: { incorrect: 5, timeout: 5 } }], ["2026-10-09", 36], ["2026-10-10", 37]])),
  { width: 900, height: 340, trim: true });
assert.deepEqual(ch.anchor, { date: "2026-10-03", correct: 37, total: 40 });
assert.equal(ch.extent, 4);                                                // at least ±4 answers for a 40-question panel
assert.deepEqual(ch.yTicks.map((t) => t.label), ["\u22124", "\u22123", "\u22122", "\u22121", "0", "+1", "+2", "+3", "+4"]);
assert.deepEqual(ch.points.map((p) => [p.date.slice(8), p.delta]), [["03", 0], ["04", 0], ["05", 1], ["07", -1], ["09", -1], ["10", 0]]);
assert.deepEqual(ch.segments.map((s) => s.map((p) => p.date.slice(8))), [["03", "04", "05"], ["09", "10"]]);   // gaps break
assert.ok(ch.marks.some((m) => m.date === "2026-10-08" && m.kind === "not_comparable"));
assert.ok(Math.abs((ch.zeroY - ch.top) - (ch.plotBottom - ch.zeroY)) < 1e-9);  // zero sits in the middle
ch = Cx.changeLayout(dated(daily("c2", [["2026-10-03", 30], ["2026-10-04", 39], ["2026-10-05", 25]])), { trim: true });
assert.equal(ch.extent, 9);                                                // widened symmetrically to the largest change
assert.equal(ch.yTicks[0].value, -ch.yTicks[ch.yTicks.length - 1].value);
ch = Cx.changeLayout(dated(daily("c3", [["2026-10-03", 0, errorsOnly], ["2026-10-04", 20], ["2026-10-05", 22]])), { trim: true });
assert.equal(ch.anchor.date, "2026-10-04");                                // an error-only run is never the anchor
ch = Cx.changeLayout(dated(Object.assign(quick("q4", [["2026-10-03", 3], ["2026-10-04", 3]]), {})), { trim: true });
assert.deepEqual(ch.yTicks.map((t) => t.label), ["\u22121", "0", "+1"]);   // ±1 minimum for a 4-question panel
assert.deepEqual(Cx.changeLayout(dated(daily("c4", [["2026-10-03", 37]])), {}), { unavailable: "one", count: 1 });
const sc = Cx.layout(dated(daily("c5", [["2026-10-03", 37], ["2026-10-04", 36]])), { trim: true });
assert.deepEqual(sc.yTicks.map((t) => t.value), [0, 10, 20, 30, 40]);       // Score view: the full scale, unchanged
console.log("measured.js: all assertions passed");
