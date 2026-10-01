// Renders a built page (dist-style folder, argv[2]) at a URL hash (argv[3], default
// "#models") with a minimal DOM stand-in, and prints {text, aria, hash} as JSON.
// Only the primitives the app uses are provided; interactive behaviour is checked in a
// real browser. Test use only.
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

class Node {
  constructor(tag) { this.tagName = tag; this.children = []; this.attrs = {}; this.ownText = ""; this.parentNode = null; }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }
  removeAttribute(k) { delete this.attrs[k]; }
  appendChild(c) { this.children.push(c); c.parentNode = this; return c; }
  insertBefore(c, ref) { const i = ref ? this.children.indexOf(ref) : -1; if (i < 0) this.children.push(c); else this.children.splice(i, 0, c); c.parentNode = this; return c; }
  removeChild(c) { this.children.splice(this.children.indexOf(c), 1); return c; }
  replaceChild(n, o) { const i = this.children.indexOf(o); this.children[i] = n; n.parentNode = this; return o; }
  get firstChild() { return this.children[0] || null; }
  addEventListener() {}
  focus() {}
  querySelector() { return null; }
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
for (const name of ["freshness.js", "directory.js", "data.js", "app.js"]) {
  vm.runInThisContext(fs.readFileSync(path.join(dir, name), "utf8"), { filename: name });
}
const aria = all().map((n) => n.getAttribute("aria-label")).filter(Boolean);
process.stdout.write(JSON.stringify({ text: body.textContent, aria, hash: location.hash }));
