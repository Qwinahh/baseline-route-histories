// Renders a built page (dist-style folder, argv[2]) at a URL hash (argv[3], default
// "#models") with a minimal DOM stand-in, and prints {text, aria, hash} as JSON. An optional
// argv[4] selects a daily test setup (the #daily-setup selector's value) and fires its change event;
// the output then also counts daily and total chart SVGs and reports the selected setup.
// Only the primitives the app uses are provided; interactive behaviour is checked in a
// real browser. Test use only. RENDER_NOW (an ISO time in the environment) fixes the page clock for fixtures;
// RENDER_ADVANCE then moves that clock after the first render and refreshes the open page the way a browser would
// (RENDER_REFRESH "tick": the minute timer, "visibility": a return from a background tab), keeping the same DOM.
// RENDER_MODE ("score" or "change") presses that graph-view button first, as a visitor would.
// RENDER_WIDTH sets the viewport width the page lays its graph out for; RENDER_PICK chooses a model id in the
// phone selector (the resulting hash is reported); RENDER_SEARCH types into the rail search first.
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

class Node {
  constructor(tag) { this.tagName = tag; this.children = []; this.attrs = {}; this.ownText = ""; this.parentNode = null; this.listeners = {}; }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }
  removeAttribute(k) { delete this.attrs[k]; }
  appendChild(c) { this.children.push(c); c.parentNode = this; return c; }
  insertBefore(c, ref) { const i = ref ? this.children.indexOf(ref) : -1; if (i < 0) this.children.push(c); else this.children.splice(i, 0, c); c.parentNode = this; return c; }
  removeChild(c) { this.children.splice(this.children.indexOf(c), 1); return c; }
  replaceChild(n, o) { const i = this.children.indexOf(o); this.children[i] = n; n.parentNode = this; return o; }
  get firstChild() { return this.children[0] || null; }
  addEventListener(type, fn) { (this.listeners[type] || (this.listeners[type] = [])).push(fn); }
  dispatchEvent(event) { event.target = this; (this.listeners[event.type] || []).forEach((fn) => fn.call(this, event)); }
  focus() {}
  querySelector() { return null; }
  get classList() { const cls = (this.attrs["class"] || "").split(/\s+/); return { contains: (c) => cls.includes(c) }; }
  set textContent(v) { this.children = []; this.ownText = String(v); }
  get textContent() { return "hidden" in this.attrs ? "" : this.ownText + this.children.map((c) => c.textContent).join(""); }
  walk(fn) { fn(this); this.children.forEach((c) => c.walk && c.walk(fn)); }
}
class Text { constructor(s) { this.textContent = s; } }

const body = new Node("body");
const app = body.appendChild(new Node("main"));
app.setAttribute("id", "app");
function all() { const out = []; body.walk((n) => out.push(n)); return out; }
const location = { hash: process.argv[3] || "#models" };
global.window = global;
global.location = location;
global.history = { replaceState: (_s, _t, hash) => { location.hash = hash; } };
global.addEventListener = () => {};
global.setInterval = () => 0;
global.document = {
  body,
  createElement: (t) => new Node(t),
  createElementNS: (ns, t) => new Node(t),
  createTextNode: (s) => new Text(s),
  getElementById: (id) => all().find((n) => n.getAttribute("id") === id) || null,
  querySelectorAll: () => [],
  querySelector: () => null,
  hidden: false,
  listeners: {},
  addEventListener(type, fn) { (this.listeners[type] || (this.listeners[type] = [])).push(fn); },
};

