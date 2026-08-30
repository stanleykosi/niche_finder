"""Persist candidate research synthesis and independent critic output.

Revision ID: 0003_evidence_bound_synthesis
Revises: 0002_media_features
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_evidence_bound_synthesis"
down_revision = "0002_media_features"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("niche_candidates")}
    if "research_synthesis" not in columns:
        op.add_column("niche_candidates", sa.Column("research_synthesis", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    if "critic_assessment" not in columns:
        op.add_column("niche_candidates", sa.Column("critic_assessment", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("niche_candidates")}
    if "critic_assessment" in columns:
        op.drop_column("niche_candidates", "critic_assessment")
    if "research_synthesis" in columns:
        op.drop_column("niche_candidates", "research_synthesis")
