"""Adapter that exposes B's execution gate to the C Agent contracts."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from ..agent.errors import AgentError, unsupported
from ..agent.dag.schemas import BOutcome, PreparedOperation, TransferInputs
from ..agent.ports import OperationState


class ExecutionGateAdapter:
    """Async C-facing adapter; all authority remains in ``ExecutionService``."""

    provenance = "mock_B"
    available = True

    def __init__(self, service, worker=None):
        self.service = service
        self.worker = worker

    def supports(self, tool_name):
        return tool_name in {"propose_transfer", "get_operation_status"}

    @staticmethod
    def _key(plan_id: str, version: int, node_id: str, inputs: Any) -> str:
        body = json.dumps({"plan_id": plan_id, "version": version, "node_id": node_id,
                           "inputs": inputs.model_dump()}, sort_keys=True, ensure_ascii=False)
        return "c_" + hashlib.sha256(body.encode()).hexdigest()

    @staticmethod
    def _transfer(raw: dict[str, Any], plan_id: str, version: int, node_id: str) -> TransferInputs:
        return TransferInputs(source_account_id=raw["account_id"], recipient_id=raw["recipient_user_id"],
                               amount_cents=raw["amount_cents"], execution_date=raw["execution_date"])

    async def create_operation(self, principal, proposal):
        if proposal.tool_name != "execution.transfer":
            raise unsupported("B 代扣执行")
        inputs = proposal.inputs
        key = self._key(proposal.plan_id, proposal.plan_version, proposal.node_id, inputs)
        raw = self.service.create_operation(user_id=principal.subject, account_id=inputs.source_account_id,
            recipient_user_id=inputs.recipient_id, amount_cents=inputs.amount_cents,
            execution_date=inputs.execution_date, plan_id=proposal.plan_id,
            plan_version=proposal.plan_version, idempotency_key=key)
        return PreparedOperation(operation_id=raw["operation_id"], plan_id=proposal.plan_id,
                                 plan_version=proposal.plan_version, node_id=proposal.node_id)

    async def get_operation_status(self, principal, binding):
        raw = self.service.status(binding.operation_id, user_id=principal.subject)
        status = {"ENQUEUED": "SUBMITTING"}.get(raw["status"], raw["status"])
        if status == "EXPIRED":
            status = "FAILED"
        params = self._transfer(raw, binding.plan_id, binding.plan_version, binding.node_id)
        return BOutcome(operation_id=binding.operation_id, plan_id=binding.plan_id,
                        plan_version=binding.plan_version, node_id=binding.node_id,
                        status=status, parameters=params, bank_ref=raw.get("bank_ref"))

    async def confirm_operation(self, principal, binding, command):
        raw = self.service.confirm(binding.operation_id, user_id=principal.subject,
                                   plan_version=command.plan_version, params_hash=command.params_hash)
        return await self.get_operation_status(principal, binding)

    async def request_verification(self, principal, binding, command):
        credential = command.credential.get_secret_value()
        try:
            self.service.verify(binding.operation_id, user_id=principal.subject, password=credential)
        finally:
            credential = None
        return await self.get_operation_status(principal, binding)

    async def execute_operation(self, principal, binding, command, idempotency_key):
        self.service.execute(binding.operation_id, user_id=principal.subject, idempotency_key=idempotency_key)
        if self.worker:
            self.worker.process_one("c-worker")
        return await self.get_operation_status(principal, binding)

    async def lookup_operation(self, principal, proposal):
        key = self._key(proposal.plan_id, proposal.plan_version, proposal.node_id, proposal.inputs)
        raw = self.service.lookup_by_key(user_id=principal.subject, idempotency_key=key)
        if not raw:
            return None
        return PreparedOperation(operation_id=raw["operation_id"], plan_id=proposal.plan_id,
                                 plan_version=proposal.plan_version, node_id=proposal.node_id)

    async def invalidate_operations(self, principal, plan_id, version, operation_ids):
        for operation_id in operation_ids:
            self.service.invalidate(operation_id, user_id=principal.subject)
        return {"plan_id": plan_id, "plan_version": version, "operation_ids": operation_ids, "invalidated": True}

    async def cancel_unsubmitted_task(self, principal, binding):
        status = self.service.cancel_unsubmitted(binding.operation_id, user_id=principal.subject)
        return {"operation_id": binding.operation_id, "plan_id": binding.plan_id,
                "plan_version": binding.plan_version, "node_id": binding.node_id, "status": status}

    async def check_mandate_scope(self, principal, inputs, scope_ref):
        raise unsupported("B 代扣范围确认")

    # Legacy C1 endpoints use this smaller gateway shape.
    async def propose(self, principal, snapshot, action):
        if action != "propose_transfer":
            raise unsupported("B 代扣执行")
        e = snapshot.entities
        if not all((e.source_account_id, e.recipient_id, e.amount_cents, e.execution_date)):
            raise AgentError("NEEDS_INFO", 409)
        key = self._key(snapshot.plan_id, snapshot.plan_version, "legacy", e)
        raw = self.service.create_operation(user_id=principal.subject, account_id=e.source_account_id,
            recipient_user_id=e.recipient_id, amount_cents=e.amount_cents, execution_date=e.execution_date,
            plan_id=snapshot.plan_id, plan_version=snapshot.plan_version, idempotency_key=key)
        return OperationState(operation_id=raw["operation_id"], plan_id=snapshot.plan_id,
                              plan_version=snapshot.plan_version, status="NEEDS_CONFIRM",
                              next_action="请在 B 确认具体参数。")

    async def confirm(self, principal, operation_id, command):
        raw = self.service.confirm(operation_id, user_id=principal.subject,
                                   plan_version=command.plan_version, params_hash=command.params_hash)
        return OperationState(operation_id=operation_id, plan_id=raw["plan_id"], plan_version=raw["plan_version"],
                              status={"ENQUEUED": "READY"}.get(raw["status"], raw["status"]),
                              next_action="需要独立强验证。" if raw["status"] == "NEEDS_AUTH" else "可以提交。")

    async def verify(self, principal, operation_id, command):
        raw = self.service.verify(operation_id, user_id=principal.subject,
                                   password=command.credential.get_secret_value())
        return OperationState(operation_id=operation_id, plan_id=raw["plan_id"], plan_version=raw["plan_version"],
                              status="READY", next_action="可以提交。")

    async def execute(self, principal, operation_id, command, idempotency_key):
        self.service.execute(operation_id, user_id=principal.subject, idempotency_key=idempotency_key)
        if self.worker:
            self.worker.process_one("legacy-worker")
        raw = self.service.status(operation_id, user_id=principal.subject)
        status = {"ENQUEUED": "SUBMITTING"}.get(raw["status"], raw["status"])
        if status == "EXPIRED": status = "FAILED"
        return OperationState(operation_id=operation_id, plan_id=raw["plan_id"], plan_version=raw["plan_version"],
                              status=status, bank_ref=raw.get("bank_ref"), next_action="查询 B 权威状态。")

    async def get(self, principal, operation_id):
        raw = self.service.status(operation_id, user_id=principal.subject)
        status = {"ENQUEUED": "SUBMITTING", "EXPIRED": "FAILED"}.get(raw["status"], raw["status"])
        return OperationState(operation_id=operation_id, plan_id=raw["plan_id"], plan_version=raw["plan_version"],
                              status=status, bank_ref=raw.get("bank_ref"), next_action="查询 B 权威状态。")
