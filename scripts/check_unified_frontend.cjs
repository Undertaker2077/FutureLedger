// Runtime smoke test for the single live FutureLedger frontend.
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const path = require('path');

const root = path.resolve(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'demo/web/index.html'), 'utf8');
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)];
assert(scripts.length, 'live frontend must contain an inline script');
const code = scripts.at(-1)[1];

function node() {
  return {
    innerHTML: '', textContent: '', value: '', hidden: false, disabled: false,
    className: '', style: {}, dataset: {}, children: [],
    classList: {add() {}, remove() {}, toggle() {}},
    addEventListener() {}, setAttribute() {}, removeAttribute() {}, focus() {},
    showModal() {}, close() {}, querySelector() { return node(); },
    append(...items) { this.children.push(...items); }, replaceChildren(...items) { this.children = items; },
  };
}

const nodes = {};
const document = {
  getElementById(id) { return nodes[id] ??= node(); },
  createElement() { return node(); },
};
const context = {
  document,
  window: {},
  localStorage: {getItem() { return '{}'; }, setItem() {}},
  crypto: {randomUUID() { return 'smoke-id'; }},
  fetch: async () => ({ok: true, json: async () => ({status: 'ready', provider: 'local'})}),
  setTimeout() {}, clearTimeout() {}, console,
};
vm.createContext(context);
vm.runInContext(code, context);

for (const route of ['home', 'bills', 'subs', 'future', 'tasks', 'settings', 'review', 'agent']) {
  vm.runInContext(`show('${route}')`, context);
  assert(nodes.content.innerHTML.length > 150, route + ' must render meaningful content');
  assert(!nodes.content.innerHTML.includes('NaN'), route + ' rendered NaN');
  assert(!nodes.content.innerHTML.includes('undefined'), route + ' rendered undefined');
}

assert(nodes.nav.innerHTML.indexOf('评审工作台') < nodes.nav.innerHTML.indexOf('智能体小智'));
assert(html.includes('id="authGate"'));
assert(html.includes('id="assistantRail"'));
console.log('Unified frontend runtime: 8 routes, login gate, assistant rail and agent navigation passed.');
