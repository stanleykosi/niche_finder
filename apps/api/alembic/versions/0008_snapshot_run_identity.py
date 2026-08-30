"""Make public snapshots idempotent within one research run.

Revision ID: 0008_snapshot_run_identity
Revises: 0007_media_bridge_assessment
"""

from alembic import op
import sqlalchemy as sa


revision = "0008_snapshot_run_identity"
down_revision = "0007_media_bridge_assessment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    sqlite = op.get_bind().dialect.name == "sqlite"
    for table, entity_column, unique_name, index_name, foreign_key_name in (
        (
            "channel_snapshots",
            "channel_id",
            "uq_channel_snapshot_run_source",
            "ix_channel_snapshots_research_run_id",
            "fk_channel_snapshots_research_run_id",
        ),
        (
            "video_snapshots",
            "video_id",
            "uq_video_snapshot_run_source",
            "ix_video_snapshots_research_run_id",
            "fk_video_snapshots_research_run_id",
        ),
    ):
        columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}
        if "research_run_id" not in columns:
            if sqlite:
                with op.batch_alter_table(table, recreate="always") as batch_op:
                    batch_op.add_column(sa.Column("research_run_id", sa.String(length=36), nullable=True))
                    batch_op.create_foreign_key(
                        foreign_key_name,
                        "research_runs",
                        ["research_run_id"],
                        ["id"],
                    )
                    batch_op.create_index(index_name, ["research_run_id"], unique=False)
                    batch_op.create_unique_constraint(
                        unique_name,
                        ["research_run_id", entity_column, "source"],
                    )
            else:
                op.add_column(table, sa.Column("research_run_id", sa.String(length=36), nullable=True))
                op.create_foreign_key(
                    foreign_key_name,
                    table,
                    "research_runs",
                    ["research_run_id"],
                    ["id"],
                )
                op.create_index(index_name, table, ["research_run_id"], unique=False)
                op.create_unique_constraint(
                    unique_name,
                    table,
                    ["research_run_id", entity_column, "source"],
                )


def downgrade() -> None:
    sqlite = op.get_bind().dialect.name == "sqlite"
    for table, unique_name, index_name, foreign_key_name in (
        (
            "video_snapshots",
            "uq_video_snapshot_run_source",
            "ix_video_snapshots_research_run_id",
            "fk_video_snapshots_research_run_id",
        ),
        (
            "channel_snapshots",
            "uq_channel_snapshot_run_source",
            "ix_channel_snapshots_research_run_id",
            "fk_channel_snapshots_research_run_id",
        ),
    ):
        columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}
        if "research_run_id" in columns:
            if sqlite:
                inspector = sa.inspect(op.get_bind())
                unique_names = {item["name"] for item in inspector.get_unique_constraints(table)}
                index_names = {item["name"] for item in inspector.get_indexes(table)}
                foreign_key_names = {item["name"] for item in inspector.get_foreign_keys(table)}
                with op.batch_alter_table(table, recreate="always") as batch_op:
                    if unique_name in unique_names:
                        batch_op.drop_constraint(unique_name, type_="unique")
                    if index_name in index_names:
                        batch_op.drop_index(index_name)
                    if foreign_key_name in foreign_key_names:
                        batch_op.drop_constraint(foreign_key_name, type_="foreignkey")
                    batch_op.drop_column("research_run_id")
            else:
                op.drop_constraint(unique_name, table, type_="unique")
                op.drop_index(index_name, table_name=table)
                op.drop_constraint(foreign_key_name, table, type_="foreignkey")
                op.drop_column(table, "research_run_id")
