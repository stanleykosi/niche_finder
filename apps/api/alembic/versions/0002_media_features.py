"""Persist deterministic and vision-ready browser media features.

Revision ID: 0002_media_features
Revises: 0001_initial
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_media_features"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("browser_media_observations")}
    if "feature_payload" not in columns:
        op.add_column("browser_media_observations", sa.Column("feature_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("browser_media_observations")}
    if "feature_payload" in columns:
        op.drop_column("browser_media_observations", "feature_payload")
