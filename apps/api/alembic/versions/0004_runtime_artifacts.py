"""Track runtime media and derived artifact lifecycle.

Revision ID: 0004_runtime_artifacts
Revises: 0003_evidence_bound_synthesis
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_runtime_artifacts"
down_revision = "0003_evidence_bound_synthesis"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "runtime_artifacts" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "runtime_artifacts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("research_run_id", sa.String(36), sa.ForeignKey("research_runs.id"), nullable=True),
        sa.Column("artifact_type", sa.String(48), nullable=False),
        sa.Column("path", sa.Text(), nullable=False, unique=True),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("state", sa.String(24), nullable=False, server_default="available"),
        sa.Column("metadata_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_runtime_artifacts_research_run_id", "runtime_artifacts", ["research_run_id"])
    op.create_index("ix_runtime_artifacts_artifact_type", "runtime_artifacts", ["artifact_type"])
    op.create_index("ix_runtime_artifacts_state", "runtime_artifacts", ["state"])
    op.create_index("ix_runtime_artifacts_expires_at", "runtime_artifacts", ["expires_at"])


def downgrade() -> None:
    if "runtime_artifacts" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("runtime_artifacts")
