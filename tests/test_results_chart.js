// Behavioural tests for site/results-chart.js, Baseline's daily score graph layout (T13).
// Fixtures are the labelled synthetic graph fixtures, summarised by scripts/own_results.py
// (tests/test_directory.py writes them to a temporary file passed as argv[2]).
"use strict";
const assert = require("node:assert/strict");
const fs = require("fs");
const C = require("../site/results-chart.js");

const views = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));   // {name: [daily_series...]}
const several = views["several-points"][0];
const lay = C.layout(several, { width: 720, height: 250 });

// Full, fixed scale: 0 to panel_items, never cropped to the data.
assert.equal(lay.max, 40);
assert.deepEqual(lay.yTicks.map((t) => t.value), [0, 10, 20, 30, 40]);
assert.equal(lay.yTicks[0].y, lay.plotBottom);
assert.equal(lay.yTicks[4].y, lay.top);

// Real calendar spacing across the whole campaign (2-29 Oct): equal days, equal distances.
const px = Object.fromEntries(lay.points.map((p) => [p.date, p]));
const step = px["2026-10-03"].x - px["2026-10-02"].x;
assert.ok(step > 0);
assert.ok(Math.abs((px["2026-10-08"].x - px["2026-10-02"].x) - 6 * step) < 1e-9);
assert.ok(Math.abs(lay.xTicks[0].x - lay.left) < 1e-9);
assert.equal(lay.xTicks[0].label, "2 Oct");
assert.equal(lay.xTicks[lay.xTicks.length - 1].label, "29 Oct");

// Points: only verified, completed, fully attempted days. A real zero sits at zero.
assert.deepEqual(lay.points.map((p) => p.date), ["2026-10-02", "2026-10-03", "2026-10-08", "2026-10-09"]);
assert.equal(px["2026-10-03"].correct, 0);
assert.equal(px["2026-10-03"].y, lay.plotBottom);
assert.ok(px["2026-10-02"].label.includes("37 of 40 correct"));
assert.ok(px["2026-10-08"].label.includes("1 more correct on a retry (not counted)"));

// Lines join consecutive calendar days of one series only; every gap breaks them.
assert.deepEqual(lay.segments.map((s) => s.map((p) => p.date)), [["2026-10-02", "2026-10-03"], ["2026-10-08", "2026-10-09"]]);

// Even if rows skip a calendar date (defence in depth), two points are never joined across it.
const skipping = JSON.parse(JSON.stringify(several));
skipping.rows = several.rows.filter((r) => ["2026-10-08", "2026-10-02"].includes(r.date));
assert.deepEqual(C.layout(skipping).segments, []);

// Days without a score are marks in the separate lane, never points or zeros.
const marks = Object.fromEntries(lay.marks.filter((m) => m.kind !== "pending").map((m) => [m.date, m]));
assert.deepEqual(Object.keys(marks).sort(), ["2026-10-04", "2026-10-05", "2026-10-06", "2026-10-07"]);
assert.equal(marks["2026-10-04"].kind, "gap");
assert.equal(marks["2026-10-05"].kind, "no_record");
assert.equal(marks["2026-10-06"].kind, "partial");
assert.ok(marks["2026-10-06"].label.includes("37 of 40 questions attempted"));
assert.ok(marks["2026-10-06"].label.includes("Not plotted as a daily score"));
assert.equal(marks["2026-10-07"].kind, "unavailable");
for (const m of lay.marks) assert.equal(m.y, undefined);
assert.equal(lay.marks.filter((m) => m.kind === "pending").length, 20);       // 10-29 Oct after as_of
assert.equal(lay.message, null);

// An open (unresolved) day is a mark, never a point or a zero, and breaks the line (T13 review R2).
const open = C.layout(views["open-day"][0]);
assert.deepEqual(open.points.map((p) => p.date), ["2026-10-02"]);
const openMark = open.marks.find((m) => m.date === "2026-10-03");
assert.equal(openMark.kind, "open");
assert.equal(openMark.y, undefined);
assert.ok(openMark.label.includes("still open or unresolved"));
const joined = JSON.parse(JSON.stringify(several));
joined.rows = several.rows.filter((r) => ["2026-10-02", "2026-10-03"].includes(r.date));
joined.rows.splice(1, 0, { date: "2026-10-03", state: "open", record: null, eligible: false });
joined.rows = joined.rows.filter((r, i) => !(r.date === "2026-10-03" && r.state !== "open"));
assert.deepEqual(C.layout(joined).segments, []);

// Zero and one point.
const empty = C.layout(views["schedule-only"][0]);
assert.equal(empty.points.length, 0);
assert.equal(empty.segments.length, 0);
assert.equal(empty.message, "Waiting for daily results");
assert.equal(empty.marks.length, 28);                                            // all scheduled dates, pending
assert.ok(empty.marks.every((m) => m.kind === "pending"));
const one = C.layout(views["one-point"][0]);
assert.equal(one.points.length, 1);
assert.equal(one.segments.length, 0);                                            // one point, no line
assert.equal(one.message, "One daily test; more days are needed to show a pattern");

// A changed setup is a separate series: separate layouts, never one line.
const both = views["two-setups"];
assert.equal(both.length, 2);
const [newest, older] = both.map((s) => C.layout(s));
assert.deepEqual(newest.points.map((p) => p.date), ["2026-10-10", "2026-10-11", "2026-10-12"]);
assert.equal(newest.xTicks[0].label, "10 Oct");
assert.ok(older.points.every((p) => p.date < "2026-10-10"));
assert.ok(newest.segments.every((s) => s.every((p) => p.date >= "2026-10-10")));

// No verdict vocabulary anywhere in the layout module.
const source = fs.readFileSync(require.resolve("../site/results-chart.js"), "utf8").toLowerCase();
for (const word of ["stable", "nerf", "significan", "confidence", "decline", "improv", "degrad"]) {
  assert.ok(!source.replace(/\/\*[\s\S]*?\*\//g, "").includes(word), word);
}

process.stdout.write("results-chart.js: all assertions passed\n");
