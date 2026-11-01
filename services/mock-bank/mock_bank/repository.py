from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import Select, and_, or_, select, text
from sqlalchemy.orm import Session, sessionmaker

from .contracts import TransactionQuery, TransferRequest
from .domain import BankError
from .faults import FaultPoint, InjectedBankFault
from .models import (
    Account,
    JournalEntry,
    JournalLine,
    Mandate,
    MandateAction,
    Recipient,
    Transaction,
    Transfer,
    TransferQuote,
)


class BankRepository:
    def __init__(self, session_factory: sessionmaker[Session], cursor_secret: str) -> None:
        self.session_factory = session_factory
        self._cursor_secret = cursor_secret.encode("utf-8")

    @staticmethod
    def _resource_error(session: Session, model: type, resource_id: str) -> BankError:
        exists = session.scalar(select(model.id).where(model.id == resource_id)) is not None
        if exists:
            return BankError("FORBIDDEN", "resource is not owned by subject", http_status=403)
        return BankError("NOT_FOUND", "resource was not found", http_status=404)

    def get_account(self, subject: str, account_id: str) -> Account:
        with self.session_factory() as session:
            account = session.scalar(
                select(Account).where(Account.id == account_id, Account.user_id == subject)
            )
            if account is None:
                raise self._resource_error(session, Account, account_id)
            session.expunge(account)
            return account

    def get_recipient(self, subject: str, recipient_id: str) -> Recipient:
        with self.session_factory() as session:
            recipient = session.scalar(
                select(Recipient).where(
                    Recipient.id == recipient_id, Recipient.user_id == subject
                )
            )
            if recipient is None:
                raise self._resource_error(session, Recipient, recipient_id)
            session.expunge(recipient)
            return recipient

    def list_transactions(
        self, subject: str, query: TransactionQuery
    ) -> tuple[list[tuple[Transaction, str]], str | None]:
        with self.session_factory() as session:
            if query.account_id is not None:
                account = session.scalar(
                    select(Account.id).where(
                        Account.id == query.account_id, Account.user_id == subject
                    )
                )
                if account is None:
                    raise self._resource_error(session, Account, query.account_id)

            statement: Select[tuple[Transaction, str]] = (
                select(Transaction, Account.currency)
                .join(Account, Account.id == Transaction.account_id)
                .where(Transaction.user_id == subject)
            )
            if query.account_id is not None:
                statement = statement.where(Transaction.account_id == query.account_id)
            if query.start is not None:
                statement = statement.where(Transaction.posted_at >= query.start)
            if query.end_exclusive is not None:
                statement = statement.where(Transaction.posted_at < query.end_exclusive)
            if query.status is not None:
                statement = statement.where(Transaction.status == query.status)
            if query.kind is not None:
                statement = statement.where(Transaction.kind == query.kind)
            if query.cursor is not None:
                cursor_time, cursor_id = self._decode_cursor(subject, query.cursor)
                statement = statement.where(
                    or_(
                        Transaction.posted_at < cursor_time,
                        and_(
                            Transaction.posted_at == cursor_time,
                            Transaction.id < cursor_id,
                        ),
                    )
                )

            rows = list(
                session.execute(
                    statement.order_by(
                        Transaction.posted_at.desc(), Transaction.id.desc()
                    ).limit(query.limit + 1)
                ).all()
            )
            has_more = len(rows) > query.limit
            rows = rows[: query.limit]
            next_cursor = None
            if has_more and rows:
                next_cursor = self._encode_cursor(
                    subject, rows[-1][0].posted_at, rows[-1][0].id
                )
            for transaction, _currency in rows:
                session.expunge(transaction)
            return rows, next_cursor

    def list_mandates(self, subject: str, account_id: str | None) -> list[Mandate]:
        with self.session_factory() as session:
            if account_id is not None:
                account = session.scalar(
                    select(Account.id).where(
                        Account.id == account_id, Account.user_id == subject
                    )
                )
                if account is None:
                    raise self._resource_error(session, Account, account_id)
            statement = select(Mandate).where(Mandate.user_id == subject)
            if account_id is not None:
                statement = statement.where(Mandate.account_id == account_id)
            mandates = list(session.scalars(statement.order_by(Mandate.id)).all())
            for mandate in mandates:
                session.expunge(mandate)
            return mandates

    def get_mandate(self, subject: str, mandate_id: str) -> Mandate:
        with self.session_factory() as session:
            mandate = session.scalar(
                select(Mandate).where(
                    Mandate.id == mandate_id, Mandate.user_id == subject
                )
            )
            if mandate is None:
                raise self._resource_error(session, Mandate, mandate_id)
            session.expunge(mandate)
            return mandate

    def ping(self) -> None:
        with self.session_factory() as session:
            session.execute(select(1)).scalar_one()

    def create_transfer_quote(
        self,
        subject: str,
        request: TransferRequest,
        params_hash: str,
        now: datetime,
        ttl_seconds: int,
    ) -> TransferQuote:
        quote = TransferQuote(
            id=f"quote_{uuid4().hex}",
            user_id=subject,
            account_id=request.account_id,
            recipient_id=request.recipient_id,
            amount_cents=request.amount_cents,
            fee_cents=0,
            currency=request.currency,
            reference=request.reference,
            params_hash=params_hash,
            expires_at=now + timedelta(seconds=ttl_seconds),
            created_at=now,
        )
        with self.session_factory.begin() as session:
            session.add(quote)
        return quote

    def submit_transfer(
        self,
        subject: str,
        quote_id: str,
        params_hash: str,
        idempotency_key: str,
        now: datetime,
        fault: FaultPoint | None = None,
    ) -> tuple[Transfer, bool]:
        with self.session_factory.begin() as session:
            session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:identity, 0))"),
                {"identity": f"transfer:{subject}:{idempotency_key}"},
            )
            existing = session.scalar(
                select(Transfer).where(
                    Transfer.user_id == subject,
                    Transfer.idempotency_key == idempotency_key,
                )
            )
            if existing is not None:
                if existing.params_hash != params_hash:
                    raise BankError(
                        "IDEMPOTENCY_CONFLICT",
                        "idempotency key was already used for different parameters",
                        http_status=409,
                    )
                return existing, True

            quote = session.scalar(
                select(TransferQuote).where(
                    TransferQuote.id == quote_id, TransferQuote.user_id == subject
                )
            )
            if quote is None:
                raise self._resource_error(session, TransferQuote, quote_id)
            if quote.params_hash != params_hash:
                raise BankError(
                    "QUOTE_MISMATCH",
                    "confirmed parameters do not match the bank quote",
                    next_action="request a new quote and confirm it",
                    http_status=409,
                )
            if quote.expires_at <= now:
                raise BankError(
                    "QUOTE_EXPIRED",
                    "bank quote has expired",
                    recoverable=True,
                    next_action="request a replacement quote",
                    http_status=409,
                )

            account = session.scalar(
                select(Account)
                .where(Account.id == quote.account_id, Account.user_id == subject)
                .with_for_update()
            )
            recipient = session.scalar(
                select(Recipient)
                .where(Recipient.id == quote.recipient_id, Recipient.user_id == subject)
                .with_for_update()
            )
            if account is None:
                raise self._resource_error(session, Account, quote.account_id)
            if recipient is None:
                raise self._resource_error(session, Recipient, quote.recipient_id)
            if not recipient.verified:
                raise BankError(
                    "RECIPIENT_UNVERIFIED",
                    "recipient is not verified by the bank",
                    next_action="verify the recipient before retrying",
                    http_status=409,
                )
            total = quote.amount_cents + quote.fee_cents
            transfer_id = f"transfer_{uuid4().hex}"
            insufficient = account.balance_cents < total
            transfer = Transfer(
                id=transfer_id,
                user_id=subject,
                quote_id=quote.id,
                account_id=quote.account_id,
                recipient_id=quote.recipient_id,
                amount_cents=quote.amount_cents,
                fee_cents=quote.fee_cents,
                currency=quote.currency,
                reference=quote.reference,
                params_hash=quote.params_hash,
                idempotency_key=idempotency_key,
                status="FAILED" if insufficient else "SUCCEEDED",
                bank_reference=None if insufficient else f"MOCK-{uuid4().hex.upper()}",
                failure_code="INSUFFICIENT_FUNDS" if insufficient else None,
                created_at=now,
                updated_at=now,
            )
            session.add(transfer)
            session.flush()

            if insufficient:
                if fault == FaultPoint.BEFORE_COMMIT:
                    raise InjectedBankFault("injected fault at before_commit")
                return transfer, False

            transaction = Transaction(
                id=f"tx_transfer_{uuid4().hex}",
                external_id=transfer.bank_reference,
                user_id=subject,
                account_id=account.id,
                amount_cents=total,
                direction="OUT",
                kind="transfer",
                status="POSTED",
                category="转账",
                merchant=recipient.name,
                memo=quote.reference or "",
                posted_at=now,
                transfer_id=transfer.id,
            )
            entry = JournalEntry(
                id=f"journal_{uuid4().hex}", business_ref=transfer.id, created_at=now
            )
            session.add_all([transaction, entry])
            session.flush()
            session.add_all(
                [
                    JournalLine(
                        id=f"line_{uuid4().hex}",
                        entry_id=entry.id,
                        ledger_account_ref=f"account:{account.id}",
                        signed_cents=-total,
                    ),
                    JournalLine(
                        id=f"line_{uuid4().hex}",
                        entry_id=entry.id,
                        ledger_account_ref="clearing:external",
                        signed_cents=total,
                    ),
                ]
            )
            account.balance_cents -= total
            account.as_of = now
            if fault == FaultPoint.BEFORE_COMMIT:
                raise InjectedBankFault("injected fault at before_commit")
            return transfer, False

    def get_transfer(self, subject: str, transfer_id: str) -> Transfer:
        with self.session_factory() as session:
            transfer = session.scalar(
                select(Transfer).where(
                    Transfer.id == transfer_id, Transfer.user_id == subject
                )
            )
            if transfer is None:
                raise self._resource_error(session, Transfer, transfer_id)
            session.expunge(transfer)
            return transfer

    def cancel_mandate(
        self,
        subject: str,
        mandate_id: str,
        idempotency_key: str,
        params_hash: str,
        now: datetime,
    ) -> tuple[Mandate, str, bool]:
        with self.session_factory.begin() as session:
            session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:identity, 0))"),
                {"identity": f"mandate:{subject}:{idempotency_key}"},
            )
            existing = session.scalar(
                select(MandateAction).where(
                    MandateAction.user_id == subject,
                    MandateAction.idempotency_key == idempotency_key,
                )
            )
            if existing is not None:
                if existing.params_hash != params_hash:
                    raise BankError(
                        "IDEMPOTENCY_CONFLICT",
                        "idempotency key was already used for a different mandate",
                        http_status=409,
                    )
                mandate = session.scalar(
                    select(Mandate).where(
                        Mandate.id == existing.mandate_id,
                        Mandate.user_id == subject,
                    )
                )
                if mandate is None:
                    raise BankError(
                        "NOT_FOUND", "mandate was not found", http_status=404
                    )
                return mandate, existing.result_status, True

            mandate = session.scalar(
                select(Mandate)
                .where(Mandate.id == mandate_id, Mandate.user_id == subject)
                .with_for_update()
            )
            if mandate is None:
                raise self._resource_error(session, Mandate, mandate_id)

            if not mandate.can_cancel and mandate.status == "ACTIVE":
                result_status = "UNSUPPORTED"
            else:
                if mandate.status == "ACTIVE":
                    mandate.status = "CANCELLED"
                    mandate.cancelled_at = now
                    mandate.updated_at = now
                result_status = mandate.status

            session.add(
                MandateAction(
                    id=f"mandate_action_{uuid4().hex}",
                    user_id=subject,
                    mandate_id=mandate.id,
                    idempotency_key=idempotency_key,
                    params_hash=params_hash,
                    result_status=result_status,
                    created_at=now,
                    updated_at=now,
                )
            )
            session.flush()
            return mandate, result_status, False

    def _encode_cursor(self, subject: str, posted_at: datetime, row_id: str) -> str:
        payload = json.dumps(
            {"subject": subject, "posted_at": posted_at.isoformat(), "id": row_id},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        signature = hmac.new(self._cursor_secret, payload, hashlib.sha256).digest()
        encoded_payload = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
        encoded_signature = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
        return f"{encoded_payload}.{encoded_signature}"

    def _decode_cursor(self, subject: str, cursor: str) -> tuple[datetime, str]:
        try:
            encoded_payload, encoded_signature = cursor.split(".", 1)
            payload = base64.urlsafe_b64decode(
                (encoded_payload + "=" * (-len(encoded_payload) % 4)).encode("ascii")
            )
            signature = base64.urlsafe_b64decode(
                (encoded_signature + "=" * (-len(encoded_signature) % 4)).encode("ascii")
            )
            expected = hmac.new(self._cursor_secret, payload, hashlib.sha256).digest()
            if not hmac.compare_digest(signature, expected):
                raise ValueError("invalid signature")
            value = json.loads(payload)
            if value["subject"] != subject:
                raise ValueError("subject mismatch")
            return datetime.fromisoformat(value["posted_at"]), str(value["id"])
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise BankError(
                "INVALID_CURSOR",
                "cursor is invalid for this subject",
                next_action="restart pagination without a cursor",
                http_status=400,
            ) from exc
