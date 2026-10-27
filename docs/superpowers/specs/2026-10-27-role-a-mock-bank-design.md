# Role A Mock Bank Design

## Intent

Build the bank-and-data subsystem owned by role A so roles B and C can call a deterministic Bank adapter instead of editing balances directly. The subsystem must make the bank database the unique source of truth for balances, transfer outcomes, transaction facts, recipients, and mandates. It must support the first manual ¥500 transfer and the complete role-A scope: read APIs, quotes, idempotent transfer submission and status verification, mandate listing/cancellation/status, deterministic seed/reset, reconciliation, and evidence for every acceptance case jointly owned by A.

The implementation is a synthetic local bank for the hackathon. It never connects to a real bank and must not accept real credentials or account data.

## Goals

- Expose the documented Bank adapter capabilities: `get_balance`, `list_transactions`, `resolve_recipient`, `quote_transfer`, `submit_transfer`, `get_transfer_status`, `list_mandates`, `cancel_mandate`, and `get_mandate_status`.
- Preserve user/account/recipient ownership at every API and database boundary.
- Store all money as integer cents and all timestamps as timezone-aware values.
- Make transfer submission atomic across transfer status, account balance, transaction fact, and balanced journal entry.
- Make retries safe with stable idempotency keys, including concurrent retries and a lost response after commit.
- Keep bank facts separate from app preferences, confirmation, authentication, scheduling, quotas, and model output.
- Provide deterministic development/test seed and reset commands using the repository's synthetic fixtures.
- Produce machine-readable reconciliation and role-A acceptance evidence.
- Run locally with Conda and PostgreSQL 18.6 in Docker Compose.

## Non-goals

- Implementing B's execution gate, authorization, quota, outbox, worker, scheduling, cancellation of unsubmitted operations, or recovery policy.
- Implementing C's intent routing, clarification, scope consent, plan generation, or assistant copy.
- Determining whether a protected mandate may be cancelled; `app.protected_mandates` remains an application concern.
- Detecting subscription candidates from transaction history; A supplies transaction evidence but does not assert that a recurring charge is a bank mandate.
- Implementing merchant-contract cancellation or mandate restoration.
- Connecting to a real bank, using real credentials, or claiming production-grade identity authentication.
- Replacing the existing SQLite Text2SQL demo. The demo remains a separate prototype consumer until C integrates the Bank adapter.

## Anti-goals

- No balance updates without a matching balanced journal entry.
- No inference from chat text inside the bank service.
- No use of floating-point values for money.
- No `X-User-ID`-only trust boundary; internal caller authentication and subject identity are separate inputs.
- No silent success for unsupported mandate operations or unknown transfer outcomes.
- No reset endpoint enabled in a production-like environment.
- No reporting shared A+B or A+C cases as fully passed when the collaborator-owned precondition has not run.

## Existing Constraints

- Python 3.10+; the development workflow uses Conda rather than `venv`.
- FastAPI, Pydantic, SQLAlchemy 2, Alembic, and PostgreSQL are the repository's backend baseline.
- PostgreSQL 18.6 runs in Docker Compose; developers do not need a host installation under `/Library/PostgreSQL`.
- CNY only for v1; `currency="CNY"` is mandatory.
- Business dates use `Asia/Shanghai`; persisted instants use `timestamptz`.
- API responses use `{data, error, request_id}` and structured error codes.
- The current `db/schema.sql` is a design baseline, not a migration history. Alembic becomes the executable schema authority while `db/schema.sql` remains a reviewed snapshot.
- The current synthetic fixtures remain deterministic with seed `20261015` and snapshot `2026-10-01T00:00:00+08:00`.

## Approaches Considered

### Selected: layered FastAPI service with PostgreSQL

Use thin HTTP routes over an application service, domain rules, and SQLAlchemy repositories. The same typed adapter protocol is consumed in-process by tests and over HTTP by B/C. This makes transaction boundaries, fault injection, and contract testing explicit while remaining one deployable service.

