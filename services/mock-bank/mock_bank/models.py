from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "app"}

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    username: Mapped[str] = mapped_column(Text, unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text, default="customer")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint("user_id", "id"),
        CheckConstraint("currency = 'CNY'"),
        CheckConstraint("balance_cents >= 0"),
        {"schema": "bank"},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("app.users.id"))
    tail4: Mapped[str] = mapped_column(String(4))
    currency: Mapped[str] = mapped_column(String(3), default="CNY")
    opening_balance_cents: Mapped[int] = mapped_column(BigInteger)
    balance_cents: Mapped[int] = mapped_column(BigInteger)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Recipient(Base):
    __tablename__ = "recipients"
    __table_args__ = (
        UniqueConstraint("user_id", "id"),
        {"schema": "bank"},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("app.users.id"))
    name: Mapped[str] = mapped_column(Text)
    alias: Mapped[str | None] = mapped_column(Text)
    bank_ref: Mapped[str] = mapped_column(Text)
    tail4: Mapped[str] = mapped_column(String(4))
    verified: Mapped[bool] = mapped_column(Boolean, default=False)


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("account_id", "external_id"),
        ForeignKeyConstraint(
            ["user_id", "account_id"], ["bank.accounts.user_id", "bank.accounts.id"]
        ),
        CheckConstraint("amount_cents > 0"),
        CheckConstraint("direction IN ('IN','OUT')"),
        CheckConstraint("status IN ('POSTED','PENDING','FAILED')"),
        Index("transaction_scope_date", "user_id", "posted_at"),
        Index("transaction_category_date", "user_id", "category", "posted_at"),
        {"schema": "bank"},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[str] = mapped_column(Text)
    account_id: Mapped[str] = mapped_column(Text)
    external_id: Mapped[str] = mapped_column(Text)
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    direction: Mapped[str] = mapped_column(String(3))
    kind: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(Text)
    merchant: Mapped[str] = mapped_column(Text)
    memo: Mapped[str] = mapped_column(Text, default="")
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    refund_of: Mapped[str | None] = mapped_column(
        ForeignKey("bank.transactions.id"), nullable=True
    )
    transfer_id: Mapped[str | None] = mapped_column(
        ForeignKey("bank.transfers.id"), nullable=True, unique=True
    )


class TransferQuote(Base):
    __tablename__ = "transfer_quotes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "account_id"], ["bank.accounts.user_id", "bank.accounts.id"]
        ),
        ForeignKeyConstraint(
            ["user_id", "recipient_id"],
            ["bank.recipients.user_id", "bank.recipients.id"],
        ),
        CheckConstraint("amount_cents > 0"),
        CheckConstraint("fee_cents >= 0"),
        {"schema": "bank"},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[str] = mapped_column(Text)
    account_id: Mapped[str] = mapped_column(Text)
    recipient_id: Mapped[str] = mapped_column(Text)
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    fee_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    currency: Mapped[str] = mapped_column(String(3), default="CNY")
    reference: Mapped[str | None] = mapped_column(String(140))
    params_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Transfer(Base):
    __tablename__ = "transfers"
    __table_args__ = (
        UniqueConstraint("user_id", "id"),
        UniqueConstraint("user_id", "idempotency_key"),
        ForeignKeyConstraint(
            ["user_id", "account_id"], ["bank.accounts.user_id", "bank.accounts.id"]
        ),
        ForeignKeyConstraint(
            ["user_id", "recipient_id"],
            ["bank.recipients.user_id", "bank.recipients.id"],
        ),
        CheckConstraint("amount_cents > 0"),
        CheckConstraint("fee_cents >= 0"),
        CheckConstraint("status IN ('PENDING','SUCCEEDED','FAILED')"),
        {"schema": "bank"},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[str] = mapped_column(Text)
    quote_id: Mapped[str] = mapped_column(ForeignKey("bank.transfer_quotes.id"))
    account_id: Mapped[str] = mapped_column(Text)
    recipient_id: Mapped[str] = mapped_column(Text)
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    fee_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    currency: Mapped[str] = mapped_column(String(3), default="CNY")
    reference: Mapped[str | None] = mapped_column(String(140))
    params_hash: Mapped[str] = mapped_column(String(64))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16))
    bank_reference: Mapped[str | None] = mapped_column(Text, unique=True)
    failure_code: Mapped[str | None] = mapped_column(Text)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class JournalEntry(Base):
    __tablename__ = "journal_entries"
    __table_args__ = ({"schema": "bank"},)

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    business_ref: Mapped[str] = mapped_column(Text, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class JournalLine(Base):
    __tablename__ = "journal_lines"
    __table_args__ = (
        CheckConstraint("signed_cents <> 0"),
        {"schema": "bank"},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    entry_id: Mapped[str] = mapped_column(ForeignKey("bank.journal_entries.id"))
    ledger_account_ref: Mapped[str] = mapped_column(Text)
    signed_cents: Mapped[int] = mapped_column(BigInteger)


class Mandate(Base):
    __tablename__ = "mandates"
    __table_args__ = (
        UniqueConstraint("user_id", "id"),
        ForeignKeyConstraint(
            ["user_id", "account_id"], ["bank.accounts.user_id", "bank.accounts.id"]
        ),
        CheckConstraint("amount_cents >= 0"),
        CheckConstraint("status IN ('ACTIVE','CANCELLED','EXPIRED')"),
        {"schema": "bank"},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[str] = mapped_column(Text)
    account_id: Mapped[str] = mapped_column(Text)
    merchant: Mapped[str] = mapped_column(Text)
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    period: Mapped[str] = mapped_column(Text)
    next_due: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16))
    can_cancel: Mapped[bool] = mapped_column(Boolean)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MandateAction(Base):
    __tablename__ = "mandate_actions"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key"),
        ForeignKeyConstraint(
            ["user_id", "mandate_id"], ["bank.mandates.user_id", "bank.mandates.id"]
        ),
        {"schema": "bank"},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[str] = mapped_column(Text)
    mandate_id: Mapped[str] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    params_hash: Mapped[str] = mapped_column(String(64))
    result_status: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

