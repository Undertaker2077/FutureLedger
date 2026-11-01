"""FastAPI adapter for the execution gate.

The endpoint layer deliberately accepts only operation identifiers and server
generated hashes.  It never accepts a model-supplied risk level or a client
supplied user id.
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .service import ExecutionError, ExecutionService


class CreateOperation(BaseModel):
    account_id: str
    recipient_user_id: str
    amount_cents: int = Field(gt=0)
    plan_id: str = "transfer"
    plan_version: int = Field(default=1, gt=0)
    idempotency_key: str | None = None


class ConfirmOperation(BaseModel):
    plan_version: int = Field(gt=0)
    params_hash: str


class VerifyOperation(BaseModel):
    password: str = Field(min_length=1, max_length=128)


class ExecuteOperation(BaseModel):
    idempotency_key: str


def create_execution_app(service: ExecutionService, *, user_id: str) -> FastAPI:
    """Create a small authenticated-context app for local integration tests."""
    app = FastAPI(title="FutureLedger execution gate", version="0.1.0")

    def call(fn):
        try:
            return fn()
        except ExecutionError as exc:
            raise HTTPException(409, {"code": exc.code, "message": str(exc), "status": exc.status}) from exc

    @app.post("/api/operations")
    def create(body: CreateOperation):
        return call(lambda: service.create_operation(user_id=user_id, **body.model_dump()))

    @app.post("/api/operations/{operation_id}/confirm")
    def confirm(operation_id: str, body: ConfirmOperation):
        return call(lambda: service.confirm(operation_id, user_id=user_id, **body.model_dump()))

    @app.post("/api/operations/{operation_id}/verify")
    def verify(operation_id: str, body: VerifyOperation):
        return call(lambda: service.verify(operation_id, user_id=user_id, password=body.password))

    @app.post("/api/operations/{operation_id}/execute")
    def execute(operation_id: str, body: ExecuteOperation):
        return call(lambda: service.execute(operation_id, user_id=user_id, **body.model_dump()))

    @app.get("/api/operations/{operation_id}")
    def status(operation_id: str):
        return call(lambda: service.status(operation_id, user_id=user_id))

    return app
