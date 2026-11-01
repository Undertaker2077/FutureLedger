# FutureLedger Mock Bank (Role A)

This service is a synthetic bank simulator. It never connects to a real bank and must not receive real credentials or financial data. PostgreSQL is the source of truth for balances, recipients, transactions, transfers, balanced journal entries, and mandates.

## Local setup with Conda

The supported local path uses Conda rather than `venv`:

```bash
cd services/mock-bank
conda env create -f environment.yml
conda activate futureledger-bank
cd ../..
docker compose -f services/mock-bank/compose.bank.yml up -d postgres
```

The compose service exposes its isolated PostgreSQL 18.6 database on `localhost:55432`; no installation under `/Library/PostgreSQL` is required. Wait until it is healthy with `docker compose -f services/mock-bank/compose.bank.yml ps`.

Set local-only configuration in the same shell. Never commit the token:

```bash
export PYTHONPATH=services/mock-bank
export BANK_DATABASE_URL='postgresql+psycopg://futureledger:futureledger@localhost:55432/futureledger_bank' # migration/reset owner only
export FUTURELEDGER_INTERNAL_TOKEN='replace-with-a-local-secret'
export FUTURELEDGER_ENV=development
export FUTURELEDGER_ALLOW_RESET=1
```

`reset` applies Alembic migrations and transactionally reloads the repository fixtures. It is refused outside `test`/`development` and also requires the explicit reset flag:

```bash
python -m mock_bank.seed reset
export BANK_DATABASE_URL='postgresql+psycopg://futureledger_runtime:futureledger-runtime@localhost:55432/futureledger_bank'
python -m mock_bank.reconcile --json
python -m uvicorn mock_bank.api:app --host 127.0.0.1 --port 8001
```

The owner connection is used only for migrations and destructive fixture reset. The API and normal reconciliation run as `futureledger_runtime`, which can read and write the `bank` schema but cannot modify `app` data. The shown credentials are synthetic local defaults; do not reuse them outside this disposable Compose stack. `FUTURELEDGER_INTERNAL_TOKEN` has no built-in default and startup fails when it is absent.

Health endpoints are public; bank endpoints require both internal service and subject headers:

```bash
curl http://127.0.0.1:8001/health/live
curl http://127.0.0.1:8001/health/ready
curl -H "Authorization: Bearer $FUTURELEDGER_INTERNAL_TOKEN" \
  -H 'X-Authenticated-User: test_user' \
  http://127.0.0.1:8001/bank/v1/accounts/acc_daily/balance
```

Stop Uvicorn with `Ctrl+C`, then stop PostgreSQL without deleting its volume:

```bash
docker compose -f services/mock-bank/compose.bank.yml down
```

## Verification and evidence

```bash
PYTHONPATH=services/mock-bank FUTURELEDGER_ENV=test FUTURELEDGER_ALLOW_RESET=1 \
FUTURELEDGER_INTERNAL_TOKEN=test-internal-token \
conda run --no-capture-output -n futureledger-bank \
python -m pytest services/mock-bank/tests -q

PYTHONPATH=services/mock-bank BANK_DATABASE_URL='postgresql+psycopg://futureledger:futureledger@localhost:55432/futureledger_bank' \
FUTURELEDGER_ENV=test conda run --no-capture-output -n futureledger-bank \
python -m mock_bank.reconcile --json

PYTHONPATH=services/mock-bank BANK_DATABASE_URL='postgresql+psycopg://futureledger:futureledger@localhost:55432/futureledger_bank' \
FUTURELEDGER_ENV=test FUTURELEDGER_ALLOW_RESET=1 FUTURELEDGER_INTERNAL_TOKEN=test-internal-token \
conda run --no-capture-output -n futureledger-bank \
python -m mock_bank.acceptance --json outputs/role-a-acceptance.json
```

The report executes all 20 A-owned transfer/mandate cases from the immutable catalog. A-direct behavior is `PASS`; shared cases are `A_SIDE_PASS` until B or C supplies the orchestration/consent evidence. Reports under `outputs/` are local artifacts and are not committed.

## Consumer handoff

### B — execution and safety

- Send the confirmed `params_hash` and a stable 8–128 visible-ASCII `Idempotency-Key` to `submit_transfer`.
- A key may replay only the same canonical subject/account/recipient/currency/amount/fee identity. Changed parameters return `IDEMPOTENCY_CONFLICT`.
- On a dropped or unknown response, replay the same key or call `get_transfer_status`; never infer failure and submit a new debit.
- A exposes `scheduled_transfers=false`. B owns scheduling, due-time policy checks, and exactly one due-worker call.
- `FAILED/INSUFFICIENT_FUNDS` is a stable bank fact bound to the original key.

### C — agent and application API

- Use `resolve_recipient` for authoritative identity/verification and never invent a `bank_ref`.
- Use mandate reads only after C obtains the required read scope/consent.
- `cancel_mandate` requires a stable key. Non-cancellable mandates return `UNSUPPORTED` and remain `ACTIVE`.
- Mandate restore is unsupported; recurring transaction evidence must not be presented as a bank mandate.

### F — verification and delivery

- Reset only disposable test/development databases with both guards enabled.
- Run reconciliation after transfer, fault, concurrency, and mandate scenarios.
- Consume `outputs/role-a-acceptance.json`; expected A statuses are `PASS` or `A_SIDE_PASS`, never `FAIL`.
- Test-only `X-Mock-Fault` values are `before_commit`, `drop_response_after_commit`, and `temporary_unavailable`; production mode rejects the header.
