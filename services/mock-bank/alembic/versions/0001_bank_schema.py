"""Create mock-bank schemas and balanced-ledger enforcement.

Revision ID: 0001_bank_schema
Revises:
Create Date: 2026-10-27
"""

from alembic import op

from mock_bank.models import Base


revision = "0001_bank_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    op.execute("CREATE SCHEMA IF NOT EXISTS app")
    op.execute("CREATE SCHEMA IF NOT EXISTS bank")
    Base.metadata.create_all(connection)
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
        END $$
        """
    )
    op.execute("GRANT USAGE ON SCHEMA app, bank TO futureledger_bank_runtime")
    op.execute("GRANT USAGE ON SCHEMA app, bank TO futureledger_bank_read")
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA bank "
        "TO futureledger_bank_runtime"
    )
    op.execute("GRANT SELECT ON ALL TABLES IN SCHEMA app, bank TO futureledger_bank_read")


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS bank CASCADE")
    op.execute("DROP SCHEMA IF EXISTS app CASCADE")