### Rejected: route-centric FastAPI implementation

Putting SQL and rules directly in route handlers would be quicker for the first transfer but would couple HTTP, persistence, idempotency, and banking rules. It would make concurrent retries, dropped responses, and B/C adapter tests harder to reason about.

### Rejected: event-sourced bank core

An event log plus projections would improve replayability, but the current DDL and team interfaces are table-oriented. Projection/replay infrastructure is unnecessary for the hackathon and would delay the verified bank closure.

## Ownership Boundary

Role A owns bank facts and their invariants. B owns whether and when a transfer call is allowed. C owns interpretation and consent for mandate reads/cancellation. The adapter therefore assumes that its internal caller has already completed app-level checks, but independently revalidates bank-level facts:

- the subject owns the account and recipient;
- the quote is current and matches the submit payload;
- the recipient is bank-verified;
- the amount is positive and the account has sufficient funds;
- the idempotency key is stable and not reused for different parameters;
- the mandate belongs to the subject, is active, and supports cancellation.

For collaborator-owned negative cases, A supplies a recording fake/spy adapter and database snapshots that prove no bank call or mutation occurred. The final end-to-end verdict stays `NOT_RUN` until B or C supplies its orchestration.

## Service Layout

```text
services/mock-bank/
  environment.yml              Conda environment for bank development
  requirements-bank.txt        Locked-compatible Python dependency ranges
  Dockerfile                   Mock Bank image only
  compose.bank.yml             PostgreSQL 18.6 + Mock Bank local stack
  alembic.ini
  alembic/
    env.py
    versions/                  Executable bank migrations
  mock_bank/
    __init__.py
    api.py                     FastAPI factory and error envelope
    auth.py                    Internal service-token and subject extraction
    config.py                  Environment settings and reset guard
    contracts.py               Pydantic request/response contracts
    domain.py                  Money, quote, transfer, mandate rules
    repository.py              SQLAlchemy persistence and row locking
    service.py                 Transaction orchestration
    adapter.py                 `BankAdapter` protocol + HTTP implementation
    seed.py                    Deterministic seed/reset CLI
    reconcile.py               Ledger/balance reconciliation CLI
    faults.py                  Test-only fault injection
  tests/
    unit/
    integration/
    contract/
    acceptance/
```

The root `db/schema.sql` is updated from Alembic's final schema snapshot. Global deployment remains F's responsibility; `compose.bank.yml` is a module-local reproducible stack and can later be included by F.

## Internal Authentication

Every bank endpoint requires:

- `Authorization: Bearer <internal service token>` authenticating the calling application service; and
- `X-Authenticated-User: <user_id>` identifying the already-authenticated subject.

The token comes from environment configuration and is never stored in the repository. Tests inject a known token. The service always scopes database queries by the subject and never accepts a request-body `user_id` as an authorization selector. This is deliberately an internal mock-service boundary, not end-user authentication.

## Bank Adapter Contract

The Python protocol and HTTP API expose matching operations:

| Adapter method | HTTP operation | Result |
|---|---|---|
| `get_balance(subject, account_id)` | `GET /bank/v1/accounts/{account_id}/balance` | balance, currency, `as_of` |
| `list_transactions(subject, query)` | `GET /bank/v1/transactions` | paginated subject-scoped bank facts |
| `resolve_recipient(subject, recipient_id)` | `GET /bank/v1/recipients/{recipient_id}` | verified bank recipient fact |
| `quote_transfer(subject, request)` | `POST /bank/v1/transfers/quotes` | quote ID, canonical parameters, fee, expiry |
| `submit_transfer(subject, quote_id, params_hash, key)` | `POST /bank/v1/transfers` | stable transfer ID and bank status |
| `get_transfer_status(subject, transfer_id)` | `GET /bank/v1/transfers/{transfer_id}` | authoritative status and bank reference |
| `list_mandates(subject, account_id?)` | `GET /bank/v1/mandates` | subject-scoped mandates |
| `cancel_mandate(subject, mandate_id, key)` | `POST /bank/v1/mandates/{mandate_id}/cancel` | stable cancellation result |
| `get_mandate_status(subject, mandate_id)` | `GET /bank/v1/mandates/{mandate_id}` | authoritative mandate status |

