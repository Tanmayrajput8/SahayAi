"""add_modality_to_cases

Revision ID: c9e9710d602f
Revises: 4901647c71b7
Create Date: 2026-09-25 16:53:54.855905

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9e9710d602f'
down_revision: Union[str, Sequence[str], None] = '4901647c71b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema — add modality column to cases."""
    with op.batch_alter_table('cases', schema=None) as batch_op:
        batch_op.add_column(sa.Column('modality', sa.String(length=32), nullable=False, server_default='text'))


def downgrade() -> None:
    """Downgrade schema — drop modality column from cases."""
    with op.batch_alter_table('cases', schema=None) as batch_op:
        batch_op.drop_column('modality')
