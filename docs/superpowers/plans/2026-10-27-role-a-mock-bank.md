# Role A Mock Bank Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver role A's PostgreSQL-backed Mock Bank with deterministic data, read APIs, balanced and idempotent transfers, mandate cancellation, reconciliation, and executable A-side evidence for all 20 shared acceptance cases.

**Architecture:** A standalone layered FastAPI service under `services/mock-bank/` exposes a typed Bank adapter and HTTP API. Domain validation and canonical hashes are independent of I/O; `BankService` coordinates SQLAlchemy repositories whose PostgreSQL transactions lock bank facts and atomically update transfers, balances, transactions, and journal entries.

**Tech Stack:** Conda/Python 3.13, FastAPI, Pydantic 2, SQLAlchemy 2, Alembic, psycopg 3, PostgreSQL 18.6 in Docker Compose, pytest, HTTPX.

**Spec:** `docs/superpowers/specs/2026-10-27-role-a-mock-bank-design.md`

## Global Constraints

- Use Conda; do not create `venv`, `.venv`, `env`, or `.env` environments.
- PostgreSQL is `postgres:18.6`; no host PostgreSQL installation is required.
- CNY only; all amounts are integer cents and booleans are not valid integers.
- Business dates use `Asia/Shanghai`; stored instants are timezone-aware.
- Every API response is `{data, error, request_id}` and Pydantic request models use `extra="forbid"`.
- Internal service authentication and `X-Authenticated-User` subject identity are separate inputs.
- The bank service never parses natural language, applies app preferences, authorizes actions, schedules work, or claims merchant-contract cancellation.
- Reset is allowed only with `FUTURELEDGER_ENV in {test, development}` and `FUTURELEDGER_ALLOW_RESET=1`.
- The existing SQLite demo stays operational and its generated runtime files remain ignored.
- Never mark a shared A+B/A+C scenario fully passed until collaborator-owned orchestration has run; emit `A_SIDE_PASS` instead.

## Review Focus

- Python treats `True` as an `int`: `test_quote_rejects_bool_amount` in Task 1 must prove booleans return `INVALID_AMOUNT`.
- Pagination cursors can be replayed across users: `test_transaction_cursor_is_subject_bound` in Task 3 must return `FORBIDDEN` without leaking existence.
- A replacement quote can share canonical parameters: `test_replacement_quote_accepts_same_unbound_key` in Task 5 must succeed once while changed parameters conflict.
- Database exceptions after account debit could leave partial writes: `test_before_commit_failure_rolls_back_all_bank_facts` in Task 5 must prove balance, transfer, transaction, and journal counts are unchanged.
- Concurrent cancellation with different keys can race: `test_concurrent_mandate_cancel_returns_one_stable_transition` in Task 6 must leave one cancelled mandate and two stable action results without reopening it.

---

### Task 1: Package, Conda Environment, Configuration, and Domain Contracts

**Files:**
- Create: `services/mock-bank/pyproject.toml`
- Create: `services/mock-bank/environment.yml`
- Create: `services/mock-bank/requirements-bank.txt`
- Create: `services/mock-bank/mock_bank/__init__.py`
- Create: `services/mock-bank/mock_bank/config.py`
- Create: `services/mock-bank/mock_bank/contracts.py`
- Create: `services/mock-bank/mock_bank/domain.py`
- Create: `services/mock-bank/tests/unit/test_domain.py`

**Interfaces:**
- Consumes: environment variables only.
- Produces: `Settings.from_env()`, `BankError`, `TransferRequest`, `TransferQuote`, `TransferResult`, `TransactionQuery`, `MandateResult`, `canonical_transfer_hash(subject, request, fee_cents)`, and `validate_idempotency_key(key)`.

- [ ] **Step 1: Write failing unit tests**

Add tests for positive integer cents, `True`, zero/negative values, non-CNY currency, canonical-hash stability/order independence, hash changes for account/recipient/amount/fee changes, and idempotency keys outside 8–128 visible ASCII characters.

- [ ] **Step 2: Run the domain tests and confirm import failures**

Run: `conda run --no-capture-output -n base python -m pytest services/mock-bank/tests/unit/test_domain.py -v`

Expected: FAIL because `mock_bank.domain` and contracts do not exist.

- [ ] **Step 3: Add the package and exact domain interfaces**

Implement strict Pydantic models and:

```python
def canonical_transfer_hash(subject: str, request: TransferRequest, fee_cents: int) -> str: ...
def validate_idempotency_key(key: str) -> str: ...
```

Use canonical UTF-8 JSON with sorted keys and SHA-256. Raise `BankError(code, message, recoverable, next_action, http_status)` for business validation.

