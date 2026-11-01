from datetime import datetime, timezone

from fastapi.testclient import TestClient

from mock_bank.api import create_app
from mock_bank.contracts import TransferRequest
from mock_bank.repository import BankRepository
from mock_bank.service import BankService


def test_lookup_by_idempotency_key_is_read_only_and_subject_scoped(bank_settings, seeded_session_factory):
    service = BankService(BankRepository(seeded_session_factory, 'lookup-test'))
    quote = service.quote_transfer('test_user', TransferRequest(account_id='acc_daily', recipient_id='rec_1',
        amount_cents=2500), datetime.now(timezone.utc))
    key = 'lookup/key+?!#'
    transfer = service.submit_transfer('test_user', quote.quote_id, quote.params_hash, key)
    with TestClient(create_app(bank_settings, seeded_session_factory)) as client:
        headers = {'Authorization': 'Bearer test-service-token', 'X-Authenticated-User': 'test_user', 'Idempotency-Key': key}
        response = client.get('/bank/v1/transfers/by-key', headers=headers)
        assert response.status_code == 200
        assert response.json()['data']['transfer_id'] == transfer.transfer_id
        headers['X-Authenticated-User'] = 'isolation_user'
        assert client.get('/bank/v1/transfers/by-key', headers=headers).status_code == 404
    assert service.get_balance('test_user', 'acc_daily')['balance_cents'] == 897_500
