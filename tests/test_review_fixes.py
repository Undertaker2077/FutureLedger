"""Regressions for the independently reproduced repository review findings."""
import unittest
from datetime import datetime, timedelta, timezone

from demo.cashflow import simulate_cashflow
from services.api.execution.service import ExecutionError, ExecutionService, InMemoryBank


class ExecutionReviewTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 1, tzinfo=timezone.utc)
        self.bank = InMemoryBank({('alice', 'a'): 1_000_000, ('bob', 'b'): 0})
        self.service = ExecutionService(ExecutionService.connect(), self.bank,
            clock=lambda: self.now, password_checker=lambda password, user: password == 'correct')
        self.addCleanup(self.service.db.close)

    def ready(self, **kwargs):
        op = self.service.create_operation(user_id='alice', account_id='a',
            recipient_user_id='bob', amount_cents=2500, **kwargs)
        self.service.confirm(op['operation_id'], user_id='alice', plan_version=1,
                             params_hash=op['params_hash'])
        return op

    def execute(self, op):
        return self.service.execute(op['operation_id'], user_id='alice',
                                    idempotency_key=op['idempotency_key'])

    def test_expired_ready_operation_never_enqueues(self):
        op = self.ready()
        self.now += timedelta(minutes=6)
        with self.assertRaises(ExecutionError) as caught:
            self.execute(op)
        self.assertEqual(caught.exception.code, 'AUTH_EXPIRED')
        self.assertFalse(self.service.db.in_transaction)
        self.assertIsNone(self.service.process_one())
        self.assertEqual(self.bank.balances[('alice', 'a')], 1_000_000)

    def test_cancel_queued_operation_removes_dispatch_and_releases_quota(self):
        op = self.ready()
        self.execute(op)
        self.assertEqual(self.service.cancel_unsubmitted(op['operation_id'], user_id='alice'), 'CANCELLED')
        self.assertIsNone(self.service.process_one())
        self.assertEqual(self.bank.balances[('alice', 'a')], 1_000_000)
        self.assertEqual(self.service.db.execute('SELECT state FROM quota_reservations').fetchone()[0], 'RELEASED')

    def test_claimed_operation_cannot_report_cancelled(self):
        op = self.ready()
        self.execute(op)
        self.service.claim_outbox('worker')
        self.assertEqual(self.service.cancel_unsubmitted(op['operation_id'], user_id='alice'), 'PENDING_UNKNOWN')

    def test_future_date_is_explicitly_unsupported(self):
        with self.assertRaises(ExecutionError) as caught:
            self.ready(execution_date='2026-12-01')
        self.assertEqual(caught.exception.code, 'UNSUPPORTED_SCHEDULE')
        self.assertFalse(self.bank.transfers)

    def test_valid_date_is_checked_again_at_execute(self):
        op = self.ready(execution_date='2026-11-01')
        self.now += timedelta(days=1)
        with self.assertRaises(ExecutionError):
            self.execute(op)
        self.assertIsNone(self.service.process_one())

    def test_business_day_uses_shanghai_timezone(self):
        self.now = datetime(2026, 10, 31, 17, tzinfo=timezone.utc)
        op = self.ready(execution_date='2026-11-01')
        self.execute(op)
        self.assertEqual(self.service.db.execute('SELECT business_date FROM quota_reservations').fetchone()[0], '2026-11-01')

    def test_default_password_checker_refuses_verification(self):
        service = ExecutionService(ExecutionService.connect(), self.bank)
        self.addCleanup(service.db.close)
        op = service.create_operation(user_id='alice', account_id='a', recipient_user_id='bob', amount_cents=200_000)
        service.confirm(op['operation_id'], user_id='alice', plan_version=1, params_hash=op['params_hash'])
        with self.assertRaises(ExecutionError):
            service.verify(op['operation_id'], user_id='alice', password='anything')
        self.assertEqual(service.status(op['operation_id'], user_id='alice')['status'], 'NEEDS_AUTH')

    def test_missing_operation_does_not_poison_next_transaction(self):
        op = self.ready()
        with self.assertRaises(ExecutionError):
            self.service.execute('missing', user_id='alice', idempotency_key='missing')
        self.assertFalse(self.service.db.in_transaction)
        self.assertEqual(self.execute(op)['status'], 'ENQUEUED')

    def test_unknown_response_is_not_resubmitted_by_worker(self):
        op = self.ready()
        self.execute(op)
        self.bank.drop_response_once = True
        self.assertEqual(self.service.process_one()['status'], 'PENDING_UNKNOWN')
        self.assertIsNone(self.service.process_one())
        self.assertEqual(self.service.db.execute('SELECT state FROM quota_reservations').fetchone()[0], 'RESERVED')
        self.assertEqual(self.service.recover_unknown(op['operation_id'], user_id='alice')['status'], 'SUCCEEDED')
        self.assertIsNone(self.service.process_one())
        self.assertEqual(len(self.bank.transfers), 1)


class CashflowReviewTests(unittest.TestCase):
    def test_custom_goal_controls_purchase_and_balances(self):
        small = simulate_cashflow(salary_day=17, purchase_day=19, goal_cents=10_000)
        large = simulate_cashflow(salary_day=17, purchase_day=19, goal_cents=1_000_000)
        self.assertEqual(small.events[-1]['signed_cents'], -10_000)
        self.assertEqual(small.points_cents[:18], large.points_cents[:18])
        self.assertEqual(small.points_cents[-1] - large.points_cents[-1], 990_000)


if __name__ == '__main__':
    unittest.main()