- [ ] **Step 4: Run unit tests**

Run: `PYTHONPATH=services/mock-bank conda run --no-capture-output -n base python -m pytest services/mock-bank/tests/unit/test_domain.py -v`

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

```bash
git add services/mock-bank
git commit -m "feat: scaffold mock bank domain"
```

### Task 2: PostgreSQL Schema, Migration, Seed/Reset, and Reconciliation Base

**Files:**
- Create: `services/mock-bank/compose.bank.yml`
- Create: `services/mock-bank/Dockerfile`
- Create: `services/mock-bank/alembic.ini`
- Create: `services/mock-bank/alembic/env.py`
- Create: `services/mock-bank/alembic/versions/0001_bank_schema.py`
- Create: `services/mock-bank/mock_bank/db.py`
- Create: `services/mock-bank/mock_bank/models.py`
- Create: `services/mock-bank/mock_bank/seed.py`
- Create: `services/mock-bank/mock_bank/reconcile.py`
- Create: `services/mock-bank/tests/conftest.py`
- Create: `services/mock-bank/tests/integration/test_seed_reconcile.py`
- Modify: `db/schema.sql`

**Interfaces:**
- Consumes: repository fixtures under `data/`, `Settings.database_url`.
- Produces: `create_engine_from_settings(settings)`, SQLAlchemy table metadata, `reset_database(settings, fixture_root)`, `reconcile(session) -> ReconciliationReport`, and CLI modules `python -m mock_bank.seed reset` / `python -m mock_bank.reconcile --json`.

- [ ] **Step 1: Write failing PostgreSQL integration tests**

Assert reset is refused outside test/development, deterministic reset yields three accounts/five recipients/four mandates/3,839 transactions, `acc_daily.balance_cents == 900000`, and a fresh reconciliation report is valid.

- [ ] **Step 2: Start PostgreSQL and verify tests fail before migrations**

Run: `docker compose -f services/mock-bank/compose.bank.yml up -d postgres`

Run: `PYTHONPATH=services/mock-bank FUTURELEDGER_ENV=test FUTURELEDGER_ALLOW_RESET=1 conda run --no-capture-output -n base python -m pytest services/mock-bank/tests/integration/test_seed_reconcile.py -v`

Expected: FAIL because migrations/reset/reconciliation are absent.

- [ ] **Step 3: Implement migration and schema snapshot**

Create executable `app.users` plus bank accounts, recipients, transactions, transfer quotes, transfers, journal entries/lines, mandates, and mandate actions. Add composite ownership foreign keys, unique idempotency constraints, runtime/read roles, and a deferred constraint trigger rejecting non-zero journal sums.

- [ ] **Step 4: Implement guarded reset and reconciliation**

Implement:

```python
def reset_database(settings: Settings, fixture_root: Path) -> SeedReport: ...
def reconcile(session: Session) -> ReconciliationReport: ...
```

Reset bank-owned facts transactionally from JSON/CSV and clear quotes/actions. Reconciliation checks journal balance, transfer evidence, account-derived balance, idempotency hash uniqueness, and mandate/action agreement.

- [ ] **Step 5: Run migration/seed/reconciliation tests**

Run the Task 2 pytest command again.

Expected: PASS with a valid reconciliation report.

- [ ] **Step 6: Commit Task 2**

```bash
git add services/mock-bank db/schema.sql
git commit -m "feat: add mock bank database lifecycle"
```

### Task 3: Authenticated Read Repository, Service, and HTTP API

**Files:**
- Create: `services/mock-bank/mock_bank/auth.py`
- Create: `services/mock-bank/mock_bank/repository.py`
- Create: `services/mock-bank/mock_bank/service.py`
- Create: `services/mock-bank/mock_bank/api.py`
- Create: `services/mock-bank/tests/integration/test_read_service.py`
- Create: `services/mock-bank/tests/contract/test_read_api.py`

**Interfaces:**
- Consumes: Task 1 contracts and Task 2 session factory.
- Produces: `BankRepository`, `BankService.get_balance`, `list_transactions`, `resolve_recipient`, `list_mandates`, `get_mandate_status`, and `create_app(settings, session_factory) -> FastAPI`.

- [ ] **Step 1: Write failing read-service tests**

Test owned balance, cross-user `FORBIDDEN`, verified and unverified recipient facts, transaction filters/order/limit/cursor, invalid date ranges, unknown kind/status, subject-bound cursors, mandate scoping, and no memo in public results.

- [ ] **Step 2: Write failing HTTP contract tests**

