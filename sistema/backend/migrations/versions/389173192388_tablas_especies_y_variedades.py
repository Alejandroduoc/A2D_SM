"""HU08 — Agrega especies y variedades con nombres únicos y estado lógico.

Cada variedad pertenece a una especie y reserva su nombre dentro de ella.

Revision ID: 389173192388
Revises: dda055fe706d
Create Date: 2026-10-24 23:33:51.862066

"""
# Tipos de los identificadores y dependencias del historial de Alembic.
from typing import Sequence, Union

# Operaciones sobre el esquema ejecutadas al aplicar o revertir la revisión.
from alembic import op
# Tipos de columna y restricciones correspondientes a los modelos de HU08.
import sqlalchemy as sa


# Identifica la revisión generada por Alembic para HU08.
revision: str = '389173192388'
# Continúa desde productores, conservando el historial existente.
down_revision: Union[str, None] = 'dda055fe706d'
# No declara una rama adicional del historial.
branch_labels: Union[str, Sequence[str], None] = None
# No requiere revisiones distintas de su antecesora.
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Crea primero especies y luego variedades sin alterar tablas anteriores."""
    # La tabla referenciada debe existir antes de crear la FK de variedades.
    op.create_table('especies',
    # SQL Server genera el identificador entero mediante IDENTITY.
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    # El nombre ignora capitalización y distingue tildes con la intercalación acordada.
    sa.Column('nombre', sa.String(length=50, collation='SQL_Latin1_General_CP1_CI_AS'), nullable=False),
    # Guarda el estado como BIT; el ORM aporta True al insertar, sin server_default.
    sa.Column('activo', sa.Boolean(), nullable=False),
    # Identifica cada especie de forma independiente de su nombre editable.
    sa.PrimaryKeyConstraint('id'),
    # Reserva el nombre incluso cuando la especie está inactiva.
    sa.UniqueConstraint('nombre', name='uq_especies_nombre')
    )
    # Cada variedad se clasifica mediante una especie obligatoria.
    op.create_table('variedades',
    # Genera una identidad propia para conservar la variedad en su historial.
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    # Coincide con el tipo entero de la PK referenciada y no admite nulos.
    sa.Column('especie_id', sa.Integer(), nullable=False),
    # Usa el mismo largo e intercalación que especies, sin unicidad global.
    sa.Column('nombre', sa.String(length=50, collation='SQL_Latin1_General_CP1_CI_AS'), nullable=False),
    # Permite desactivar conservando la clasificación y el registro.
    sa.Column('activo', sa.Boolean(), nullable=False),
    # Respalda la asociación a una especie sin configurar borrado en cascada.
    sa.ForeignKeyConstraint(['especie_id'], ['especies.id'], name='fk_variedades_especie_id'),
    # Identifica cada variedad con su id entero estable.
    sa.PrimaryKeyConstraint('id'),
    # Restringe nombres dentro de cada especie, incluidos registros inactivos.
    sa.UniqueConstraint('especie_id', 'nombre', name='uq_variedades_especie_nombre')
    )


def downgrade() -> None:
    """Retira únicamente HU08; su prueba real requiere ambas tablas vacías."""
    # Retira primero la tabla hija, junto con su FK y su restricción única.
    op.drop_table('variedades')
    # Elimina después la tabla referenciada sin tocar productores ni auditoría.
    op.drop_table('especies')
