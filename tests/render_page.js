// Renders a built page (dist-style folder, argv[2]) at a URL hash (argv[3], default
// "#models") with a minimal DOM stand-in, and prints {text, aria, hash} as JSON. An optional
// argv[4] selects a daily test setup (the #daily-setup selector's value) and fires its change event;
// the output then also counts daily and total chart SVGs and reports the selected setup.
// Only the primitives the app uses are provided; interactive behaviour is checked in a
// real browser. Test use only.
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
};

const dir = process.argv[2];
for (const name of ["freshness.js", "directory.js", "results-chart.js", "data.js", "app.js"]) {
  vm.runInThisContext(fs.readFileSync(path.join(dir, name), "utf8"), { filename: name });
}
const selector = all().find((n) => n.getAttribute("id") === "daily-setup");
if (process.argv[4] !== undefined) {
  if (!selector) throw new Error("No setup selector");
  selector.value = process.argv[4];
  selector.dispatchEvent({ type: "change" });
}
const svgs = all().filter((n) => n.tagName === "svg");
const dailyCharts = svgs.filter((n) => (n.getAttribute("class") || "").split(/\s+/).includes("daily-chart")).length;
const aria = all().map((n) => n.getAttribute("aria-label")).filter(Boolean);
process.stdout.write(JSON.stringify({ text: body.textContent, aria, hash: location.hash, dailyCharts,
  totalCharts: svgs.length, selectedSetup: selector ? selector.value : null }));