Test missing/wrong service token, missing subject header, request IDs, envelope shape, capabilities, liveness/readiness, and that cross-user IDs return the same public error shape as unknown IDs.

- [ ] **Step 3: Run Task 3 tests and confirm failures**

Run: `PYTHONPATH=services/mock-bank FUTURELEDGER_ENV=test FUTURELEDGER_ALLOW_RESET=1 FUTURELEDGER_INTERNAL_TOKEN=test-internal-token conda run --no-capture-output -n base python -m pytest services/mock-bank/tests/integration/test_read_service.py services/mock-bank/tests/contract/test_read_api.py -v`

Expected: FAIL because repository/service/API are absent.

- [ ] **Step 4: Implement repository reads and opaque cursor signing**

`BankRepository` receives a SQLAlchemy `sessionmaker`. Encode cursors as URL-safe base64 JSON containing subject, last `posted_at`, and last ID plus an HMAC using the internal token; reject invalid or cross-subject cursors.

- [ ] **Step 5: Implement service methods and FastAPI envelope**

Map `BankError` centrally to `{data:null,error:{code,message,recoverable,next_action},request_id}`. Successful responses set `error:null`. Close database sessions through FastAPI dependencies and dispose the engine on shutdown.

- [ ] **Step 6: Run Task 3 tests**

Run the Task 3 pytest command again.

Expected: PASS.

- [ ] **Step 7: Commit Task 3**

```bash
git add services/mock-bank/mock_bank services/mock-bank/tests
git commit -m "feat: expose mock bank read API"
```

### Task 4: Quote and Atomic Balanced Transfer

**Files:**
- Modify: `services/mock-bank/mock_bank/contracts.py`
- Modify: `services/mock-bank/mock_bank/repository.py`
- Modify: `services/mock-bank/mock_bank/service.py`
- Modify: `services/mock-bank/mock_bank/api.py`
- Create: `services/mock-bank/tests/integration/test_transfer_success.py`
- Create: `services/mock-bank/tests/contract/test_transfer_api.py`

**Interfaces:**
- Consumes: `TransferRequest`, canonical hash, repository session factory.
- Produces: `BankService.quote_transfer(subject, request, now)`, `submit_transfer(subject, quote_id, params_hash, idempotency_key, fault=None)`, and `get_transfer_status(subject, transfer_id)`.

- [ ] **Step 1: Write failing `transfer_01` tests**

Quote `acc_daily -> rec_1` for 50000 cents, submit, then assert one `SUCCEEDED` transfer, balance 850000, one posted outgoing transaction, one journal entry with exactly two lines summing to zero, and status lookup returns the same bank reference.

- [ ] **Step 2: Write failing validation tests**

Cover `transfer_04` zero amount, invalid currency, cross-user account/recipient, unverified `rec_5`, mismatched confirmation hash, expired quote, and unexpected request fields. Each must leave transfer/balance/transaction/journal state unchanged.

- [ ] **Step 3: Run Task 4 tests and confirm failures**

Run: `PYTHONPATH=services/mock-bank FUTURELEDGER_ENV=test FUTURELEDGER_ALLOW_RESET=1 FUTURELEDGER_INTERNAL_TOKEN=test-internal-token conda run --no-capture-output -n base python -m pytest services/mock-bank/tests/integration/test_transfer_success.py services/mock-bank/tests/contract/test_transfer_api.py -v`

Expected: FAIL because write methods/endpoints are absent.

- [ ] **Step 4: Implement quote creation**

Quotes expire after five minutes, charge zero fee, store the canonical hash, and never reserve funds. Replacement quotes with unchanged canonical parameters produce the same `params_hash`.

- [ ] **Step 5: Implement atomic submission**

Within one SQLAlchemy transaction: validate quote/hash, check existing idempotency key, lock the account and recipient, recheck funds and verification, create transfer/transaction/journal rows, update balance, and commit `SUCCEEDED`. The clearing line uses `clearing:external`.

- [ ] **Step 6: Add HTTP quote/submit/status routes**

Require `Idempotency-Key` on submit and return 201 for the first accepted result, 200 for a replay, and structured business errors.

- [ ] **Step 7: Run Task 4 tests and reconciliation**

Run the Task 4 pytest command, then `python -m mock_bank.reconcile --json` through Conda with the test database URL.

Expected: tests PASS and reconciliation reports valid.

- [ ] **Step 8: Commit Task 4**

```bash
git add services/mock-bank
git commit -m "feat: add balanced mock bank transfers"
```

### Task 5: Stable Failures, Concurrency, and Lost-Response Recovery

