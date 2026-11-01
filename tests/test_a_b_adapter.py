import unittest
from datetime import datetime

from services.api.execution import ExecutionService
from services.api.execution.a_adapter import RoleABankAdapter


class FakeRoleABank:
    def __init__(self):
        self.next_id = 0
        self.transfers = {}

    def quote_transfer(self, subject, request, now):
        self.next_id += 1
        return {"quote_id": f"quote-{self.next_id}", "params_hash": "h"}

    def submit_transfer(self, subject, quote_id, params_hash, idempotency_key):
        transfer_id = self.transfers.setdefault(idempotency_key, f"transfer-{len(self.transfers)+1}")
        return {"transfer_id": transfer_id, "status": "SUCCEEDED", "bank_reference": f"bank-{transfer_id}"}

    def get_transfer_status(self, subject, transfer_id):
        return {"status": "SUCCEEDED"}


class RoleABridgeTests(unittest.TestCase):
    def test_b_worker_port_calls_a_contract_once_and_recovers_status(self):
        bank = FakeRoleABank()
        adapter = RoleABankAdapter(bank, request_factory=dict)
        ref = adapter.submit_transfer(
            operation_id="op-1", user_id="alice", account_id="acc_daily",
            recipient_user_id="rec_1", amount_cents=2500, idempotency_key="key-1",
        )
        self.assertEqual(ref, "bank-transfer-1")
        self.assertEqual(adapter.get_transfer_status(operation_id="op-1", idempotency_key="key-1"), "SUCCEEDED")
        self.assertEqual(len(bank.transfers), 1)


if __name__ == "__main__":
    unittest.main()
