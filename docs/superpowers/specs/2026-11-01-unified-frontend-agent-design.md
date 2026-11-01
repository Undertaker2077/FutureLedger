# Unified FutureLedger Frontend Design

## Intent

FutureLedger must expose one browser application rather than a separate offline dashboard and standalone chat page. The dashboard shown in `prototype/index.html` is the product shell and default experience. The working chatbot becomes a sidebar destination named **智能体小智**, placed immediately below **评审工作台**. Login and first-password setup gate the whole application.

## Goals

- Preserve all existing dashboard destinations and panels: 银行总览、账单分析、订阅与代扣、未来账本、任务中心、个人偏好、评审工作台, plus the persistent right-side assistant panel.
- Add 智能体小智 directly below 评审工作台 in the left navigation.
- Move the functional conversation list, chat composer, result cards, CSV export, and synthetic transfer confirmation flow into the 智能体小智 page.
- Reuse the existing `demo.api` authentication, session, query, planning, and action endpoints.
- Show the existing login/first-password form before any application content is usable.
- Keep the responsive desktop/mobile behavior and the dashboard visual language from the prototype.
- Serve the unified application from `/` on the existing demo server.

## Non-goals

- Do not replace the legacy demo API with the newer C/A/B service stack in this change.
- Do not claim production authentication, banking, or persistence.
- Do not introduce Vue/Vite or a new package toolchain; this change consolidates the existing HTML applications.
- Do not remove or redesign existing dashboard panels.

## Constraints

- Credentials remain in the dedicated authentication and reauthentication forms; they never enter chat history or model prompts.
- The browser does not decide authorization. It only renders server responses from `demo.api`.
- Chat is unavailable until login creates an authenticated server session.
- Server restarts invalidate in-memory auth/session tokens and return the UI to login.
- The live application is `demo/web/index.html`; `prototype/index.html` remains a design reference only.

## Approaches

### Selected: consolidate into the existing live demo HTML

Rebuild `demo/web/index.html` with the prototype shell and copy the working chat/auth behaviors into dedicated page renderers. This preserves the existing FastAPI serving path, requires no new build system, and produces one localhost application immediately.

### Rejected: serve the prototype and retrofit API routes into it

This would make an offline reference file the production entry point and complicate its existing `sample-summary.json` smoke harness.

### Deferred: create the formal Vue application under `apps/web/`

This matches the long-term architecture but is a larger project involving a package toolchain, component system, routing, state management, and deployment configuration. It is not required to consolidate the two current pages.

## Interaction design

The default post-login route is 银行总览. The top bar displays the authenticated username rather than a hard-coded identity. The existing right-side assistant remains on dashboard routes and can navigate to 智能体小智. The 智能体小智 page uses the full central work area for conversation history and result cards while keeping the global left navigation. Logout returns to the login gate and clears the in-memory browser identity.

## Verification

- Static frontend tests pin navigation order, preserved panels, login gate, and API endpoint wiring.
- Existing demo API tests cover registration, login, session ownership, queries, CSV export, and transfer confirmation.
- The prototype smoke test remains green, proving the reference dashboard was not removed.
- Browser QA verifies login, dashboard navigation, 智能体小智 chat, logout, and responsive layout.
