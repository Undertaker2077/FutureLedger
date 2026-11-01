# Unified FutureLedger Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Serve one authenticated FutureLedger dashboard with the API-connected 智能体小智 as a sidebar destination below 评审工作台.

**Architecture:** Keep `demo.api` and its endpoints unchanged. Replace the standalone layout in `demo/web/index.html` with the prototype dashboard shell, preserving every dashboard renderer and the persistent assistant panel while integrating the existing authentication, chat, result, CSV, and transfer-confirmation JavaScript into an `agent` route.

**Tech Stack:** FastAPI, plain HTML/CSS/JavaScript, SQLite demo fixture, Node smoke checks, Python unittest/TestClient.

**Spec:** `docs/superpowers/specs/2026-11-01-unified-frontend-agent-design.md`

## Global Constraints

- Preserve every existing dashboard destination and the persistent right-side assistant panel.
- Place 智能体小智 immediately after 评审工作台 in sidebar order.
- Gate the entire application with the existing login/first-password flow.
- Credentials must never enter chat history, model prompts, localStorage, or rendered messages.
- Reuse existing same-origin `/api/*` endpoints; do not create browser-side authorization rules.
- Do not add a frontend build tool or dependency.

## Review Focus

- A server restart invalidates auth/session tokens: the next request must recover by returning to login, not show stale authenticated state.
- Empty or corrupt localStorage conversation data must not prevent the unified application from loading.
- Switching between dashboard routes and 智能体小智 must preserve conversations without duplicating navigation or panels.
- A transfer password must remain only in the reauthentication form and be cleared after every attempt.
- Mobile layout must keep navigation, content, assistant, and chat composer reachable without horizontal clipping.

---

### Task 1: Pin the unified shell contract

**Files:**
- Modify: `tests/test_text2sql_demo.py`
- Create: `scripts/check_unified_frontend.cjs`

**Interfaces:**
- Consumes: `GET /` returning the live HTML string.
- Produces: regression checks for nav order, preserved dashboard panels, login gate, agent route, and endpoint wiring.

- [ ] **Step 1: Write failing Python and Node checks**

Add `test_home_serves_unified_dashboard_with_agent_and_login` asserting the live HTML contains all eight sidebar destinations in order, the right-side assistant, `authGate`, `agentPage`, and existing API paths. Add a Node smoke check that extracts the live page script, renders all eight routes with browser stubs, and asserts each route has non-empty content without `NaN` or `undefined`.

- [ ] **Step 2: Run checks and verify RED**

Run: `conda run --no-capture-output -n futureledger-bank python -m unittest tests.test_text2sql_demo.Text2SQLDemoTests.test_home_serves_unified_dashboard_with_agent_and_login -v && node scripts/check_unified_frontend.cjs`

Expected: FAIL because the standalone chat HTML lacks dashboard destinations and the unified smoke target.

- [ ] **Step 3: Commit the failing contract tests**

```bash
git add tests/test_text2sql_demo.py scripts/check_unified_frontend.cjs
git commit -m "test: define unified FutureLedger frontend contract"
```

### Task 2: Build the unified authenticated dashboard

**Files:**
- Modify: `demo/web/index.html`

**Interfaces:**
- Consumes: existing `/api/health`, `/api/auth/*`, `/api/sessions`, `/api/ask`, `/api/actions/*`, and `/api/queries/*` response shapes.
- Produces: `show(pageId)`, dashboard renderers, `agentPage()`, login/logout state, conversation state, result rendering, and transfer reauthentication UI.

- [ ] **Step 1: Implement the prototype shell and preserved dashboard renderers**

Use the prototype visual tokens and all seven current dashboard page functions. Keep the right-side assistant and add an `agent` route label `智能体小智` after `review`.

- [ ] **Step 2: Integrate authentication as a whole-app gate**

Reuse the existing register/login/logout calls. On login, set the authenticated username in the top bar, create or renew the server session, reveal the application, and default to `home`. On logout or authentication expiry, clear runtime credentials and show `authGate`.

- [ ] **Step 3: Integrate the working chatbot as `agentPage()`**

Move conversation selection, message rendering, examples, composer, result cards, charts/tables, CSV links, session renewal, and API errors into the central content renderer without a second global sidebar.

- [ ] **Step 4: Preserve the transfer confirmation flow**

Keep the dedicated password form, category selection, authorization ID, final confirmation, and password clearing behavior. No password appears in messages or localStorage.

- [ ] **Step 5: Run focused checks and verify GREEN**

Run: `conda run --no-capture-output -n futureledger-bank python -m unittest tests.test_text2sql_demo.Text2SQLDemoTests.test_home_serves_unified_dashboard_with_agent_and_login -v && node scripts/check_unified_frontend.cjs`

Expected: PASS.

- [ ] **Step 6: Commit the unified application**

```bash
git add demo/web/index.html
git commit -m "feat: unify dashboard and chatbot frontend"
```

### Task 3: Documentation and complete verification

**Files:**
- Modify: `README.md`
- Modify: `docs/02-功能清单与页面.md`
- Modify: `scripts/check_prototype.cjs` only if required to keep the original reference smoke compatible.

**Interfaces:**
- Consumes: the unified application behavior from Task 2.
- Produces: accurate launch instructions and explicit distinction between the live unified demo and retained prototype reference.

- [ ] **Step 1: Update documentation**

Document the unified dashboard, 智能体小智 route, whole-app authentication, port `8003` local launch used in this workspace, and the fact that the formal Vue rewrite is still deferred.

- [ ] **Step 2: Run frontend and regression verification**

Run: `node scripts/check_unified_frontend.cjs && node scripts/check_prototype.cjs && conda run --no-capture-output -n futureledger-bank python -m unittest discover -s tests -q`

Expected: all checks pass with no failures.

- [ ] **Step 3: Run hygiene checks**

Run: `git diff --check && git status --short`

Expected: no whitespace errors and only intended documentation changes before commit.

- [ ] **Step 4: Commit documentation**

```bash
git add README.md docs/02-功能清单与页面.md docs/superpowers/specs/2026-11-01-unified-frontend-agent-design.md docs/superpowers/plans/2026-11-01-unified-frontend-agent.md
git commit -m "docs: describe unified FutureLedger frontend"
```
