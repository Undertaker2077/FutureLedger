from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, Any
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, sessionmaker

from .auth import authenticate
from .config import Settings
from .contracts import TransactionQuery
from .db import create_session_factory
from .domain import BankError
from .repository import BankRepository
from .service import BankService


def create_app(
    settings: Settings | None = None,
    session_factory: sessionmaker[Session] | None = None,
) -> FastAPI:
    resolved_settings = settings or Settings.from_env()
    factory = session_factory or create_session_factory(resolved_settings)
    repository = BankRepository(factory, resolved_settings.service_token)
    service = BankService(repository)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        bind = factory.kw.get("bind")
        if bind is not None:
            bind.dispose()

    app = FastAPI(title="FutureLedger Mock Bank", version="1.0.0", lifespan=lifespan)

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request.state.request_id = request.headers.get("X-Request-ID") or str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.exception_handler(BankError)
    async def bank_error_handler(request: Request, exc: BankError) -> JSONResponse:
        error = exc.as_dict()
        status = exc.http_status
        if exc.code == "FORBIDDEN":
            status = 404
            error = {
                "code": "NOT_FOUND",
                "message": "resource was not found",
                "recoverable": False,
                "next_action": None,
            }
        return JSONResponse(
            status_code=status,
            content={
                "data": None,
                "error": error,
                "request_id": request.state.request_id,
            },
        )

    def envelope(request: Request, data: Any) -> dict[str, Any]:
        return {"data": data, "error": None, "request_id": request.state.request_id}

    def subject_dependency(
        authorization: Annotated[str | None, Header()] = None,
        x_authenticated_user: Annotated[str | None, Header()] = None,
    ) -> str:
        return authenticate(resolved_settings, authorization, x_authenticated_user)

    Subject = Annotated[str, Depends(subject_dependency)]

    @app.get("/health/live")
    def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    def ready() -> dict[str, str]:
        repository.ping()
        return {"status": "ready"}

    @app.get("/bank/v1/capabilities")
    def capabilities(request: Request, _subject: Subject) -> dict[str, Any]:
        return envelope(
            request,
            {
                "idempotent_transfers": True,
                "transfer_status_query": True,
                "mandate_status_query": True,
                "scheduled_transfers": False,
                "mandate_restore": False,
            },
        )

    @app.get("/bank/v1/accounts/{account_id}/balance")
    def get_balance(account_id: str, request: Request, subject: Subject) -> dict[str, Any]:
        return envelope(request, service.get_balance(subject, account_id))

    @app.get("/bank/v1/recipients/{recipient_id}")
    def resolve_recipient(
        recipient_id: str, request: Request, subject: Subject
    ) -> dict[str, Any]:
        return envelope(request, service.resolve_recipient(subject, recipient_id))

    @app.get("/bank/v1/transactions")
    def list_transactions(
        request: Request,
        subject: Subject,
        account_id: str | None = None,
        start: datetime | None = None,
        end_exclusive: datetime | None = None,
        status: str | None = None,
        kind: str | None = None,
        cursor: str | None = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ) -> dict[str, Any]:
        query = TransactionQuery.model_construct(
            account_id=account_id,
            start=start,
            end_exclusive=end_exclusive,
            status=status,
            kind=kind,
            cursor=cursor,
            limit=limit,
        )
        return envelope(request, service.list_transactions(subject, query))

    @app.get("/bank/v1/mandates")
    def list_mandates(
        request: Request, subject: Subject, account_id: str | None = None
    ) -> dict[str, Any]:
        return envelope(request, service.list_mandates(subject, account_id))

    @app.get("/bank/v1/mandates/{mandate_id}")
    def get_mandate(
        mandate_id: str, request: Request, subject: Subject
    ) -> dict[str, Any]:
        return envelope(request, service.get_mandate_status(subject, mandate_id))

    return app


app = create_app()
