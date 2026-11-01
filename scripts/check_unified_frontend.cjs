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
    listeners: {},
    classList: {add() {}, remove() {}, toggle() {}},
    addEventListener(type, handler) { this.listeners[type] = handler; },
    setAttribute() {}, removeAttribute() {}, focus() {},
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

const preservedPanels = {
  home: ['从一件事开始', '一个目标，几种安排', '接下来的固定支出'],
  bills: ['按类别看净支出', '账单问答', '发现需核查的线索'],
  subs: ['黄色 · 查询范围确认示意', '模拟云盘', '模拟健身'],
  future: ['30天日终余额', '调整假设', '方案说明', '查看30天余额表'],
  tasks: ['任务进度，一眼看清', '请求超时 ≠ 转账失败'],
  settings: ['最低留存余额', '保护云盘代扣', '规划账户'],
  review: ['离线参考对齐', '银行/安全验收', '未来执行轨迹应包含'],
  agent: ['智能体小智', 'agentPage'],
};

for (const route of Object.keys(preservedPanels)) {
  vm.runInContext(`show('${route}')`, context);
  assert(nodes.content.innerHTML.length > 150, route + ' must render meaningful content');
  assert(!nodes.content.innerHTML.includes('NaN'), route + ' rendered NaN');
  assert(!nodes.content.innerHTML.includes('undefined'), route + ' rendered undefined');
  for (const marker of preservedPanels[route]) {
    assert(nodes.content.innerHTML.includes(marker), route + ' lost existing panel: ' + marker);
  }
}

const nav = html.split('<nav id="nav"', 2)[1].split('</nav>', 1)[0];
assert(nav.indexOf('评审工作台') < nav.indexOf('智能体小智'));
assert(html.includes('id="authGate"'));
assert(html.includes('id="assistantRail"'));

(async () => {
  let sessionCalls = 0;
  context.fetch = async path => {
    if (path === '/api/auth/login') {
      return {ok: true, status: 200, json: async () => ({auth_token: 'token', username: 'test_user'})};
    }
    if (path === '/api/sessions') {
      sessionCalls += 1;
      return {ok: true, status: 200, json: async () => ({session_id: 'session-' + sessionCalls})};
    }
    return {ok: true, status: 200, json: async () => ({status: 'ready', provider: 'local'})};
  };
  document.getElementById('authUser').value = 'test_user';
  document.getElementById('authPassword').value = 'test-password-123';
  await nodes.authForm.listeners.submit({preventDefault() {}});
  assert.strictEqual(sessionCalls, 1, 'login must create or renew exactly one server session');

  context.fetch = async () => ({
    ok: false,
    status: 401,
    json: async () => ({detail: {code: 'AUTH_REQUIRED', message: '登录已失效'}}),
  });
  vm.runInContext("authToken='expired'; $('appShell').hidden=false; $('authGate').hidden=true", context);
  await assert.rejects(vm.runInContext("api('/api/sessions', {})", context), /登录已失效/);
  assert.strictEqual(nodes.appShell.hidden, true, 'expired auth must hide the application');
  assert.strictEqual(nodes.authGate.hidden, false, 'expired auth must return to login');
  assert.strictEqual(vm.runInContext('authToken', context), null, 'expired auth token must be cleared');
  console.log('Unified frontend runtime: 8 routes, preserved panels, login recovery, assistant rail and agent navigation passed.');
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
