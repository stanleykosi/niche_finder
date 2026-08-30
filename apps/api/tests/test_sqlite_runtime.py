from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from apps.api.app.core.config import AppMode, Settings
from apps.api.app.db.session import Database


def _stamp_legacy_revision_0007(database_path: Path) -> None:
    """Create the smallest real pre-0008 SQLite schema instead of current metadata."""
    engine = create_engine(f"sqlite:///{database_path}")
    statements = [
        "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)",
        "CREATE TABLE research_runs (id VARCHAR(36) NOT NULL PRIMARY KEY)",
        "CREATE TABLE channels (id VARCHAR(36) NOT NULL PRIMARY KEY)",
        "CREATE TABLE videos (id VARCHAR(36) NOT NULL PRIMARY KEY, channel_id VARCHAR(36), FOREIGN KEY(channel_id) REFERENCES channels (id))",
        """CREATE TABLE channel_snapshots (
            id VARCHAR(36) NOT NULL PRIMARY KEY,
            channel_id VARCHAR(36) NOT NULL,
            observed_at DATETIME NOT NULL,
            subscriber_count BIGINT,
            total_view_count BIGINT NOT NULL,
            video_count BIGINT NOT NULL,
            source VARCHAR(32) NOT NULL,
            FOREIGN KEY(channel_id) REFERENCES channels (id)
        )""",
        """CREATE TABLE video_snapshots (
            id VARCHAR(36) NOT NULL PRIMARY KEY,
            video_id VARCHAR(36) NOT NULL,
            observed_at DATETIME NOT NULL,
            view_count BIGINT NOT NULL,
            like_count BIGINT,
            comment_count BIGINT,
            source VARCHAR(32) NOT NULL,
            FOREIGN KEY(video_id) REFERENCES videos (id)
        )""",
        """CREATE TABLE comment_samples (
            id VARCHAR(36) NOT NULL PRIMARY KEY,
            video_id VARCHAR(36) NOT NULL,
            source_comment_id VARCHAR(120) NOT NULL,
            text TEXT NOT NULL,
            like_count BIGINT NOT NULL,
            published_at DATETIME,
            observed_at DATETIME NOT NULL,
            is_pinned_if_known BOOLEAN,
            source VARCHAR(32) NOT NULL,
            FOREIGN KEY(video_id) REFERENCES videos (id)
        )""",
    ]
    with engine.begin() as connection:
        for statement in statements:
            connection.exec_driver_sql(statement)
        connection.execute(text("INSERT INTO alembic_version (version_num) VALUES ('0007_media_bridge_assessment')"))
        connection.execute(text("INSERT INTO channels (id) VALUES ('channel-1')"))
        connection.execute(text("INSERT INTO videos (id, channel_id) VALUES ('video-1', 'channel-1')"))
        for identifier, observed_at in (("comment-old", "2026-08-24 00:00:00"), ("comment-new", "2026-08-25 00:00:00")):
            connection.execute(text("""
                INSERT INTO comment_samples (
                    id, video_id, source_comment_id, text, like_count,
                    observed_at, is_pinned_if_known, source
                ) VALUES (
                    :id, 'video-1', 'source-comment-1', :text, 0,
                    :observed_at, NULL, 'youtube_api'
                )
            """), {"id": identifier, "text": identifier, "observed_at": observed_at})
    engine.dispose()


def test_sqlite_migrations_reach_head_without_unsupported_type_alter(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[3]
    database_path = tmp_path / "migrated.db"
    monkeypatch.setenv("APP_MODE", "development")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("BROWSER_PROFILE_ROOT", str(tmp_path / "runtime" / "browser_profiles"))
    monkeypatch.setenv("MEDIA_WORK_ROOT", str(tmp_path / "runtime" / "media"))
    config = Config(str(root / "apps/api/alembic.ini"))
    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{database_path}")
    assert "video_snapshots" in inspect(engine).get_table_names()
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0009_comment_sample_identity"
    engine.dispose()


def test_existing_sqlite_revision_0007_upgrades_constraints_to_head(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[3]
    database_path = tmp_path / "legacy-0007.db"
    _stamp_legacy_revision_0007(database_path)
    monkeypatch.setenv("APP_MODE", "development")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("BROWSER_PROFILE_ROOT", str(tmp_path / "runtime" / "browser_profiles"))
    monkeypatch.setenv("MEDIA_WORK_ROOT", str(tmp_path / "runtime" / "media"))

    command.upgrade(Config(str(root / "apps/api/alembic.ini")), "head")

    engine = create_engine(f"sqlite:///{database_path}")
    inspector = inspect(engine)
    for table, unique_name, index_name in (
        ("channel_snapshots", "uq_channel_snapshot_run_source", "ix_channel_snapshots_research_run_id"),
        ("video_snapshots", "uq_video_snapshot_run_source", "ix_video_snapshots_research_run_id"),
    ):
        assert "research_run_id" in {column["name"] for column in inspector.get_columns(table)}
        assert unique_name in {constraint["name"] for constraint in inspector.get_unique_constraints(table)}
        assert index_name in {index["name"] for index in inspector.get_indexes(table)}
    assert "uq_comment_sample_source_identity" in {
        constraint["name"] for constraint in inspector.get_unique_constraints("comment_samples")
    }
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0009_comment_sample_identity"
        assert connection.execute(text("SELECT COUNT(*) FROM comment_samples")).scalar_one() == 1
        assert connection.execute(text("SELECT text FROM comment_samples")).scalar_one() == "comment-new"
    engine.dispose()


def test_development_sqlite_keeps_durable_journal_and_synchronous_defaults(tmp_path):
    settings = Settings(
        app_mode=AppMode.DEVELOPMENT,
        database_url=f"sqlite:///{tmp_path / 'durable.db'}",
        browser_profile_root=str(tmp_path / "runtime" / "browser_profiles"),
        media_work_root=str(tmp_path / "runtime" / "media"),
    )
    database = Database(settings)
    with database.engine.connect() as connection:
        journal_mode = str(connection.exec_driver_sql("PRAGMA journal_mode").scalar_one()).lower()
        synchronous = int(connection.exec_driver_sql("PRAGMA synchronous").scalar_one())
        foreign_keys = int(connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one())
    assert journal_mode != "memory"
    assert synchronous != 0
    assert foreign_keys == 1
    database.engine.dispose()