`GET /bank/v1/capabilities` declares `idempotent_transfers=true`, `transfer_status_query=true`, `mandate_status_query=true`, `scheduled_transfers=false`, and `mandate_restore=false`. Scheduling remains B's responsibility: B calls `submit_transfer` once the scheduled operation becomes due and all checks are repeated.

`list_transactions` accepts optional `account_id`, `start`, `end_exclusive`, `status`, and `kind` filters plus an opaque cursor and `limit` from 1 to 100. Results are ordered by `(posted_at DESC, id DESC)` and return `transaction_id`, `account_id`, `amount_cents`, `currency`, `direction`, `kind`, `status`, `category`, `merchant`, `posted_at`, and `refund_of`. The memo and internal database details are omitted. This gives C/D stable evidence IDs and recurring-charge inputs without claiming that a repeated merchant is an authorization.

The submit body contains `quote_id` and the `params_hash` displayed and confirmed by B. The canonical hash covers subject, account, recipient, currency, amount, and fee, but not quote ID or expiry. A replacement quote for the same canonical parameters therefore retains the same intended-transfer identity and may use the same not-yet-bound idempotency key; any parameter change requires a new confirmation hash and idempotency key.

## Error Contract

Errors use the shared envelope and include `code`, `recoverable`, and `next_action`. Bank v1 defines:

- `UNAUTHENTICATED`, `FORBIDDEN`, and `NOT_FOUND`;
- `INVALID_AMOUNT`, `INVALID_CURRENCY`, and `INVALID_IDEMPOTENCY_KEY`;
- `IDEMPOTENCY_CONFLICT` when a key is reused for different canonical parameters;
- `QUOTE_EXPIRED` and `QUOTE_MISMATCH`;
- `RECIPIENT_UNVERIFIED` and `INSUFFICIENT_FUNDS`;
- `UNSUPPORTED` for non-cancellable mandates, restore, and unsupported capabilities;
- `UPSTREAM_UNAVAILABLE` only for an explicit simulated outage.

A committed transfer whose HTTP response is deliberately dropped is not changed to `FAILED`. Retrying the same key or querying the transfer returns the committed `SUCCEEDED` fact.

Invalid requests, unverified recipients, and expired or mismatched quotes are rejected before an idempotency key is bound because no valid submission exists. Once a valid, unexpired quote reaches the funds check, the key is bound. Insufficient funds creates a stable `FAILED` transfer with `failure_code="INSUFFICIENT_FUNDS"`; adding funds later cannot make the old key succeed. A new authorized operation must use a new key.

## Data Model

### Existing tables retained

- `bank.accounts`, `bank.recipients`, `bank.transactions`, `bank.transfers`, `bank.journal_entries`, `bank.journal_lines`, and `bank.mandates` remain bank facts.
- Composite ownership foreign keys remain mandatory.

### Additions and changes

- `bank.transfer_quotes`: quote ID, subject, account, recipient, amount, fee, canonical request hash, expiry, and creation time. Quotes do not reserve funds.
- `bank.transfers`: add quote ID, canonical request hash, bank reference, failure code, and `updated_at`; retain unique `(user_id, idempotency_key)`.
- `bank.mandate_actions`: stable idempotency record for cancellation requests, with mandate ID, canonical request hash, result status, and timestamps.
- `bank.journal_lines`: add a deferred constraint trigger that rejects any journal entry whose signed lines do not sum to zero at commit.
- Database grants: the mock-bank runtime role may mutate `bank`; analytics/read roles receive only approved read access. Direct balance updates outside the repository transaction are not granted to app roles.

