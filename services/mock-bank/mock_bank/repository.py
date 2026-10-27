from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime

from sqlalchemy import Select, and_, or_, select
from sqlalchemy.orm import Session, sessionmaker

from .contracts import TransactionQuery
from .domain import BankError
from .models import Account, Mandate, Recipient, Transaction


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

