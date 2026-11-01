"""Create the immutable mock-bank schema.

Revision ID: 0001_bank_schema
Revises:
Create Date: 2026-10-27
"""

from alembic import op
import sqlalchemy as sa


revision = "0001_bank_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS app")
    op.execute("CREATE SCHEMA IF NOT EXISTS bank")
    op.create_table(
        "users",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("username", sa.Text(), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False, server_default="customer"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="app",
    )
    op.create_table(
        "accounts",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("user_id", sa.Text(), sa.ForeignKey("app.users.id"), nullable=False),
        sa.Column("tail4", sa.String(4), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="CNY"),
        sa.Column("opening_balance_cents", sa.BigInteger(), nullable=False),
        sa.Column("balance_cents", sa.BigInteger(), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "id"),
        sa.CheckConstraint("currency = 'CNY'"),
        sa.CheckConstraint("balance_cents >= 0"),
        schema="bank",
    )
    op.create_table(
        "recipients",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("user_id", sa.Text(), sa.ForeignKey("app.users.id"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("alias", sa.Text()),
        sa.Column("bank_ref", sa.Text(), nullable=False),
        sa.Column("tail4", sa.String(4), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("user_id", "id"),
        schema="bank",
    )
    op.create_table(
        "transfer_quotes",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("account_id", sa.Text(), nullable=False),
        sa.Column("recipient_id", sa.Text(), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("fee_cents", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="CNY"),
        sa.Column("reference", sa.String(140)),
        sa.Column("params_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id", "account_id"], ["bank.accounts.user_id", "bank.accounts.id"]),
        sa.ForeignKeyConstraint(["user_id", "recipient_id"], ["bank.recipients.user_id", "bank.recipients.id"]),
        sa.CheckConstraint("amount_cents > 0"),
        sa.CheckConstraint("fee_cents >= 0"),
        sa.CheckConstraint("currency = 'CNY'"),
        schema="bank",
    )
    op.create_table(
        "transfers",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("quote_id", sa.Text(), sa.ForeignKey("bank.transfer_quotes.id"), nullable=False),
        sa.Column("account_id", sa.Text(), nullable=False),
        sa.Column("recipient_id", sa.Text(), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("fee_cents", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="CNY"),
        sa.Column("reference", sa.String(140)),
        sa.Column("params_hash", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("bank_reference", sa.Text(), unique=True),
        sa.Column("failure_code", sa.Text()),
        sa.Column("scheduled_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "id"),
        sa.UniqueConstraint("user_id", "idempotency_key"),
        sa.ForeignKeyConstraint(["user_id", "account_id"], ["bank.accounts.user_id", "bank.accounts.id"]),
        sa.ForeignKeyConstraint(["user_id", "recipient_id"], ["bank.recipients.user_id", "bank.recipients.id"]),
        sa.CheckConstraint("amount_cents > 0"),
        sa.CheckConstraint("fee_cents >= 0"),
        sa.CheckConstraint("currency = 'CNY'"),
        sa.CheckConstraint("status IN ('PENDING','SUCCEEDED','FAILED')"),
        schema="bank",
    )
    op.create_table(
        "transactions",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("account_id", sa.Text(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("direction", sa.String(3), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("merchant", sa.Text(), nullable=False),
        sa.Column("memo", sa.Text(), nullable=False, server_default=""),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("refund_of", sa.Text(), sa.ForeignKey("bank.transactions.id")),
        sa.Column("transfer_id", sa.Text(), sa.ForeignKey("bank.transfers.id"), unique=True),
        sa.UniqueConstraint("account_id", "external_id"),
        sa.ForeignKeyConstraint(["user_id", "account_id"], ["bank.accounts.user_id", "bank.accounts.id"]),
        sa.CheckConstraint("amount_cents > 0"),
        sa.CheckConstraint("direction IN ('IN','OUT')"),
        sa.CheckConstraint("kind IN ('expense','refund','income','transfer')"),
        sa.CheckConstraint("status IN ('POSTED','PENDING','FAILED')"),
        schema="bank",
    )
    op.create_index("transaction_scope_date", "transactions", ["user_id", "posted_at"], schema="bank")
    op.create_index("transaction_category_date", "transactions", ["user_id", "category", "posted_at"], schema="bank")
    op.create_table(
        "journal_entries",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("business_ref", sa.Text(), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="bank",
    )
    op.create_table(
        "journal_lines",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("entry_id", sa.Text(), sa.ForeignKey("bank.journal_entries.id"), nullable=False),
        sa.Column("ledger_account_ref", sa.Text(), nullable=False),
        sa.Column("signed_cents", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("signed_cents <> 0"),
        schema="bank",
    )
    op.create_table(
        "mandates",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("account_id", sa.Text(), nullable=False),
        sa.Column("merchant", sa.Text(), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("period", sa.Text(), nullable=False),
        sa.Column("next_due", sa.Date()),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("can_cancel", sa.Boolean(), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "id"),
        sa.ForeignKeyConstraint(["user_id", "account_id"], ["bank.accounts.user_id", "bank.accounts.id"]),
        sa.CheckConstraint("amount_cents >= 0"),
        sa.CheckConstraint("status IN ('ACTIVE','CANCELLED','EXPIRED')"),
        schema="bank",
    )
    op.create_table(
        "mandate_actions",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("mandate_id", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("params_hash", sa.String(64), nullable=False),
        sa.Column("result_status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "idempotency_key"),
        sa.ForeignKeyConstraint(["user_id", "mandate_id"], ["bank.mandates.user_id", "bank.mandates.id"]),
        schema="bank",
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION bank.assert_balanced_journal_entry()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE target_entry text;
        BEGIN
          target_entry := COALESCE(NEW.entry_id, OLD.entry_id);
          IF EXISTS (SELECT 1 FROM bank.journal_entries WHERE id = target_entry)
             AND COALESCE((SELECT SUM(signed_cents) FROM bank.journal_lines
                           WHERE entry_id = target_entry), 0) <> 0 THEN
            RAISE EXCEPTION 'journal entry % is not balanced', target_entry;
          END IF;
          RETURN NULL;
        END $$
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER journal_lines_balanced
        AFTER INSERT OR UPDATE OR DELETE ON bank.journal_lines
        DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
        EXECUTE FUNCTION bank.assert_balanced_journal_entry()
        """
    )
    op.execute(
        """
        DO $$ BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'futureledger_bank_runtime') THEN
            CREATE ROLE futureledger_bank_runtime NOLOGIN;
          END IF;
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'futureledger_bank_read') THEN
            CREATE ROLE futureledger_bank_read NOLOGIN;
          END IF;
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'futureledger_runtime') THEN
            CREATE ROLE futureledger_runtime LOGIN PASSWORD 'futureledger-runtime'
              NOSUPERUSER NOCREATEDB NOCREATEROLE;
          ELSE
            ALTER ROLE futureledger_runtime PASSWORD 'futureledger-runtime';
          END IF;
        END $$
        """
    )
    op.execute("GRANT USAGE ON SCHEMA bank TO futureledger_bank_runtime")
    op.execute("GRANT USAGE ON SCHEMA app, bank TO futureledger_bank_read")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA bank TO futureledger_bank_runtime")
    op.execute("GRANT SELECT ON ALL TABLES IN SCHEMA app, bank TO futureledger_bank_read")
    op.execute("GRANT futureledger_bank_runtime TO futureledger_runtime")


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS bank CASCADE")
    op.execute("DROP SCHEMA IF EXISTS app CASCADE")