The synthetic clearing leg uses a stable ledger reference such as `clearing:external`. A successful external transfer produces one negative customer-account line and one positive clearing line with equal cents.

## Transfer Flow

1. `quote_transfer` validates ownership, positive integer cents, CNY, and verified recipient, then returns an expiring canonical quote. It does not reserve or debit funds.
2. `submit_transfer` validates the internal caller and idempotency key, loads the quote, compares the confirmed `params_hash`, and rejects expired/invalid quotes before binding the key.
3. It starts a transaction and checks `(subject, idempotency_key)`. An existing matching transfer, including a stable bank-level failure, is returned unchanged; a mismatched hash returns `IDEMPOTENCY_CONFLICT`.
4. It locks the source account with `SELECT ... FOR UPDATE`, rechecks ownership, recipient verification, quote expiry, and available balance.
5. If funds are insufficient, it records one stable `FAILED` transfer without balance, transaction, or journal changes. Otherwise it inserts the transfer fact, updates the account balance, appends a `POSTED` transfer transaction, creates one journal entry with two equal-and-opposite lines, and sets the transfer to `SUCCEEDED` in the same transaction.
6. After commit, the test-only fault hook may drop the HTTP response. The committed fact remains queryable and a retry returns the same transfer without another debit.

The mock completes synchronously, but the contract still exposes `PENDING`, `SUCCEEDED`, and `FAILED` so a future adapter can be asynchronous. Only an authoritative bank result may set a terminal status.

## Mandate Flow

- `list_mandates` and `get_mandate_status` return only the authenticated subject's bank mandates.
- `cancel_mandate` requires an idempotency key and locks the mandate row.
- An `ACTIVE` and cancellable mandate becomes `CANCELLED`, records `as_of`, and stores a stable `bank.mandate_actions` result.
- A repeated matching request returns the existing cancellation result without another transition.
- A non-cancellable mandate returns `UNSUPPORTED` and remains `ACTIVE`.
- An already cancelled mandate returns the stable cancelled fact.
- Restore is absent from the adapter and advertised as unsupported; no endpoint may set a cancelled mandate back to active.
- Protected-mandate and ambiguous-user-language cases are blocked before the adapter by C/B. A's spy adapter proves no call occurred.

## Seed, Reset, and Reconciliation

`python -m mock_bank.seed reset` loads `data/users.json`, `data/accounts.json`, `data/recipients.json`, `data/transactions.csv`, and `data/mandates.json` into PostgreSQL in a single deterministic reset workflow. Reset is permitted only when `FUTURELEDGER_ENV` is `test` or `development` and `FUTURELEDGER_ALLOW_RESET=1`; otherwise it exits without changing data.

Reset recreates bank facts and zeroes quote/action history. It never reads `.env` automatically and never accepts real data. Tests reset an isolated database/schema per case rather than sharing mutated state.

`python -m mock_bank.reconcile` returns non-zero unless all of the following hold:

- each journal entry sums to zero;
- every successful transfer has exactly one journal entry and one outgoing transfer transaction;
- account balances equal the deterministic opening balance plus all posted bank movements in the seeded coverage window;
- no transfer idempotency key maps to multiple payload hashes;
- mandate states and action history agree.

The command also supports JSON output for F's evidence collector.

## Fault Injection and Concurrency

Fault injection is enabled only in tests. Supported hooks are `before_commit`, `drop_response_after_commit`, and `temporary_unavailable`. Production-like configuration refuses fault headers.

Integration tests use real PostgreSQL transactions and concurrent clients to prove:

- simultaneous identical idempotency keys create one debit and one ledger entry;
- the same key with different parameters is rejected;
- competing transfers cannot overdraw the locked account;
- dropped responses are recovered by retry/status lookup without resubmission;
- duplicate mandate cancellation is stable.

## Verification Strategy

Verification precedes implementation for every task:

