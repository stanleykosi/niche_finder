from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from ..core.config import Settings, ensure_database_dir
from .base import Base
from . import models  # noqa: F401 - register mapped tables


class Database:
    def __init__(self, settings: Settings) -> None:
        ensure_database_dir(settings)
        url = settings.database_sync_url
        if url.startswith("sqlite"):
            connect_args = {"check_same_thread": False}
        else:
            connect_args = {}
        self.engine = create_engine(url, connect_args=connect_args, future=True)
        if url.startswith("sqlite"):
            @event.listens_for(self.engine, "connect")
            def _sqlite_closed_mode_tuning(dbapi_connection, connection_record):  # noqa: ARG001
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                if settings.is_closed:
                    # Only disposable, network-blocked closed-test databases
                    # trade durability for test speed. Development keeps
                    # SQLite's durable journal and synchronous defaults.
                    cursor.execute("PRAGMA journal_mode=MEMORY")
                    cursor.execute("PRAGMA synchronous=OFF")
                cursor.close()
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False, class_=Session)

    def create_schema(self) -> None:
        Base.metadata.create_all(self.engine)

    def session(self) -> Session:
        return self.session_factory()

    def drop_schema(self) -> None:
        Base.metadata.drop_all(self.engine)
