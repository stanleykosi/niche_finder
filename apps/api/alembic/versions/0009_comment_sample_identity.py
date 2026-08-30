"""Make retried public comment observations idempotent.

Revision ID: 0009_comment_sample_identity
Revises: 0008_snapshot_run_identity
"""

from alembic import op
import sqlalchemy as sa


revision = "0009_comment_sample_identity"
down_revision = "0008_snapshot_run_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Keep the freshest pre-constraint observation for each public source ID.
    op.execute("""
        DELETE FROM comment_samples
        WHERE id IN (
            SELECT id FROM (
                SELECT id, ROW_NUMBER() OVER (
                    PARTITION BY video_id, source_comment_id, source
                    ORDER BY observed_at DESC, id DESC
                ) AS duplicate_rank
                FROM comment_samples
            ) AS ranked_comments
            WHERE duplicate_rank > 1
        )
    """)
    constraints = {
        item["name"]
        for item in sa.inspect(op.get_bind()).get_unique_constraints("comment_samples")
    }
    if "uq_comment_sample_source_identity" not in constraints:
        if op.get_bind().dialect.name == "sqlite":
            with op.batch_alter_table("comment_samples", recreate="always") as batch_op:
                batch_op.create_unique_constraint(
                    "uq_comment_sample_source_identity",
                    ["video_id", "source_comment_id", "source"],
                )
        else:
            op.create_unique_constraint(
                "uq_comment_sample_source_identity",
                "comment_samples",
                ["video_id", "source_comment_id", "source"],
            )


def downgrade() -> None:
    constraints = {
        item["name"]
        for item in sa.inspect(op.get_bind()).get_unique_constraints("comment_samples")
    }
    if "uq_comment_sample_source_identity" in constraints:
        if op.get_bind().dialect.name == "sqlite":
            with op.batch_alter_table("comment_samples", recreate="always") as batch_op:
                batch_op.drop_constraint("uq_comment_sample_source_identity", type_="unique")
        else:
            op.drop_constraint(
                "uq_comment_sample_source_identity",
                "comment_samples",
                type_="unique",
            )
