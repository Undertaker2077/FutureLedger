"""Explicit A read bridge for the transfer DAG; no authority to submit a payment."""
import asyncio
from datetime import datetime, timezone

from .errors import AgentError
from .orchestration.adapters import UnavailableBankRead


class RoleABankReads(UnavailableBankRead):
    provenance = 'A'

    def __init__(self, bank, request_factory=None):
        self.bank = bank
        self.request_factory = request_factory

    def supports(self, tool_name):
        return tool_name in {'get_balance', 'resolve_recipient', 'quote_transfer'}

    async def _call(self, method, *args):
        try:
            return await asyncio.to_thread(getattr(self.bank, method), *args)
        except Exception as exc:
            code = getattr(exc, 'code', 'UPSTREAM_UNAVAILABLE')
            if code not in {'FORBIDDEN', 'UNSUPPORTED', 'AUTH_REQUIRED'}:
                code = 'UPSTREAM_UNAVAILABLE'
            raise AgentError(code, 503) from None

    async def get_balance(self, principal, inputs):
        value = await self._call('get_balance', principal.subject, inputs.source_account_id)
        return {'available_cents': value['balance_cents']}

    async def resolve_recipient(self, principal, inputs):
        value = await self._call('resolve_recipient', principal.subject, inputs.recipient_id)
        return {'recipient_id': value['recipient_id'], 'verified': value['verified']}

    async def quote_transfer(self, principal, inputs):
        factory = self.request_factory
        if factory is None:
            from mock_bank.contracts import TransferRequest
            factory = TransferRequest
        request = factory(account_id=inputs.source_account_id, recipient_id=inputs.recipient_id,
                          amount_cents=inputs.amount_cents, currency='CNY')
        value = await self._call('quote_transfer', principal.subject, request, datetime.now(timezone.utc))
        fee = value['fee_cents'] if isinstance(value, dict) else value.fee_cents
        return {'valid': True, 'fee_cents': fee}
