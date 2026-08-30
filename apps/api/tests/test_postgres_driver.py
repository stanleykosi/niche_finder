"""Deployment-driver checks that do not open a database connection."""

import psycopg

from apps.api.app.core.config import AppMode, Settings
from apps.api.app.db.session import Database


def test_compose_postgresql_url_has_installed_sync_driver():
    assert psycopg.__version__
    settings = Settings(
        app_mode=AppMode.PRODUCTION,
        database_url="postgresql+psycopg://postgres:postgres@postgres:5432/nicheintel",
    )
    database = Database(settings)
    assert database.engine.dialect.driver == "psycopg"
    database.engine.dispose()
