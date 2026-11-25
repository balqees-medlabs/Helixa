"""NGS pipeline tables & machine-auth support (Spec 4)

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-25

Scaffold (T001): ``upgrade()``/``downgrade()`` are intentionally empty here;
the schema lands in T003–T008 of Phase 2.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
