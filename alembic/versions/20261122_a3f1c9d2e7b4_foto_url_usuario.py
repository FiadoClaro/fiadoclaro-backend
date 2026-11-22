"""foto de perfil del usuario (solo el enlace)

Revision ID: a3f1c9d2e7b4
Revises: 0befd2b4c891
Create Date: 2026-11-22 10:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a3f1c9d2e7b4'
down_revision: Union[str, Sequence[str], None] = '0befd2b4c891'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Columna opcional: los usuarios existentes quedan sin foto."""
    op.add_column('usuario', sa.Column('foto_url', sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column('usuario', 'foto_url')
