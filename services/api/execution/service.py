"""Deterministic, persistence-backed execution gate.

The model may propose an operation, but this module alone decides whether a
write is authorized and when a bank adapter may be called.  Amounts are integer
cents throughout.  The SQLite store is intentionally small so the same code is
usable in tests and in the local demo; PostgreSQL can implement the same tables
and locking contract for deployment.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from functools import wraps
from typing import Any, Callable, Protocol
from zoneinfo import ZoneInfo


THRESHOLD_CENTS = 100_000
CONFIRM_TTL = timedelta(minutes=5)


class ExecutionError(RuntimeError):
    def __init__(self, code: str, message: str, *, status: str | None = None):
        super().__init__(message)
        self.code, self.status = code, status


class UnknownBankResult(RuntimeError):
    """The bank may have committed, but the response was not received."""


class BankAdapter(Protocol):
    def submit_transfer(self, *, operation_id: str, user_id: str, account_id: str,
                        recipient_user_id: str, amount_cents: int,
                        idempotency_key: str) -> str: ...

    def get_transfer_status(self, *, operation_id: str, idempotency_key: str) -> str: ...


class InMemoryBank:
    """Thread-safe mock bank used by tests and a local execution demo."""

    def __init__(self, balances: dict[tuple[str, str], int]):
        self.balances = dict(balances)
        self.transfers: dict[str, dict[str, Any]] = {}
        self.lock = threading.RLock()
        self.drop_response_once = False

    def submit_transfer(self, *, operation_id: str, user_id: str, account_id: str,
                        recipient_user_id: str, amount_cents: int,
                        idempotency_key: str) -> str:
        with self.lock:
            existing = self.transfers.get(idempotency_key)
            if existing:
                if self.drop_response_once:
                    self.drop_response_once = False
                    raise UnknownBankResult("response lost after bank commit")
                return existing["bank_ref"]
            source = (user_id, account_id)
            destination_candidates = [key for key in self.balances if key[0] == recipient_user_id]
            if not destination_candidates:
                raise ExecutionError("RECIPIENT_NOT_FOUND", "收款人没有可用模拟账户。", status="FAILED")
            destination = destination_candidates[0]
            if self.balances.get(source, 0) < amount_cents:
                raise ExecutionError("INSUFFICIENT_FUNDS", "余额不足。", status="FAILED")
            self.balances[source] -= amount_cents
            self.balances[destination] += amount_cents
            bank_ref = "bank_" + secrets.token_urlsafe(10)
            self.transfers[idempotency_key] = {"bank_ref": bank_ref, "status": "SUCCEEDED",
                                               "operation_id": operation_id}
            if self.drop_response_once:
                self.drop_response_once = False
                raise UnknownBankResult("response lost after bank commit")
            return bank_ref

    def get_transfer_status(self, *, operation_id: str, idempotency_key: str) -> str:
        with self.lock:
            return self.transfers.get(idempotency_key, {}).get("status", "NOT_FOUND")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def _hash_params(params: dict[str, Any]) -> str:
    body = json.dumps(params, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(body.encode()).hexdigest()


def serialized(method):
    """One connection cannot host concurrent transactions from API threads."""
    @wraps(method)
    def call(self, *args, **kwargs):
        with self.lock:
            try:
                return method(self, *args, **kwargs)
            except BaseException:
                self.db.rollback()
                raise
    return call


SCHEMA = """
CREATE TABLE IF NOT EXISTS operations(
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL, account_id TEXT NOT NULL,
 recipient_user_id TEXT NOT NULL, amount_cents INTEGER NOT NULL CHECK(amount_cents>0),
 plan_id TEXT NOT NULL, plan_version INTEGER NOT NULL, params_json TEXT NOT NULL,
 params_hash TEXT NOT NULL, idempotency_key TEXT NOT NULL, risk_level TEXT NOT NULL,
 status TEXT NOT NULL, confirm_expires_at TEXT NOT NULL, bank_ref TEXT,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 UNIQUE(user_id,idempotency_key)
);
CREATE TABLE IF NOT EXISTS authorizations(
 id TEXT PRIMARY KEY, operation_id TEXT NOT NULL, params_hash TEXT NOT NULL,
 plan_version INTEGER NOT NULL, confirmed_at TEXT NOT NULL, expires_at TEXT NOT NULL,
 auth_ref TEXT, used_at TEXT
);
CREATE TABLE IF NOT EXISTS quota_reservations(
 operation_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, business_date TEXT NOT NULL,
 amount_cents INTEGER NOT NULL, state TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS outbox(
 id INTEGER PRIMARY KEY AUTOINCREMENT, operation_id TEXT NOT NULL UNIQUE,
 event_type TEXT NOT NULL, payload_json TEXT NOT NULL, lease_owner TEXT,
 lease_until TEXT, attempts INTEGER NOT NULL DEFAULT 0, dispatched_at TEXT
);
CREATE TABLE IF NOT EXISTS audit_events(
 id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL, operation_id TEXT,
 event_type TEXT NOT NULL, redacted_payload TEXT NOT NULL, created_at TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class Operation:
    id: str
    user_id: str
    account_id: str
    recipient_user_id: str
    amount_cents: int
    plan_id: str
    plan_version: int
    params_hash: str
    idempotency_key: str
    risk_level: str
    status: str
    confirm_expires_at: str
    bank_ref: str | None = None


class ExecutionService:
    def __init__(self, connection: sqlite3.Connection, bank: BankAdapter,
                 *, password_checker: Callable[[str, str], bool] | None = None,
                 clock: Callable[[], datetime] = _utc_now):
        self.db = connection
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript(SCHEMA)
        self.bank = bank
        self.password_checker = password_checker or (lambda password, user_id: False)
        self.clock = clock
        self.lock = threading.RLock()
        if hasattr(bank, 'attach_store'):
            bank.attach_store(self.db)

    @staticmethod
    def connect(path: str = ":memory:") -> sqlite3.Connection:
        """Open a connection suitable for FastAPI's worker threads."""
        return sqlite3.connect(path, check_same_thread=False)

    def _audit(self, user_id: str, operation_id: str | None, event_type: str, payload: dict[str, Any]):
        safe = {k: v for k, v in payload.items() if k not in {"password", "otp", "auth_ref"}}
        self.db.execute("INSERT INTO audit_events(user_id,operation_id,event_type,redacted_payload,created_at) VALUES(?,?,?,?,?)",
                        (user_id, operation_id, event_type, json.dumps(safe, sort_keys=True), _iso(self.clock())))

    def _business_date(self) -> str:
        return self.clock().astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat()

    def _check_execution_date(self, execution_date: str | None):
        if execution_date is None:
            return
        try:
            requested = date.fromisoformat(execution_date)
        except (ValueError, TypeError) as exc:
            raise ExecutionError('INVALID_DATE', '执行日期必须是 YYYY-MM-DD。') from exc
        today = date.fromisoformat(self._business_date())
        if requested > today:
            raise ExecutionError('UNSUPPORTED_SCHEDULE', '预约转账尚未实现，请在执行当天重新确认。')
        if requested < today:
            raise ExecutionError('INVALID_DATE', '执行日期已过期，请重新创建操作。')

    @serialized
    def create_operation(self, *, user_id: str, account_id: str, recipient_user_id: str,
                         amount_cents: int, plan_id: str = "transfer", plan_version: int = 1,
                         execution_date: str | None = None,
                         idempotency_key: str | None = None) -> dict[str, Any]:
        if amount_cents <= 0:
            raise ExecutionError("INVALID_AMOUNT", "金额必须为正数。")
        idem = idempotency_key or secrets.token_urlsafe(18)
        existing = self.db.execute("SELECT * FROM operations WHERE user_id=? AND idempotency_key=?", (user_id, idem)).fetchone()
        if existing:
            return self._view(existing)
        self._check_execution_date(execution_date)
        now = self.clock()
        business_date = self._business_date()
        reserved = self.db.execute("SELECT COALESCE(SUM(amount_cents),0) FROM quota_reservations WHERE user_id=? AND business_date=? AND state IN ('RESERVED','COMMITTED')", (user_id, business_date)).fetchone()[0]
        risk = "RED" if reserved + amount_cents > THRESHOLD_CENTS else "YELLOW"
        params = {"account_id": account_id, "recipient_user_id": recipient_user_id, "amount_cents": amount_cents}
        if execution_date is not None:
            params["execution_date"] = execution_date
        op_id = "op_" + secrets.token_urlsafe(12)
        expires = now + CONFIRM_TTL
        self.db.execute("INSERT INTO operations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (op_id, user_id, account_id, recipient_user_id, amount_cents, plan_id, plan_version,
                         json.dumps(params, sort_keys=True), _hash_params(params), idem, risk, "NEEDS_CONFIRM",
                         _iso(expires), None, _iso(now), _iso(now)))
        self._audit(user_id, op_id, "OPERATION_CREATED", {"risk_level": risk, "amount_cents": amount_cents, "plan_version": plan_version})
        self.db.commit()
        return self._view(self.db.execute("SELECT * FROM operations WHERE id=?", (op_id,)).fetchone())

    @serialized
    def confirm(self, operation_id: str, *, user_id: str, plan_version: int, params_hash: str) -> dict[str, Any]:
        row = self._owned(operation_id, user_id)
        if row["status"] not in {"NEEDS_CONFIRM", "NEEDS_AUTH"}:
            raise ExecutionError("INVALID_STATE", "操作当前不接受确认。", status=row["status"])
        if row["plan_version"] != plan_version or not hmac.compare_digest(row["params_hash"], params_hash):
            raise ExecutionError("PLAN_STALE", "操作参数或计划版本已变化，请重新规划。", status=row["status"])
        if _parse(row["confirm_expires_at"]) <= self.clock():
            self._set_status(operation_id, "EXPIRED")
            self.db.commit()
            raise ExecutionError("AUTH_EXPIRED", "确认已过期，请重新创建操作。", status="EXPIRED")
        now = self.clock()
        auth_id = "auth_" + secrets.token_urlsafe(12)
        self.db.execute("INSERT INTO authorizations VALUES(?,?,?,?,?,?,?,?)", (auth_id, operation_id, params_hash, plan_version, _iso(now), row["confirm_expires_at"], None, None))
        status = "NEEDS_AUTH" if row["risk_level"] == "RED" else "READY"
        self._set_status(operation_id, status)
        self._audit(user_id, operation_id, "CONFIRMED", {"risk_level": row["risk_level"], "plan_version": plan_version})
        self.db.commit()
        return self.status(operation_id, user_id=user_id)

    @serialized
    def verify(self, operation_id: str, *, user_id: str, password: str) -> dict[str, Any]:
        row = self._owned(operation_id, user_id)
        if row["status"] != "NEEDS_AUTH":
            raise ExecutionError("AUTH_NOT_REQUIRED", "当前操作不需要强验证。", status=row["status"])
        if not self.password_checker(password, user_id):
            self._audit(user_id, operation_id, "AUTH_FAILED", {})
            self.db.commit()
            raise ExecutionError("AUTH_REQUIRED", "强验证失败。", status=row["status"])
        auth = self.db.execute("SELECT * FROM authorizations WHERE operation_id=? ORDER BY rowid DESC LIMIT 1", (operation_id,)).fetchone()
        if auth is None or _parse(auth["expires_at"]) <= self.clock():
            raise ExecutionError("AUTH_EXPIRED", "强验证已过期，请重新确认。", status="EXPIRED")
        ref = "authref_" + secrets.token_urlsafe(12)
        self.db.execute("UPDATE authorizations SET auth_ref=? WHERE id=?", (ref, auth["id"]))
        self._set_status(operation_id, "READY")
        self._audit(user_id, operation_id, "AUTH_VERIFIED", {})
        self.db.commit()
        return self.status(operation_id, user_id=user_id)

    @serialized
    def execute(self, operation_id: str, *, user_id: str, idempotency_key: str) -> dict[str, Any]:
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            row = self._owned(operation_id, user_id)
            if row["idempotency_key"] != idempotency_key:
                self.db.rollback()
                raise ExecutionError("PLAN_STALE", "幂等键与操作不匹配。", status=row["status"])
            if row["status"] in {"SUCCEEDED", "FAILED", "PENDING_UNKNOWN", "ENQUEUED", "SUBMITTING"}:
                self.db.commit()
                return self._view(row)
            if row["status"] != "READY":
                self.db.rollback()
                raise ExecutionError("AUTH_REQUIRED", "操作尚未完成确认或强验证。", status=row["status"])
            now = self.clock()
            auth = self.db.execute("SELECT * FROM authorizations WHERE operation_id=? ORDER BY rowid DESC LIMIT 1", (operation_id,)).fetchone()
            if (auth is None or _parse(auth['expires_at']) <= now or auth['used_at'] is not None
                    or auth['params_hash'] != row['params_hash'] or auth['plan_version'] != row['plan_version']):
                self._set_status(operation_id, 'EXPIRED')
                self.db.commit()
                raise ExecutionError('AUTH_EXPIRED', '确认或授权已过期，请重新创建操作。', status='EXPIRED')
            if row['risk_level'] == 'RED' and not auth['auth_ref']:
                raise ExecutionError('AUTH_REQUIRED', '需要独立强验证。', status='NEEDS_AUTH')
            self._check_execution_date(json.loads(row['params_json']).get('execution_date'))
            business_date = self._business_date()
            total = self.db.execute("SELECT COALESCE(SUM(amount_cents),0) FROM quota_reservations WHERE user_id=? AND business_date=? AND state IN ('RESERVED','COMMITTED')", (user_id, business_date)).fetchone()[0]
            if total + row["amount_cents"] > THRESHOLD_CENTS and row["risk_level"] != "RED":
                self.db.execute("UPDATE operations SET risk_level='RED' WHERE id=?", (operation_id,))
                self._set_status(operation_id, "NEEDS_AUTH")
                self._audit(user_id, operation_id, "RISK_ESCALATED", {"total_cents": total + row["amount_cents"]})
                self.db.commit()
                raise ExecutionError("AUTH_REQUIRED", "并发累计额度超过日限额，需要强验证。", status="NEEDS_AUTH")
            self.db.execute("INSERT INTO quota_reservations VALUES(?,?,?,?,?)", (operation_id, user_id, business_date, row["amount_cents"], "RESERVED"))
            self.db.execute("INSERT INTO outbox(operation_id,event_type,payload_json) VALUES(?,?,?)", (operation_id, "TRANSFER_SUBMIT", json.dumps({"operation_id": operation_id, "idempotency_key": idempotency_key})))
            self.db.execute('UPDATE authorizations SET used_at=? WHERE id=?', (_iso(now), auth['id']))
            self._set_status(operation_id, "ENQUEUED")
            self._audit(user_id, operation_id, "EXECUTION_ENQUEUED", {"amount_cents": row["amount_cents"]})
            self.db.commit()
            return self.status(operation_id, user_id=user_id)

    @serialized
    def claim_outbox(self, worker_id: str, *, lease_seconds: int = 30) -> sqlite3.Row | None:
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            now = self.clock()
            row = self.db.execute("SELECT o.* FROM outbox o JOIN operations p ON p.id=o.operation_id WHERE o.dispatched_at IS NULL AND p.status IN ('ENQUEUED','SUBMITTING') AND (o.lease_until IS NULL OR o.lease_until<?) ORDER BY o.id LIMIT 1", (_iso(now),)).fetchone()
            if not row:
                self.db.commit()
                return None
            self.db.execute("UPDATE outbox SET lease_owner=?,lease_until=?,attempts=attempts+1 WHERE id=?", (worker_id, _iso(now + timedelta(seconds=lease_seconds)), row["id"]))
            self._set_status(row['operation_id'], 'SUBMITTING')
            self.db.commit()
            return self.db.execute("SELECT * FROM outbox WHERE id=?", (row["id"],)).fetchone()

    @serialized
    def process_one(self, worker_id: str = "worker") -> dict[str, Any] | None:
        item = self.claim_outbox(worker_id)
        if item is None:
            return None
        payload = json.loads(item["payload_json"])
        row = self.db.execute("SELECT * FROM operations WHERE id=?", (item["operation_id"],)).fetchone()
        try:
            ref = self.bank.submit_transfer(operation_id=row["id"], user_id=row["user_id"], account_id=row["account_id"], recipient_user_id=row["recipient_user_id"], amount_cents=row["amount_cents"], idempotency_key=payload["idempotency_key"])
        except (UnknownBankResult, ExecutionError) as exc:
            if isinstance(exc, ExecutionError) and exc.status == 'FAILED':
                self._set_status(row['id'], 'FAILED')
                self.db.execute("UPDATE quota_reservations SET state='RELEASED' WHERE operation_id=?", (row['id'],))
                self.db.execute('UPDATE outbox SET dispatched_at=? WHERE id=?', (_iso(self.clock()), item['id']))
                self._audit(row['user_id'], row['id'], 'BANK_FAILED', {'code': exc.code})
                self.db.commit()
                return self.status(row['id'], user_id=row['user_id'])
            self._set_status(row["id"], "PENDING_UNKNOWN")
            self.db.execute("UPDATE outbox SET lease_owner=NULL,lease_until=NULL WHERE id=?", (item["id"],))
            self._audit(row["user_id"], row["id"], "BANK_RESULT_UNKNOWN", {})
            self.db.commit()
            return self.status(row["id"], user_id=row["user_id"])
        self._set_status(row["id"], "SUCCEEDED", bank_ref=ref)
        self.db.execute("UPDATE quota_reservations SET state='COMMITTED' WHERE operation_id=?", (row["id"],))
        self.db.execute("UPDATE outbox SET dispatched_at=? WHERE id=?", (_iso(self.clock()), item["id"]))
        self._audit(row["user_id"], row["id"], "BANK_SUCCEEDED", {"bank_ref": ref})
        self.db.commit()
        return self.status(row["id"], user_id=row["user_id"])

    @serialized
    def recover_unknown(self, operation_id: str, *, user_id: str) -> dict[str, Any]:
        row = self._owned(operation_id, user_id)
        if row["status"] not in {'PENDING_UNKNOWN', 'SUBMITTING'}:
            return self._view(row)
        result = self.bank.get_transfer_status(operation_id=operation_id, idempotency_key=row["idempotency_key"])
        if result == "SUCCEEDED":
            reference = (self.bank.get_bank_reference(operation_id=operation_id, idempotency_key=row['idempotency_key'])
                         if hasattr(self.bank, 'get_bank_reference') else
                         self.bank.transfers[row['idempotency_key']]['bank_ref'] if hasattr(self.bank, 'transfers') else None)
            self._set_status(operation_id, "SUCCEEDED", bank_ref=reference)
            self.db.execute("UPDATE quota_reservations SET state='COMMITTED' WHERE operation_id=?", (operation_id,))
            self._audit(user_id, operation_id, "BANK_CONFIRMED", {})
            self.db.execute('UPDATE outbox SET dispatched_at=? WHERE operation_id=?', (_iso(self.clock()), operation_id))
            self.db.commit()
        elif result == "FAILED":
            self._set_status(operation_id, "FAILED")
            self.db.execute("UPDATE quota_reservations SET state='RELEASED' WHERE operation_id=?", (operation_id,))
            self.db.execute('UPDATE outbox SET dispatched_at=? WHERE operation_id=?', (_iso(self.clock()), operation_id))
            self.db.commit()
        return self.status(operation_id, user_id=user_id)

    @serialized
    def status(self, operation_id: str, *, user_id: str) -> dict[str, Any]:
        return self._view(self._owned(operation_id, user_id))

    @serialized
    def lookup_by_key(self, *, user_id: str, idempotency_key: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT * FROM operations WHERE user_id=? AND idempotency_key=?", (user_id, idempotency_key)).fetchone()
        return self._view(row) if row else None

    @serialized
    def invalidate(self, operation_id: str, *, user_id: str) -> dict[str, Any]:
        row = self._owned(operation_id, user_id)
        if row["status"] in {"SUCCEEDED", "SUBMITTING", "PENDING_UNKNOWN", "ENQUEUED"}:
            raise ExecutionError("PENDING_UNKNOWN", "已提交操作必须先查证，不能静默失效。", status=row["status"])
        self._set_status(operation_id, "EXPIRED")
        self._audit(user_id, operation_id, "OPERATION_INVALIDATED", {})
        self.db.commit()
        return self.status(operation_id, user_id=user_id)

    @serialized
    def cancel_unsubmitted(self, operation_id: str, *, user_id: str) -> str:
        self.db.execute('BEGIN IMMEDIATE')
        row = self._owned(operation_id, user_id)
        if row["status"] in {"SUBMITTING", "PENDING_UNKNOWN", "SUCCEEDED"}:
            self.db.commit()
            return "PENDING_UNKNOWN" if row["status"] != "SUCCEEDED" else "ALREADY_SUBMITTED"
        self.db.execute('UPDATE outbox SET dispatched_at=? WHERE operation_id=?', (_iso(self.clock()), operation_id))
        self.db.execute("UPDATE quota_reservations SET state='RELEASED' WHERE operation_id=?", (operation_id,))
        self._set_status(operation_id, "EXPIRED")
        self._audit(user_id, operation_id, "OPERATION_CANCELLED", {})
        self.db.commit()
        return "CANCELLED"

    def _owned(self, operation_id: str, user_id: str) -> sqlite3.Row:
        row = self.db.execute("SELECT * FROM operations WHERE id=? AND user_id=?", (operation_id, user_id)).fetchone()
        if row is None:
            raise ExecutionError("FORBIDDEN", "找不到属于当前用户的操作。")
        return row

    def _set_status(self, operation_id: str, status: str, *, bank_ref: str | None = None):
        self.db.execute("UPDATE operations SET status=?,bank_ref=COALESCE(?,bank_ref),updated_at=? WHERE id=?", (status, bank_ref, _iso(self.clock()), operation_id))

    @staticmethod
    def _view(row: sqlite3.Row) -> dict[str, Any]:
        params = json.loads(row["params_json"])
        return {"operation_id": row["id"], "plan_id": row["plan_id"], "status": row["status"],
                "risk_level": row["risk_level"], "amount_cents": row["amount_cents"],
                "account_id": row["account_id"], "recipient_user_id": row["recipient_user_id"],
                "execution_date": params.get("execution_date"), "plan_version": row["plan_version"],
                "params_hash": row["params_hash"], "idempotency_key": row["idempotency_key"],
                "confirm_expires_at": row["confirm_expires_at"], "bank_ref": row["bank_ref"]}
