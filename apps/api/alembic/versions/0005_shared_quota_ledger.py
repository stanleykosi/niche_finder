"""Add the process-shared YouTube API quota ledger.

Revision ID: 0005_shared_quota_ledger
Revises: 0004_runtime_artifacts
"""

from alembic import op
import sqlalchemy as sa

revision = "0005_shared_quota_ledger"
down_revision = "0004_runtime_artifacts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "quota_ledgers" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "quota_ledgers",
        sa.Column("ledger_date", sa.Date(), primary_key=True),
        sa.Column("used_search_calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("used_units", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    if "quota_ledgers" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("quota_ledgers")
