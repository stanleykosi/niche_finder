"""Persist the separately derived Shorts-to-long-form bridge assessment.

Revision ID: 0007_media_bridge_assessment
Revises: 0006_bigint_public_counters
"""

from alembic import op
import sqlalchemy as sa

revision = "0007_media_bridge_assessment"
down_revision = "0006_bigint_public_counters"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("niche_candidates")}
    if "bridge_assessment" not in columns:
        op.add_column("niche_candidates", sa.Column("bridge_assessment", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("niche_candidates")}
    if "bridge_assessment" in columns:
        op.drop_column("niche_candidates", "bridge_assessment")