**Files:**
- Create: `services/mock-bank/mock_bank/faults.py`
- Modify: `services/mock-bank/mock_bank/repository.py`
- Modify: `services/mock-bank/mock_bank/service.py`
- Modify: `services/mock-bank/mock_bank/api.py`
- Create: `services/mock-bank/tests/integration/test_transfer_idempotency.py`
- Create: `services/mock-bank/tests/integration/test_transfer_concurrency.py`
- Create: `services/mock-bank/tests/contract/test_transfer_faults.py`

**Interfaces:**
- Consumes: Task 4 transfer service.
- Produces: stable `FAILED/INSUFFICIENT_FUNDS` facts, `FaultPoint` hooks available only in tests, and replay metadata indicating first result versus replay.

- [ ] **Step 1: Write failing idempotency and stable-failure tests**

Cover identical replay, same key/different hash conflict, replacement quote/same hash/same unbound key, and `transfer_05` insufficient funds remaining failed after a later deposit.

- [ ] **Step 2: Write failing concurrency tests**

Using independent database sessions and a barrier, assert simultaneous identical keys debit once, competing keys cannot overdraw, and every committed transfer has one journal/transaction.

- [ ] **Step 3: Write failing fault tests**

Assert `before_commit` rolls back every fact; `drop_response_after_commit` makes the first HTTP call disconnect/raise while replay/status lookup returns the single committed transfer; fault headers are rejected outside test mode.

- [ ] **Step 4: Run Task 5 tests and confirm failures**

Run the three Task 5 test files with the standard test environment.

Expected: FAIL before idempotency locking and hooks exist.

- [ ] **Step 5: Implement key reservation and row-lock ordering**

Always lock idempotency/transfer identity before account rows, and account before recipient, to keep concurrent paths deterministic. Persist insufficient-funds failures without journal or balance mutations.

- [ ] **Step 6: Implement test-only fault hooks**

Expose typed internal hooks rather than production code branches scattered through repositories. The API recognizes `X-Mock-Fault` only when `FUTURELEDGER_ENV=test`.

- [ ] **Step 7: Run Task 5 tests repeatedly**

Run the Task 5 suite five consecutive times plus reconciliation to detect flaky races.

Expected: all runs PASS with one debit per logical transfer.

- [ ] **Step 8: Commit Task 5**

```bash
git add services/mock-bank
git commit -m "feat: harden bank transfer recovery"
```

### Task 6: Idempotent Mandate Cancellation and Status

**Files:**
- Modify: `services/mock-bank/mock_bank/contracts.py`
- Modify: `services/mock-bank/mock_bank/repository.py`
- Modify: `services/mock-bank/mock_bank/service.py`
- Modify: `services/mock-bank/mock_bank/api.py`
- Create: `services/mock-bank/tests/integration/test_mandates.py`
- Create: `services/mock-bank/tests/contract/test_mandate_api.py`

**Interfaces:**
- Consumes: seeded mandates and `bank.mandate_actions`.
- Produces: `BankService.cancel_mandate(subject, mandate_id, idempotency_key, now)` and stable status/list endpoints.

- [ ] **Step 1: Write failing direct mandate-case tests**

Cover `mandate_02` user scoping, `mandate_03` video cancellation, `mandate_06` non-cancellable fitness remains active, `mandate_08` repeated key returns the same result, and `mandate_09` capabilities expose restore as unsupported with no restore route.

- [ ] **Step 2: Write failing ownership/idempotency/concurrency tests**

Cover cross-user mandate IDs, same key/different mandate conflict, two concurrent cancellation keys, and already-cancelled mandate stability. Verify no endpoint accepts an ACTIVE restore status.

- [ ] **Step 3: Run Task 6 tests and confirm failures**

Run the mandate integration and contract test files.

Expected: FAIL because cancel behavior is absent.

- [ ] **Step 4: Implement cancellation transaction**

Lock idempotency identity then mandate. Persist one action per key. An active cancellable mandate transitions once; a non-cancellable mandate returns `UNSUPPORTED`; an already cancelled mandate returns the bank fact without reopening it.

- [ ] **Step 5: Add cancel/status/list routes and run tests**

Run the Task 6 tests plus reconciliation.

Expected: PASS and reconciliation remains valid.

- [ ] **Step 6: Commit Task 6**

```bash
git add services/mock-bank
git commit -m "feat: add mandate cancellation facts"
```

### Task 7: HTTP Adapter, Recording Spy, and A-Side Acceptance Evidence

**Files:**
- Create: `services/mock-bank/mock_bank/adapter.py`
- Create: `services/mock-bank/mock_bank/acceptance.py`
- Create: `services/mock-bank/tests/contract/test_adapter.py`
- Create: `services/mock-bank/tests/acceptance/test_role_a_cases.py`
- Create: `services/mock-bank/tests/acceptance/test_role_a_shared_evidence.py`

