"""Static deployment-contract checks; these never contact hosting providers."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from apps.api.app.db import migrate, schema_gate
from workers.research import worker


ROOT = Path(__file__).resolve().parents[3]


def test_vercel_project_is_rootable_at_the_nextjs_application():
    config = json.loads((ROOT / "apps/web/vercel.json").read_text())
    assert config["framework"] == "nextjs"
    assert config["installCommand"] == "npm ci"
    assert config["buildCommand"] == "npm run build"
    assert (ROOT / "apps/web/package-lock.json").is_file()


def test_railway_api_image_migrates_and_binds_the_injected_port():
    dockerfile = (ROOT / "Dockerfile.api").read_text()
    assert "python -m apps.api.app.db.migrate" in dockerfile
    assert "mkdir -p /app/runtime" in dockerfile
    assert '${PORT:-${API_PORT:-8000}}' in dockerfile
    assert "BROWSER_EXECUTABLE_PATH=/usr/bin/chromium" in dockerfile
    assert "ffmpeg chromium" in dockerfile


def test_default_sqlite_migration_creates_its_parent_before_alembic(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./runtime/nicheintel.db")
    observed = []

    def upgrade(config, revision):  # noqa: ARG001
        observed.append((tmp_path / "runtime").is_dir())
        assert revision == "head"

    monkeypatch.setattr(migrate.command, "upgrade", upgrade)
    migrate.main()
    assert observed == [True]


def test_schema_gate_rejects_an_unmigrated_database_before_worker_start(monkeypatch):
    monkeypatch.setattr(schema_gate, "expected_schema_revisions", lambda: {"head"})
    monkeypatch.setattr(schema_gate, "current_schema_revisions", lambda engine: {"old"})
    with pytest.raises(RuntimeError, match="worker refused to start"):
        schema_gate.wait_for_migrations(object(), timeout_seconds=0)


def test_worker_startup_waits_for_migrations_before_storage_maintenance(monkeypatch):
    events = []

    class Engine:
        def dispose(self):
            events.append("disposed")

    settings = type("SettingsDouble", (), {
        "bootstrap_schema_on_startup": False,
        "migration_wait_timeout_seconds": 12,
        "migration_poll_interval_seconds": 0.25,
    })()
    database = type("DatabaseDouble", (), {"engine": Engine()})()
    monkeypatch.setattr(
        worker,
        "create_worker_context",
        lambda: {"settings": settings, "database": database},
    )

    def wait(engine, **kwargs):
        assert engine is database.engine
        assert kwargs == {"timeout_seconds": 12, "poll_interval_seconds": 0.25}
        events.append("schema_at_head")

    async def publish(ctx, *, cleanup):
        assert ctx["database"] is database
        assert cleanup is True
        events.append("storage_maintained")

    monkeypatch.setattr(worker, "wait_for_migrations", wait)
    monkeypatch.setattr(worker, "_publish_worker_storage", publish)
    context = {"redis": object()}
    asyncio.run(worker.startup(context))
    assert events == ["schema_at_head", "storage_maintained"]


def test_deployment_runbook_uses_predeploy_migration_and_worker_gate():
    readme = (ROOT / "README.md").read_text()
    assert "Railway Pre-deploy" in readme
    assert "python -m apps.api.app.db.migrate" in readme
    assert "cannot dequeue a job until it matches" in readme
    assert "publishes measured usage to Redis" in readme
