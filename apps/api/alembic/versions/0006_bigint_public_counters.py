"""Store exact public and artifact counters as signed 64-bit values.

Revision ID: 0006_bigint_public_counters
Revises: 0005_shared_quota_ledger
"""

from alembic import op
import sqlalchemy as sa

revision = "0006_bigint_public_counters"
down_revision = "0005_shared_quota_ledger"
branch_labels = None
depends_on = None


_COLUMNS = {
    "channel_snapshots": (("subscriber_count", True), ("total_view_count", True), ("video_count", True)),
    "video_snapshots": (("view_count", False), ("like_count", True), ("comment_count", True)),
    "comment_samples": (("like_count", False),),
    "runtime_artifacts": (("size_bytes", False),),
}


def upgrade() -> None:
    # SQLite INTEGER already has signed 64-bit storage semantics and does not
    # support PostgreSQL's ALTER COLUMN TYPE syntax. No physical rewrite is
    # necessary on the documented SQLite fallback.
    if op.get_bind().dialect.name == "sqlite":
        return
    for table_name, columns in _COLUMNS.items():
        for column_name, nullable in columns:
            op.alter_column(
                table_name,
                column_name,
                existing_type=sa.Integer(),
                type_=sa.BigInteger(),
                existing_nullable=nullable,
            )


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        return
    for table_name, columns in _COLUMNS.items():
        for column_name, nullable in columns:
            op.alter_column(
                table_name,
                column_name,
                existing_type=sa.BigInteger(),
                type_=sa.Integer(),
                existing_nullable=nullable,
            )
