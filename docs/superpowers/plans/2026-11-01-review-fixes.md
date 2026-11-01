# Review findings implementation plan

Goal: repair the reproducible defects in the 6fb2586 review without claiming unfinished product features are complete.
Architecture: retain FastAPI/SQLite, Vue and the existing PostgreSQL bank contract. B remains financial authority. Treat ambiguous submissions as unknown, retain quota, recover by stable key; reject unsupported scheduled payments instead of sending early.
Scope: the user authorized modifying the reviewed defects. Work in the existing isolated cloud checkout on codex/fix-reviewed-defects; no additional worktree, push or publication.

## Tasks

- [x] Execution: add failing regressions for post-confirm expiry, queued cancellation, future dates, missing checker, transaction rollback, unknown-result quota and recovery. Implement atomic state transitions and rerun execution/adapter suites.
- [x] A/B bridge: test dropped replies with an idempotent fake and the actual PostgreSQL bank; persist quote/lookup information in B's SQLite store and recover with the original submission identity. Confirm recovered bank reference is returned and never debit twice.
- [x] Cashflow: test non-default target amounts and update the purchase event to use goal_cents; retain the published 600000-cent oracle.
- [x] Frontend: regression-test authentication errors and per-action confirmation state. Keep transfer-password failures logged in; clear only expired action authorization. Replace fabricated home account values with authenticated account snapshots and refresh after transfer.
- [x] Wiring and quality: connect A read tools in the explicit bank dev path, preserve explicit unsupported D/mandate capabilities; isolate startup tests from the local-test override, derive the bank runtime test URL from its configured database. Install the frontend from the official registry with existing integrity hashes.
- [x] Verify: C4 quality runner, full root unittest, frontend regression/typecheck/build, PostgreSQL pytest/reconcile and real A/B lost-response integration. Review the diff and document remaining product gaps.

Decisions: no new production authentication, scheduling engine, full business pages, real bank or model credentials. Unsupported features remain explicit. Regressions must fail before each corresponding implementation change. Preserve synthetic data and published gold files.

Completion: 231 root unit tests, 103 PostgreSQL tests, 5 frontend tests and all C4 gates pass. Independent review finding about late session responses was reproduced and fixed; see docs/review-fixes.md. Branch retained locally, no push/merge/publication.
