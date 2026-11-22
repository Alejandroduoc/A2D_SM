"""tablas tipos de bandeja y embalajes

Revision ID: 30d78ce03230
Revises: 4b255aeb7ac0
Create Date: 2026-10-31 15:13:00.816537

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# Identificadores de revisión usados por Alembic para ordenar la migración.
revision: str = '30d78ce03230'
down_revision: Union[str, None] = '4b255aeb7ac0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Crea el catálogo de embalajes con peso fijo opcional para representar granel.
    op.create_table('embalajes',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('nombre', sa.String(length=50, collation='SQL_Latin1_General_CP1_CI_AS'), nullable=False),
    sa.Column('kg_por_caja', sa.Numeric(precision=8, scale=2), nullable=True),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.CheckConstraint('kg_por_caja IS NULL OR kg_por_caja > 0', name='ck_embalajes_kg_por_caja_positivo_o_nulo'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('nombre', name='uq_embalajes_nombre')
    )
    # Crea el catálogo de bandejas exigiendo una tara estrictamente positiva.
    op.create_table('tipos_bandeja',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('nombre', sa.String(length=50, collation='SQL_Latin1_General_CP1_CI_AS'), nullable=False),
    sa.Column('peso_tara_kg', sa.Numeric(precision=6, scale=2), nullable=False),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.CheckConstraint('peso_tara_kg > 0', name='ck_tipos_bandeja_peso_tara_kg_positivo'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('nombre', name='uq_tipos_bandeja_nombre')
    )


def downgrade() -> None:
    # Elimina primero la última tabla creada por esta revisión.
    op.drop_table('tipos_bandeja')
    # Elimina el catálogo restante sin afectar tablas de historias anteriores.
    op.drop_table('embalajes')
