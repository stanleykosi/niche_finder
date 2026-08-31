"""Delete expired runtime artifacts and report reclaimed storage."""

from apps.api.app.core.config import load_settings
from apps.api.app.db.session import Database
from apps.api.app.repositories.store import ResearchRepository
from apps.api.app.storage.artifacts import RuntimeArtifactManager


def main() -> int:
    settings = load_settings()
    database = Database(settings)
    if settings.bootstrap_schema_on_startup:
        database.create_schema()
    manager = RuntimeArtifactManager(settings, ResearchRepository(database.session()))
    result = manager.cleanup_expired()
    status = manager.status()
    print(f"files deleted: {result.files_deleted}")
    print(f"directories deleted: {result.directories_deleted}")
    print(f"bytes reclaimed: {result.bytes_reclaimed}")
    print(f"remaining usage bytes: {status['usage_bytes']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
