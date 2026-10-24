"""HU07 — Incorpora el mantenimiento de productores con RUT único normalizado.

El estado permite desactivar productores conservando su identidad e historial.

Revision ID: dda055fe706d
Revises: 374ea7356923
Create Date: 2026-10-24 16:30:07.599367

"""
# Tipos para anotar los identificadores y las dependencias del historial.
from typing import Sequence, Union

# Operaciones que Alembic ejecuta sobre el esquema de la base de datos.
from alembic import op
# Tipos de columna y restricciones de la tabla de productores.
import sqlalchemy as sa


# Identifica esta migración de HU07 dentro del historial de Alembic.
revision: str = 'dda055fe706d'
# Continúa desde la migración de auditoría, que debe conservarse.
down_revision: Union[str, None] = '374ea7356923'
# Esta revisión no declara etiquetas de rama.
branch_labels: Union[str, Sequence[str], None] = None
# No requiere otras revisiones además de su antecesora.
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Crea productores y su índice único de RUT sin modificar tablas previas."""
    # Agrega únicamente las seis columnas previstas en el diseño de HU07.
    op.create_table('productores',
    # SQL Server genera el identificador entero mediante IDENTITY.
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    # Conserva el RUT validado y normalizado por la aplicación.
    sa.Column('rut', sa.String(length=12), nullable=False),
    # Exige una razón social de hasta 150 caracteres.
    sa.Column('razon_social', sa.String(length=150), nullable=False),
    # Permite omitir la dirección de contacto.
    sa.Column('direccion', sa.String(length=200), nullable=True),
    # Permite omitir el teléfono de contacto.
    sa.Column('telefono', sa.String(length=20), nullable=True),
    # Almacena el estado como BIT; el ORM proporciona True al crear un productor.
    sa.Column('activo', sa.Boolean(), nullable=False),
    # Identifica cada productor sin depender de su RUT editable.
    sa.PrimaryKeyConstraint('id')
    )
    # Respalda la unicidad del RUT normalizado incluso ante operaciones simultáneas.
    op.create_index(op.f('ix_productores_rut'), 'productores', ['rut'], unique=True)


def downgrade() -> None:
    """Revierte solo productores; la prueba requiere que la tabla esté vacía."""
    # Retira el índice antes de eliminar la tabla a la que pertenece.
    op.drop_index(op.f('ix_productores_rut'), table_name='productores')
    # Elimina productores sin modificar auditoría, usuarios ni roles.
    op.drop_table('productores')
