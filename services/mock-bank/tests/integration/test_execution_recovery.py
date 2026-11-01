"""The real bank ledger and B must agree after a dropped commit response."""
from mock_bank.adapter import ServiceBankAdapter
from mock_bank.faults import FaultPoint
from mock_bank.repository import BankRepository
from mock_bank.service import BankService
from mock_bank.reconcile import reconcile
from services.api.execution import ExecutionService, RoleABankAdapter


def test_real_bank_commit_recovers_after_b_restart_without_resubmission(seeded_session_factory, tmp_path):
    bank = BankService(BankRepository(seeded_session_factory, 'synthetic-recovery-token'))

    class DropReply(ServiceBankAdapter):
        def submit_transfer(self, subject, quote_id, params_hash, idempotency_key):
            return self.service.submit_transfer(subject, quote_id, params_hash, idempotency_key,
                                                 FaultPoint.DROP_RESPONSE_AFTER_COMMIT)

    path = str(tmp_path / 'execution.sqlite')
    first = ExecutionService(ExecutionService.connect(path), RoleABankAdapter(DropReply(bank)))
    try:
        op = first.create_operation(user_id='test_user', account_id='acc_daily', recipient_user_id='rec_1', amount_cents=2500)
        first.confirm(op['operation_id'], user_id='test_user', plan_version=1, params_hash=op['params_hash'])
        first.execute(op['operation_id'], user_id='test_user', idempotency_key=op['idempotency_key'])
        assert first.process_one()['status'] == 'PENDING_UNKNOWN'
        assert bank.get_balance('test_user', 'acc_daily')['balance_cents'] == 897500
    finally:
        first.db.close()
    restarted = ExecutionService(ExecutionService.connect(path), RoleABankAdapter(ServiceBankAdapter(bank)))
    try:
        result = restarted.recover_unknown(op['operation_id'], user_id='test_user')
        assert result['status'] == 'SUCCEEDED'
        assert result['bank_ref']
        assert restarted.process_one() is None
        assert bank.get_balance('test_user', 'acc_daily')['balance_cents'] == 897500
        with seeded_session_factory() as session:
            assert reconcile(session).valid
    finally:
        restarted.db.close()
