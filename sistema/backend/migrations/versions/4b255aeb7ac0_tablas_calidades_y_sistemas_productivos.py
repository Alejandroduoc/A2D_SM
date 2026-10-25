"""tablas calidades y sistemas productivos

Revision ID: 4b255aeb7ac0
Revises: 389173192388
Create Date: 2026-10-25 02:28:09.261489

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4b255aeb7ac0'
down_revision: Union[str, None] = '389173192388'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Crea dos catálogos independientes con baja lógica mediante activo.
    op.create_table('calidades',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('nombre', sa.String(length=50, collation='SQL_Latin1_General_CP1_CI_AS'), nullable=False),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('nombre', name='uq_calidades_nombre')
    )
    # La unicidad reserva el nombre incluso cuando la calidad está inactiva.
    op.create_table('sistemas_productivos',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('nombre', sa.String(length=50, collation='SQL_Latin1_General_CP1_CI_AS'), nullable=False),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('nombre', name='uq_sistemas_productivos_nombre')
    )
    # El sistema productivo tampoco libera su nombre al desactivarse.


def downgrade() -> None:
    # Revierte únicamente los dos catálogos incorporados por esta revisión.
    op.drop_table('sistemas_productivos')
    op.drop_table('calidades')
