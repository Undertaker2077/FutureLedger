import sqlite3
import threading
import unittest
from datetime import datetime, timedelta, timezone

from services.api.execution import ExecutionError, ExecutionService, InMemoryBank


class Clock:
    def __init__(self):
        self.value = datetime(2026, 10, 26, 1, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.value

    def advance(self, **kwargs):
        self.value += timedelta(**kwargs)


class ExecutionGateTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.bank = InMemoryBank({("alice", "alice-main"): 200_000, ("bob", "bob-main"): 0})
        self.service = ExecutionService(sqlite3.connect(":memory:", check_same_thread=False), self.bank,
                                        password_checker=lambda password, user: password == "correct-password",
                                        clock=self.clock)

    def operation(self, *, amount=50000, key=None):
        return self.service.create_operation(user_id="alice", account_id="alice-main", recipient_user_id="bob",
                                              amount_cents=amount, idempotency_key=key)

    def authorize(self, op, *, password=None):
        confirmed = self.service.confirm(op["operation_id"], user_id="alice", plan_version=op["plan_version"], params_hash=op["params_hash"])
        if confirmed["status"] == "NEEDS_AUTH":
            self.assertIsNotNone(password)
            return self.service.verify(op["operation_id"], user_id="alice", password=password)
        return confirmed

    def test_confirmation_expiry_and_no_bank_write(self):
        op = self.operation()
        with self.assertRaisesRegex(ExecutionError, "尚未完成确认"):
            self.service.execute(op["operation_id"], user_id="alice", idempotency_key=op["idempotency_key"])
        self.clock.advance(minutes=6)
        with self.assertRaisesRegex(ExecutionError, "确认已过期"):
            self.service.confirm(op["operation_id"], user_id="alice", plan_version=1, params_hash=op["params_hash"])
        self.assertEqual(self.service.status(op["operation_id"], user_id="alice")["status"], "EXPIRED")
        self.assertEqual(self.bank.balances[("alice", "alice-main")], 200000)

    def test_red_operation_requires_password_and_parameters_are_bound(self):
        op = self.operation(amount=100001)
        with self.assertRaises(ExecutionError) as caught:
            self.service.confirm(op["operation_id"], user_id="alice", plan_version=2, params_hash=op["params_hash"])
        self.assertEqual(caught.exception.code, "PLAN_STALE")
        self.service.confirm(op["operation_id"], user_id="alice", plan_version=1, params_hash=op["params_hash"])
        # Confirmation creates NEEDS_AUTH, but it is not yet executable.
        self.assertEqual(self.service.status(op["operation_id"], user_id="alice")["status"], "NEEDS_AUTH")
        with self.assertRaises(ExecutionError):
            self.service.execute(op["operation_id"], user_id="alice", idempotency_key=op["idempotency_key"])
        self.authorize(op, password="correct-password")
        self.service.execute(op["operation_id"], user_id="alice", idempotency_key=op["idempotency_key"])
        result = self.service.process_one()
        self.assertEqual(result["status"], "SUCCEEDED")

    def test_duplicate_idempotency_only_enqueues_once(self):
        first = self.operation(amount=1000, key="same-key")
        second = self.operation(amount=2000, key="same-key")
        self.assertEqual(first["operation_id"], second["operation_id"])
        self.authorize(first)
        self.service.execute(first["operation_id"], user_id="alice", idempotency_key="same-key")
        self.service.execute(first["operation_id"], user_id="alice", idempotency_key="same-key")
        self.service.process_one()
        self.assertEqual(self.bank.balances[("alice", "alice-main")], 199000)
        self.assertEqual(self.bank.balances[("bob", "bob-main")], 1000)

    def test_concurrent_quota_escalates_second_operation(self):
        a = self.operation(amount=60000, key="a")
        b = self.operation(amount=60000, key="b")
        self.authorize(a)
        self.authorize(b)
        self.service.execute(a["operation_id"], user_id="alice", idempotency_key="a")
        with self.assertRaises(ExecutionError) as caught:
            self.service.execute(b["operation_id"], user_id="alice", idempotency_key="b")
        self.assertEqual(caught.exception.code, "AUTH_REQUIRED")
        self.assertEqual(self.service.status(b["operation_id"], user_id="alice")["status"], "NEEDS_AUTH")
        self.service.verify(b["operation_id"], user_id="alice", password="correct-password")
        self.service.execute(b["operation_id"], user_id="alice", idempotency_key="b")
        self.service.process_one()
        self.service.process_one()
        self.assertEqual(self.bank.balances[("alice", "alice-main")], 80000)

    def test_lost_response_is_recovered_without_second_payment(self):
        op = self.operation(amount=5000)
        self.authorize(op)
        self.service.execute(op["operation_id"], user_id="alice", idempotency_key=op["idempotency_key"])
        self.bank.drop_response_once = True
        unknown = self.service.process_one()
        self.assertEqual(unknown["status"], "PENDING_UNKNOWN")
        self.assertEqual(self.bank.balances[("alice", "alice-main")], 195000)
        recovered = self.service.recover_unknown(op["operation_id"], user_id="alice")
        self.assertEqual(recovered["status"], "SUCCEEDED")
        self.assertEqual(self.bank.balances[("alice", "alice-main")], 195000)


if __name__ == "__main__":
    unittest.main()
