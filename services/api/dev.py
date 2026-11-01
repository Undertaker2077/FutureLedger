"""Development factory; startup requires an LLM provider and key."""

import os

from demo.provider import ChatProvider

from .app import ROOT, create_app
from .agent.adapters import FixtureAnalysis
from .agent.auth import DevelopmentTokens, Principal
from .execution import ExecutionGateAdapter, ExecutionService, RoleABankAdapter


def create_dev_app():
    token = os.getenv('FUTURELEDGER_DEV_TOKEN')
    if not token or len(token) < 24:
        raise RuntimeError('Set FUTURELEDGER_DEV_TOKEN to a private local token of at least 24 characters.')
    auth = DevelopmentTokens({token: Principal('test_user', ('acc_daily', 'acc_savings'), ('personal_ledger',))})
    provider = ChatProvider()
    kwargs = dict(authenticator=auth, analysis=FixtureAnalysis(ROOT / 'data/benchmark.sqlite'),
                  agent_provider=provider if provider.provider != 'local' else None)
    # Set both variables to opt into the real A↔B demo path. Without them the
    # app remains read-only, which avoids silently creating a bank client.
    bank_url = os.getenv('FUTURELEDGER_BANK_URL')
    bank_token = os.getenv('FUTURELEDGER_BANK_TOKEN')
    if bank_url and bank_token:
        from mock_bank.adapter import HttpBankAdapter
        bank = RoleABankAdapter(HttpBankAdapter(bank_url, bank_token))
        password = os.getenv('FUTURELEDGER_DEMO_PASSWORD', '')
        checker = lambda supplied, _user: bool(password) and supplied == password
        service = ExecutionService(ExecutionService.connect(os.getenv('FUTURELEDGER_EXECUTION_DB', ':memory:')),
                                   bank, password_checker=checker)
        gate = ExecutionGateAdapter(service, worker=service)
        kwargs.update(execution=gate, execution_gate_adapter=gate)
    return create_app(**kwargs)
