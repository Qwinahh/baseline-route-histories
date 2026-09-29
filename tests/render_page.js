// Renders a built page (dist-style folder given as argv[2]) with a minimal DOM stand-in
// and prints {text, aria} as JSON: all text content and every aria-label. Test use only.
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

class Node {
  constructor(tag) { this.tagName = tag; this.children = []; this.attrs = {}; this.ownText = ""; this.parentNode = null; }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }
  appendChild(c) { this.children.push(c); c.parentNode = this; return c; }
  replaceChild(n, o) { const i = this.children.indexOf(o); this.children[i] = n; n.parentNode = this; return o; }
  get classList() { const cls = (this.attrs["class"] || "").split(/\s+/); return { contains: (c) => cls.includes(c) }; }
  set textContent(v) { this.children = []; this.ownText = String(v); }
  get textContent() { return this.ownText + this.children.map((c) => c.textContent).join(""); }
  walk(fn) { fn(this); this.children.forEach((c) => c.walk && c.walk(fn)); }
}
class Text { constructor(s) { this.textContent = s; } }

const body = new Node("body");
const app = body.appendChild(new Node("main"));
app.setAttribute("id", "app");
function all() { const out = []; body.walk((n) => out.push(n)); return out; }
global.window = global;
global.document = {
  body,
  createElement: (t) => new Node(t),
  createElementNS: (ns, t) => new Node(t),
  createTextNode: (s) => new Text(s),
  getElementById: (id) => all().find((n) => n.getAttribute("id") === id) || null,
  querySelectorAll: () => [],
  querySelector: () => null,
};
global.setInterval = () => 0;

const dir = process.argv[2];
for (const name of ["freshness.js", "data.js", "app.js"]) {
  vm.runInThisContext(fs.readFileSync(path.join(dir, name), "utf8"), { filename: name });
}
const aria = all().map((n) => n.getAttribute("aria-label")).filter(Boolean);
process.stdout.write(JSON.stringify({ text: body.textContent, aria }));
