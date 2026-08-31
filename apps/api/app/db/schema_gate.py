"""Block workers until the shared database reaches the canonical Alembic head."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.engine import Engine


def alembic_config() -> Config:
    root = Path(__file__).resolve().parents[4]
    return Config(str(root / "apps/api/alembic.ini"))


def expected_schema_revisions(config: Config | None = None) -> set[str]:
    script = ScriptDirectory.from_config(config or alembic_config())
    return set(script.get_heads())


def current_schema_revisions(engine: Engine) -> set[str]:
    with engine.connect() as connection:
        return set(MigrationContext.configure(connection).get_current_heads())


def wait_for_migrations(
    engine: Engine,
    *,
    timeout_seconds: float = 300.0,
    poll_interval_seconds: float = 2.0,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Return at Alembic head or fail before the worker can dequeue a job."""
    expected = expected_schema_revisions()
    deadline = time.monotonic() + timeout_seconds
    current: set[str] = set()
    last_error: Exception | None = None
    while True:
        try:
            current = current_schema_revisions(engine)
            last_error = None
            if current == expected:
                return
        except Exception as exc:  # database may still be starting or migrating
            last_error = exc
        if time.monotonic() >= deadline:
            detail = (
                f"database unavailable: {type(last_error).__name__}: {last_error}"
                if last_error is not None
                else f"current revisions {sorted(current)!r}; expected {sorted(expected)!r}"
            )
            raise RuntimeError(
                "worker refused to start before the database reached Alembic head; " + detail
            ) from last_error
        sleep(min(poll_interval_seconds, max(0.0, deadline - time.monotonic())))
