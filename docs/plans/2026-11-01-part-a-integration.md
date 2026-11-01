# Part A / teammate archive integration plan

## Finding

The archive does not contain a new Role A Mock Bank implementation relative to the current repository. `services/mock-bank/` and the A-owned contracts are already present in the current project. The substantive new code in the archive is `apps/web/`, a Vue 3 + TypeScript + Vite frontend scaffold. It currently has a home page, assistant page and review page, while the other routes are placeholders and the assistant defaults to mock mode.

## Scope

In scope:

- Add the archive's `apps/web/` Vue application without committing `node_modules`, npm caches or build output.
- Connect it to the existing `demo.api` authentication, session and chat contracts.
- Make the LLM-backed API the default; keep mock data only for explicit local component development, never as the production fallback.
- Implement the seven dashboard routes and the assistant route with explicit loading, error and unavailable states.
- Preserve the existing standalone HTML demo and all A/B/C/D backend contracts.

Out of scope:

- Replacing the existing FastAPI demo API with a new backend.
- Claiming that the Vue app is a production bank client or connecting real bank credentials.
- Implementing new bank ledger behavior when the archive does not contain a Role A delta.

## Integration decisions

1. The Vue app uses `/api/auth/register`, `/api/auth/login`, `/api/auth/logout`, `/api/sessions`, `/api/ask`, `/api/actions/*` and `/api/queries/*` from `demo.api`.
2. Authentication is a whole-app gate. The browser stores only the demo auth token/session state in memory; passwords never enter chat messages or LLM prompts.
3. Query results and transfer confirmations are rendered from server responses. The browser does not compile SQL or authorize a transfer.
4. The Vue app is served by Vite in development and can be built to static assets. The existing FastAPI HTML demo remains the compatibility path until a static-asset mount is deliberately added.

## Feature slices

1. **Foundation:** copy Vue source/package manifests, make `npm run check` and `npm run build` pass.
2. **Authentication and API client:** register/login/logout, session creation, expired-session recovery and visible API errors.
3. **Assistant:** query/clarification/result rendering, charts/tables and transfer preview/reauthentication.
4. **Dashboard routes:** bills, subscriptions, future ledger, tasks and settings show honest API-backed or unavailable states; no fabricated success claims.
5. **Verification:** TypeScript check, production build, backend Text2SQL regression, existing HTML smoke, and a browser smoke when a browser runner is available.

## Acceptance checks

- `npm run check` passes in `apps/web`.
- `npm run build` passes in `apps/web`.
- The Vue app can log in against the existing FastAPI demo and create a server session.
- A query reaches `/api/ask` and displays the returned status/chart/rows without exposing SQL or internal IDs.
- A transfer stops at preview/password/category confirmation and reports server errors without pretending to succeed.
- Logout and expired sessions return to the login gate.
- Existing backend and HTML prototype tests remain green.

