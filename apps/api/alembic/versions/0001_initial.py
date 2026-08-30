"""Initial evidence schema.

The application uses ``Base.metadata.create_all`` for the no-dependency closed fixture
path; this revision documents the same schema for PostgreSQL deployments.
"""

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    from alembic import op
    from apps.api.app.db.base import Base
    from apps.api.app.db import models  # noqa: F401
    Base.metadata.create_all(op.get_bind())


def downgrade() -> None:
    from alembic import op
    from apps.api.app.db.base import Base
    from apps.api.app.db import models  # noqa: F401
    Base.metadata.drop_all(op.get_bind())