1. Write a failing unit, integration, contract, or acceptance test.
2. Run the narrow test and confirm the intended failure.
3. Implement the smallest behavior that satisfies it.
4. Run the narrow test, then the full bank suite.
5. Run reconciliation and the repository's existing 26 tests, 210-case benchmark, and prototype smoke check.
6. Commit a self-contained change.

Unit tests cover canonical hashing, money validation, errors, and state rules. Integration tests run against PostgreSQL 18.6. HTTP contract tests assert the envelope, authentication, scoping, and adapter compatibility. Acceptance tests emit evidence rather than only checking chat text.

## Acceptance-Case Mapping

### Direct A behavior

- `transfer_01`: ¥500 succeeds, balance becomes 850000 cents, and exactly one balanced journal entry exists.
- `transfer_04`: zero amount returns `INVALID_AMOUNT` without writes.
- `transfer_05`: insufficient funds returns the bank error without a debit.
- `transfer_06`: an unverified recipient cannot be quoted/submitted and no bank reference is invented.
- `mandate_02`: listing is scoped to `test_user`.
- `mandate_03`: cancellable video mandate becomes `CANCELLED`.
- `mandate_06`: non-cancellable fitness mandate returns `UNSUPPORTED` and remains active.
- `mandate_08`: repeated cancellation returns the stable existing result.
- `mandate_09`: restore is unsupported and cannot create a fake active state.

### Shared cases with A-side evidence

- `transfer_02`, `transfer_03`, and `transfer_10`: B/C must not call write methods; the recording adapter and before/after reconciliation prove zero bank mutations.
- `transfer_07`: B owns scheduling; when its due worker calls A, stable idempotency proves exactly one submission.
- `transfer_08`: B cancels before submission; A proves no transfer exists and no debit occurred.
- `transfer_09`: B rejects undo semantics; A's status remains `SUCCEEDED` and no reversal occurs without a new transfer.
- `mandate_01`: C owns read-scope confirmation; the recording adapter proves `list_mandates` was not called beforehand.
- `mandate_04` and `mandate_05`: C/B enforce protected preferences; A proves the cloud mandate remains active and no cancellation call occurred.
- `mandate_07`: C/D detect candidates; A supplies transaction evidence and a bank lookup that returns no mandate, preventing false authorization claims.
- `mandate_10`: C cannot infer service usage; A exposes no usage telemetry and records no cancellation call.

The A suite labels direct cases `PASS` when bank evidence succeeds and shared cases `A_SIDE_PASS` until the collaborator-owned behavior runs. It never rewrites `benchmark/acceptance_cases.json` gold expectations.

## Security and Operational Behavior

- Logs include `request_id`, operation type, subject pseudonymous ID, transfer/mandate reference, and outcome; never the service token or raw credentials.
- Request bodies are size-limited by the application server and strictly validated with `extra="forbid"`.
- IDs are opaque, generated server-side, and responses never leak another user's existence.
- The service token is compared safely and rotated through configuration, not source changes.
- Health has separate liveness and database-readiness endpoints.
- Shutdown drains in-flight requests and closes the SQLAlchemy engine.

## Documentation and Handoff

- README instructions use Conda and `compose.bank.yml`, not `.venv`.
- `services/mock-bank/README.md` documents environment variables, migrations, seed/reset, reconciliation, API examples, and the explicit synthetic-only boundary.
- B receives the adapter protocol, error map, idempotency requirements, and dropped-response recovery example.
- C receives recipient/mandate read contracts and confirmation-boundary examples.
- F receives reset/reconcile commands, JSON evidence, and the case mapping above.

## Success Criteria

- The first manual ¥500 transfer passes with bank-table evidence.
- All direct A cases pass against PostgreSQL 18.6.
- Every shared A-owned case has executable A-side evidence and an honest cross-team status.
- Concurrency and lost-response tests prove no duplicate debit.
- Seed/reset is deterministic and production-guarded.
- Reconciliation passes after success, duplicate retry, insufficient funds, and mandate cancellation scenarios.
- The existing demo, reference tests, benchmark, and prototype smoke checks remain green.