if (process.env.RENDER_NOW) { const fixed = Date.parse(process.env.RENDER_NOW); Date.now = () => fixed; }
if (process.env.RENDER_WIDTH) global.innerWidth = Number(process.env.RENDER_WIDTH);
const dir = process.argv[2];
for (const name of ["freshness.js", "directory.js", "results-chart.js", "measured.js", "data.js", "app.js"]) {
  vm.runInThisContext(fs.readFileSync(path.join(dir, name), "utf8"), { filename: name });
}
const selector = all().find((n) => n.getAttribute("id") === "daily-setup");
if (process.argv[4] !== undefined) {
  if (!selector) throw new Error("No setup selector");
  selector.value = process.argv[4];
  selector.dispatchEvent({ type: "change" });
}
function byClass(name) { return all().filter((n) => (n.getAttribute && (n.getAttribute("class") || "").split(/\s+/).includes(name))); }
function text(n) { return n ? n.textContent : null; }
if (process.env.RENDER_MODE) {
  const button = all().find((n) => n.tagName === "button" && n.getAttribute("data-mode") === process.env.RENDER_MODE);
  if (!button) throw new Error("No graph-view button " + process.env.RENDER_MODE);
  button.dispatchEvent({ type: "click" });
}
if (process.env.RENDER_SEARCH !== undefined) {         // type into the rail search, as a visitor would
  const q = all().find((n) => n.getAttribute("id") === "q");
  q.value = process.env.RENDER_SEARCH;
  q.dispatchEvent({ type: "input" });
}
if (process.env.RENDER_PICK) {
  const pick = all().find((n) => n.getAttribute("id") === "model-picker");
  pick.value = process.env.RENDER_PICK;
  pick.dispatchEvent({ type: "change" });
}
let kept = null;
if (process.env.RENDER_ADVANCE) {
  const nodes = all(), charts = nodes.filter((n) => n.tagName === "svg");
  const later = Date.parse(process.env.RENDER_ADVANCE);
  Date.now = () => later;
  if (process.env.RENDER_REFRESH === "visibility") {
    document.hidden = true; (document.listeners.visibilitychange || []).forEach((fn) => fn({ type: "visibilitychange" }));
    document.hidden = false; (document.listeners.visibilitychange || []).forEach((fn) => fn({ type: "visibilitychange" }));
  } else window.BaselinePage.tick();
  const after = new Set(all());
  kept = { nodes: nodes.filter((n) => after.has(n)).length, of: nodes.length,
           charts: charts.filter((n) => after.has(n)).length, chartsBefore: charts.length };
}
const svgs = all().filter((n) => n.tagName === "svg");
const dailyCharts = svgs.filter((n) => (n.getAttribute("class") || "").split(/\s+/).includes("daily-chart")).length;
const aria = all().map((n) => n.getAttribute("aria-label")).filter(Boolean);
// The rail (one entry per tested model), the movement links and the selected model's workspace.
const modelRows = byClass("rail-item").map((n) => {
  const a = n.children[0];
  return { name: a.children[0].textContent, href: a.getAttribute("href"), current: a.getAttribute("aria-current") === "true" };
});
const moves = byClass("rail-moves").filter((n) => !("hidden" in n.attrs)).flatMap((n) => n.walk ? (() => {
  const out = []; n.walk((c) => { if (c.tagName === "a") out.push({ text: c.textContent, href: c.getAttribute("href") }); }); return out; })() : []);
const picker = all().find((n) => n.getAttribute("id") === "model-picker");
const pressed = all().find((n) => n.tagName === "button" && n.getAttribute("data-mode") && n.getAttribute("aria-pressed") === "true");
const changeButton = all().find((n) => n.tagName === "button" && n.getAttribute("data-mode") === "change");
const graph = svgs.find((n) => (n.getAttribute("class") || "").split(/\s+/).includes("daily-chart"));
const workspace = byClass("workspace")[0];
const selected = workspace ? {
  kicker: text(byClass("ws-kicker")[0]) || "", name: text(workspace.children.find((n) => n.tagName === "h1")),
  context: text(byClass("context")[0]), score: text((byClass("score")[0] || { children: [] }).children[0]),
  observation: text(byClass("observation")[0]), cautions: byClass("caution").map(text),
  mode: pressed ? pressed.getAttribute("data-mode") : null,
  changeDisabled: changeButton ? changeButton.getAttribute("aria-disabled") === "true" : null,
  changeNote: text(byClass("mode-note")[0]), graphMode: graph ? graph.getAttribute("data-mode") : null,
  axisTitle: text(byClass("axis-title")[0]), caveat: text(byClass("caveat")[0]),
  ticks: graph ? byClass("tick").map(text) : [], pointLabels: byClass("point-label").map(text).filter(Boolean),
} : null;
const service = all().find(n => n.getAttribute("id") === "model-service");
// What the graph actually draws: each mark's kind and visible glyph, the lane label, the viewBox and hit areas.
const chart = graph ? {
  viewBox: graph.getAttribute("viewBox"),
  marks: byClass("mark").map((g) => ({ kind: g.getAttribute("data-kind"),
    glyph: (g.children.find((c) => c.tagName === "text") || { textContent: "" }).textContent,
    label: g.getAttribute("aria-label"), focusable: g.getAttribute("tabindex") === "0" })),
  lane: text(byClass("lane-label")[0]),
  hits: byClass("hit").map((h) => Number(h.getAttribute("r") || h.getAttribute("width") / 2)),
  points: byClass("score-point").length,
} : null;
const railLinks = byClass("rail-link").map((a) => a.getAttribute("href"));
const moveLinks = byClass("rail-moves").flatMap((n) => { const out = []; n.walk((c) => { if (c.tagName === "a") out.push(c.getAttribute("href")); }); return out; });

process.stdout.write(JSON.stringify({ text: body.textContent, aria, hash: location.hash, dailyCharts,
  totalCharts: svgs.length, selectedSetup: selector ? selector.value : null, modelRows,
  selectedService: service ? service.value : null,
  serviceOptions: service ? service.children.map(n=>n.getAttribute("value")) : [], selected, moves,
  picker: picker ? { value: picker.value, options: picker.children.map((n) => n.getAttribute("value")).filter(Boolean) } : null,
  chart, railLinks, moveLinks,
  kept }));
