"""Small worker loop for the execution Outbox.

Production deployment can replace the loop with a supervised process; the
claim/lease and recovery semantics stay in :mod:`services.api.execution`.
"""

from services.api.execution.service import ExecutionService


def run_once(service: ExecutionService, worker_id: str = "worker"):
    return service.process_one(worker_id)
