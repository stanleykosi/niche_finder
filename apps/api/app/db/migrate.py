"""Apply every canonical Alembic revision to the configured database."""

from pathlib import Path

from alembic import command
from alembic.config import Config

from ..core.config import ensure_database_dir, load_settings


def main() -> None:
    # Alembic opens SQLite before ``Database`` is ever constructed, so the
    # image entrypoint must prepare the configured file's parent itself.
    ensure_database_dir(load_settings())
    root = Path(__file__).resolve().parents[4]
    config = Config(str(root / "apps/api/alembic.ini"))
    command.upgrade(config, "head")
    print("Alembic schema at head")


if __name__ == "__main__":
    main()
