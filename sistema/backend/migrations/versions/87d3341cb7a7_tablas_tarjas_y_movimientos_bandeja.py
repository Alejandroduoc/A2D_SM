"""tablas tarjas y movimientos bandeja

Revision ID: 87d3341cb7a7
Revises: e650ab5e4bce
Create Date: 2026-11-01 19:17:39.792327

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '87d3341cb7a7'
down_revision: Union[str, None] = 'e650ab5e4bce'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # La numeracion se consume aunque una transaccion se revierta, para no repetirla.
    op.execute(
        "CREATE SEQUENCE seq_numero_tarja "
        "AS INT START WITH 1 INCREMENT BY 1"
    )

    # Crea primero tarjas porque los movimientos dependen de su clave foránea.
    op.create_table('tarjas',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('numero_tarja', sa.Integer(), nullable=False),
    sa.Column('productor_id', sa.Integer(), nullable=False),
    sa.Column('usuario_id', sa.String(length=36), nullable=False),
    sa.Column('sistema_productivo_id', sa.Integer(), nullable=False),
    sa.Column('variedad_id', sa.Integer(), nullable=False),
    sa.Column('calidad_id', sa.Integer(), nullable=False),
    sa.Column('tipo_bandeja_id', sa.Integer(), nullable=False),
    sa.Column('cantidad_bandejas', sa.Integer(), nullable=False),
    sa.Column('tara_kg', sa.Numeric(precision=6, scale=2), nullable=False),
    sa.Column('peso_pallet_kg', sa.Numeric(precision=8, scale=2), nullable=False),
    sa.Column('kilos_brutos', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('kilos_netos', sa.Integer(), nullable=False),
    sa.Column('porcentaje_calidad', sa.SmallInteger(), nullable=False),
    sa.Column('fecha_recepcion', sa.Date(), nullable=False),
    sa.Column('estado', sa.Enum('RECEPCIONADA', 'PARCIAL', 'PROCESADA', 'ANULADA', name='estadotarja', length=20), nullable=False),
    sa.Column('fecha_hora', sa.DateTime(), nullable=False),
    sa.Column('veces_impresa', sa.Integer(), nullable=False),
    sa.Column('impresa_en', sa.DateTime(), nullable=True),
    sa.CheckConstraint('cantidad_bandejas > 0', name='ck_tarjas_cantidad_bandejas_positiva'),
    sa.CheckConstraint('kilos_brutos > 0', name='ck_tarjas_kilos_brutos_positivos'),
    sa.CheckConstraint('kilos_netos > 0', name='ck_tarjas_kilos_netos_positivos'),
    sa.CheckConstraint('peso_pallet_kg >= 0', name='ck_tarjas_peso_pallet_kg_no_negativo'),
    sa.CheckConstraint('porcentaje_calidad BETWEEN 0 AND 100', name='ck_tarjas_porcentaje_calidad_rango'),
    sa.CheckConstraint('tara_kg > 0', name='ck_tarjas_tara_kg_positiva'),
    sa.CheckConstraint('veces_impresa >= 0', name='ck_tarjas_veces_impresa_no_negativa'),
    sa.ForeignKeyConstraint(['calidad_id'], ['calidades.id'], ),
    sa.ForeignKeyConstraint(['productor_id'], ['productores.id'], ),
    sa.ForeignKeyConstraint(['sistema_productivo_id'], ['sistemas_productivos.id'], ),
    sa.ForeignKeyConstraint(['tipo_bandeja_id'], ['tipos_bandeja.id'], ),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ),
    sa.ForeignKeyConstraint(['variedad_id'], ['variedades.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('numero_tarja')
    )
    op.create_index(op.f('ix_tarjas_productor_id'), 'tarjas', ['productor_id'], unique=False)
    op.create_table('movimientos_bandeja',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('productor_id', sa.Integer(), nullable=False),
    sa.Column('tipo_bandeja_id', sa.Integer(), nullable=False),
    sa.Column('tarja_id', sa.Integer(), nullable=True),
    sa.Column('tipo', sa.Enum('ENTRADA', 'SALIDA', name='tipomovimientobandeja', length=10), nullable=False),
    sa.Column('cantidad', sa.Integer(), nullable=False),
    sa.Column('anulado', sa.Boolean(), nullable=False),
    sa.Column('fecha_hora', sa.DateTime(), nullable=False),
    sa.CheckConstraint('cantidad > 0', name='ck_movimientos_bandeja_cantidad_positiva'),
    sa.ForeignKeyConstraint(['productor_id'], ['productores.id'], ),
    sa.ForeignKeyConstraint(['tarja_id'], ['tarjas.id'], ),
    sa.ForeignKeyConstraint(['tipo_bandeja_id'], ['tipos_bandeja.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_movimientos_bandeja_productor_id'), 'movimientos_bandeja', ['productor_id'], unique=False)


def downgrade() -> None:
    # Elimina primero los movimientos para respetar su clave foránea a tarjas.
    op.drop_index(op.f('ix_movimientos_bandeja_productor_id'), table_name='movimientos_bandeja')
    op.drop_table('movimientos_bandeja')
    op.drop_index(op.f('ix_tarjas_productor_id'), table_name='tarjas')
    op.drop_table('tarjas')

    # Se elimina al final, cuando ninguna tabla puede depender de la secuencia.
    op.execute("DROP SEQUENCE seq_numero_tarja")