**Interfaces:**
- Consumes: all `BankService` operations and `benchmark/acceptance_cases.json`.
- Produces: `BankAdapter` protocol, `HttpBankAdapter`, `RecordingBankAdapter`, and `run_role_a_acceptance(...) -> RoleAAcceptanceReport` with `PASS`, `A_SIDE_PASS`, or `FAIL` per case.

- [ ] **Step 1: Write failing adapter contract tests**

Run the same balance, quote, submit, status, transaction, and mandate scenarios against an in-process service adapter and `HttpBankAdapter`. Assert identical typed results and error codes.

- [ ] **Step 2: Write failing direct acceptance tests**

Map and execute `transfer_01/04/05/06` and `mandate_02/03/06/08/09`, capturing table counts, balance, journal sums, statuses, and request IDs as JSON evidence.

- [ ] **Step 3: Write failing shared-evidence tests**

Use `RecordingBankAdapter` snapshots to prove zero calls/mutations for `transfer_02/03/08/10` and `mandate_01/04/05/10`; one stable call for `transfer_07`; immutable success for `transfer_09`; and transaction evidence without a matching mandate for `mandate_07`.

- [ ] **Step 4: Run Task 7 tests and confirm failures**

Run all contract/acceptance files.

Expected: FAIL because adapters/reporting are absent.

- [ ] **Step 5: Implement adapters and acceptance report**

Do not edit gold expectations. The report records case ID, ownership, A status, evidence references, and remaining B/C prerequisite. Secrets and full service tokens are redacted.

- [ ] **Step 6: Run Task 7 tests and emit report**

Run: `python -m mock_bank.acceptance --json outputs/role-a-acceptance.json` through Conda against a reset test database.

Expected: direct cases `PASS`, shared cases `A_SIDE_PASS`, zero `FAIL`.

- [ ] **Step 7: Commit Task 7**

```bash
git add services/mock-bank
git commit -m "test: add role A acceptance evidence"
```

### Task 8: Documentation, Full Regression, and Handoff

**Files:**
- Create: `services/mock-bank/README.md`
- Modify: `README.md`
- Modify: `CONTRIBUTING.md`
- Modify: `docs/03-数据库与接口契约.md`
- Modify: `docs/05-六人分工与里程碑.md`
- Modify: `benchmark/VERIFICATION.md`

**Interfaces:**
- Consumes: completed service commands and evidence output.
- Produces: reproducible Conda/Docker instructions and B/C/F handoff contracts.

- [ ] **Step 1: Document exact setup and operations**

Document Conda environment creation/activation, PostgreSQL startup, migration, guarded reset, service start, health checks, reconciliation, acceptance evidence, and shutdown. State that the service is synthetic and that shared cases remain cross-team.

- [ ] **Step 2: Document consumer handoffs**

For B: idempotency, confirmation hash, status recovery, and scheduling boundary. For C: recipient/mandate reads and consent boundary. For F: reset, reconcile, JSON evidence, and expected statuses.

- [ ] **Step 3: Run the complete bank verification**

Run all `services/mock-bank/tests`, reconciliation, and the acceptance report against PostgreSQL 18.6.

Expected: all bank tests PASS, reconciliation valid, direct cases `PASS`, shared cases `A_SIDE_PASS`.

- [ ] **Step 4: Run repository regression checks**

```bash
conda run --no-capture-output -n base python scripts/generate_data.py
conda run --no-capture-output -n base python scripts/generate_scenarios.py
conda run --no-capture-output -n base python scripts/run_benchmark.py
conda run --no-capture-output -n base python -m unittest discover -s tests -v
node scripts/check_prototype.cjs
```

Expected: 210/210 offline cases, 26/26 existing tests, and prototype smoke PASS. Existing SQLite connection/deprecation warnings are reported separately unless fixed by their owning module.

- [ ] **Step 5: Verify staged files and commit**

Run `git status --short`, ensure no environment, database, model, upload, or generated output is staged, then commit documentation.

```bash
git add -A
git status --short
git commit -m "docs: document mock bank workflows"
```

- [ ] **Step 6: Request whole-branch review and resolve findings**

Use `superpowers:requesting-code-review`, fix verified issues through TDD, then repeat complete verification.

- [ ] **Step 7: Push the completed branch**

Run: `git push -u origin codex/bank-adapter`

Expected: branch is available to teammates; if authentication or permission fails, stop immediately and report the exact failing command.
