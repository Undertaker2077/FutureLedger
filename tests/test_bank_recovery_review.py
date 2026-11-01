import tempfile
import unittest
import asyncio
from pathlib import Path

from fastapi.testclient import TestClient
from services.api.agent.auth import Principal
from services.api.execution import ExecutionGateAdapter
from services.api.execution.api import create_execution_app

from services.api.execution.service import ExecutionService
from services.api.execution.a_adapter import RoleABankAdapter


class LostReplyBank:
    def __init__(self):
        self.submit_calls = 0
        self.lookup_calls = 0
        self.balance = 900_000
        self.transfers = {}

    def quote_transfer(self, subject, request, now):
        return {'quote_id': 'q', 'params_hash': 'confirmed-hash'}

    def submit_transfer(self, subject, quote_id, params_hash, key):
        self.submit_calls += 1
        self.balance -= 2500
        self.transfers[(subject, key)] = {'transfer_id': 'bank-id', 'status': 'SUCCEEDED', 'bank_reference': 'BANK-FACT'}
        raise TimeoutError('bank committed; response lost')

    def get_transfer_by_key(self, subject, key):
        self.lookup_calls += 1
        return self.transfers[(subject, key)]


class BankRecoveryReviewTests(unittest.TestCase):
    def test_status_interfaces_reconcile_unknown_bank_facts(self):
        for interface in ('api', 'c'):
            with self.subTest(interface=interface):
                bank = LostReplyBank()
                service = ExecutionService(ExecutionService.connect(), RoleABankAdapter(bank, request_factory=dict))
                try:
                    op = service.create_operation(user_id='alice', account_id='a', recipient_user_id='rec_1', amount_cents=2500)
                    service.confirm(op['operation_id'], user_id='alice', plan_version=1, params_hash=op['params_hash'])
                    service.execute(op['operation_id'], user_id='alice', idempotency_key=op['idempotency_key'])
                    self.assertEqual(service.process_one()['status'], 'PENDING_UNKNOWN')
                    if interface == 'api':
                        with TestClient(create_execution_app(service, user_id='alice')) as client:
                            result = client.get('/api/operations/' + op['operation_id']).json()
                        status = result['status']
                    else:
                        principal = Principal('alice', ('a',), ('personal_ledger',))
                        result = asyncio.run(ExecutionGateAdapter(service).get(principal, op['operation_id']))
                        status = result.status
                    self.assertEqual(status, 'SUCCEEDED')
                    self.assertEqual(bank.submit_calls, 1)
                finally:
                    service.db.close()

    def test_restart_recovers_original_submission_by_read_only_key_lookup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / 'execution.sqlite')
            bank = LostReplyBank()
            first = ExecutionService(ExecutionService.connect(path), RoleABankAdapter(bank, request_factory=dict))
            op = first.create_operation(user_id='alice', account_id='a', recipient_user_id='rec_1', amount_cents=2500)
            first.confirm(op['operation_id'], user_id='alice', plan_version=1, params_hash=op['params_hash'])
            first.execute(op['operation_id'], user_id='alice', idempotency_key=op['idempotency_key'])
            self.assertEqual(first.process_one()['status'], 'PENDING_UNKNOWN')
            self.assertEqual(first.db.execute('SELECT state FROM quota_reservations').fetchone()[0], 'RESERVED')
            first.db.close()
            restarted = ExecutionService(ExecutionService.connect(path), RoleABankAdapter(bank, request_factory=dict))
            self.addCleanup(restarted.db.close)
            recovered = restarted.recover_unknown(op['operation_id'], user_id='alice')
            self.assertEqual(recovered['status'], 'SUCCEEDED')
            self.assertEqual(recovered['bank_ref'], 'BANK-FACT')
            self.assertEqual(bank.submit_calls, 1)
            self.assertEqual(bank.lookup_calls, 1)
            self.assertEqual(bank.balance, 897_500)
            self.assertIsNone(restarted.process_one())


if __name__ == '__main__':
    unittest.main()
