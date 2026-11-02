"""tablas tarjas y movimientos bandeja

Revision ID: 87d3341cb7a7
Revises: e650ab5e4bce
Create Date: 2026-11-01 19:17:39.792327

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '87d3341cb7a7'  # Identificador de esta migración.
down_revision: Union[str, None] = 'e650ab5e4bce'  # Migración anterior: código del productor.
branch_labels: Union[str, Sequence[str], None] = None  # Sin ramas de migraciones.
depends_on: Union[str, Sequence[str], None] = None  # Sin dependencias adicionales.


def upgrade() -> None:
    # La numeracion se consume aunque una transaccion se revierta, para no repetirla.
    op.execute(
        "CREATE SEQUENCE seq_numero_tarja "
        "AS INT START WITH 1 INCREMENT BY 1"
    )

    # Crea primero tarjas porque los movimientos dependen de su clave foránea.
    op.create_table('tarjas',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),  # Identidad interna de la tarja.
    sa.Column('numero_tarja', sa.Integer(), nullable=False),  # Número que asigna el service con la secuencia (HU13).
    sa.Column('productor_id', sa.Integer(), nullable=False),  # Productor que entrega la fruta.
    sa.Column('usuario_id', sa.String(length=36), nullable=False),  # Usuario que registró la tarja.
    sa.Column('sistema_productivo_id', sa.Integer(), nullable=False),  # Sistema productivo elegido.
    sa.Column('variedad_id', sa.Integer(), nullable=False),  # Variedad elegida; la especie sale de ella.
    sa.Column('calidad_id', sa.Integer(), nullable=False),  # Calidad elegida.
    sa.Column('tipo_bandeja_id', sa.Integer(), nullable=False),  # Tipo de bandeja elegido.
    sa.Column('cantidad_bandejas', sa.Integer(), nullable=False),  # Bandejas recibidas.
    sa.Column('tara_kg', sa.Numeric(precision=6, scale=2), nullable=False),  # Copia de la tara al registrar (HU14 criterio 4).
    sa.Column('peso_pallet_kg', sa.Numeric(precision=8, scale=2), nullable=False),  # Peso del pallet.
    sa.Column('kilos_brutos', sa.Numeric(precision=10, scale=2), nullable=False),  # Peso de balanza.
    sa.Column('kilos_netos', sa.Integer(), nullable=False),  # Calculado por el service, entero.
    sa.Column('porcentaje_calidad', sa.SmallInteger(), nullable=False),  # Calidad visual (decisión B).
    sa.Column('fecha_recepcion', sa.Date(), nullable=False),  # Día de llegada de la fruta (decisión C).
    sa.Column('estado', sa.Enum('RECEPCIONADA', 'PARCIAL', 'PROCESADA', 'ANULADA', name='estadotarja', length=20), nullable=False),  # Estado del flujo de la tarja.
    sa.Column('fecha_hora', sa.DateTime(), nullable=False),  # Registro en UTC, no editable.
    sa.Column('veces_impresa', sa.Integer(), nullable=False),  # Contador de impresiones (HU16).
    sa.Column('impresa_en', sa.DateTime(), nullable=True),  # Última impresión (HU16).
    sa.CheckConstraint('cantidad_bandejas > 0', name='ck_tarjas_cantidad_bandejas_positiva'),  # Al menos una bandeja.
    sa.CheckConstraint('kilos_brutos > 0', name='ck_tarjas_kilos_brutos_positivos'),  # La balanza siempre es positiva.
    sa.CheckConstraint('kilos_netos > 0', name='ck_tarjas_kilos_netos_positivos'),  # HU14 criterio 2.
    sa.CheckConstraint('peso_pallet_kg >= 0', name='ck_tarjas_peso_pallet_kg_no_negativo'),  # Puede llegar sin pallet.
    sa.CheckConstraint('porcentaje_calidad BETWEEN 0 AND 100', name='ck_tarjas_porcentaje_calidad_rango'),  # Decisión B.
    sa.CheckConstraint('tara_kg > 0', name='ck_tarjas_tara_kg_positiva'),  # Misma regla del catálogo.
    sa.CheckConstraint('veces_impresa >= 0', name='ck_tarjas_veces_impresa_no_negativa'),  # Contador no negativo.
    sa.ForeignKeyConstraint(['calidad_id'], ['calidades.id'], ),  # Debe existir en el catálogo.
    sa.ForeignKeyConstraint(['productor_id'], ['productores.id'], ),  # Debe ser un productor existente.
    sa.ForeignKeyConstraint(['sistema_productivo_id'], ['sistemas_productivos.id'], ),  # Debe existir en el catálogo.
    sa.ForeignKeyConstraint(['tipo_bandeja_id'], ['tipos_bandeja.id'], ),  # Debe existir en el catálogo.
    sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ),  # Debe ser un usuario existente.
    sa.ForeignKeyConstraint(['variedad_id'], ['variedades.id'], ),  # Debe existir en el catálogo.
    sa.PrimaryKeyConstraint('id'),  # Clave primaria de tarjas.
    sa.UniqueConstraint('numero_tarja')  # Un número de tarja no se repite (HU13).
    )
    op.create_index(op.f('ix_tarjas_productor_id'), 'tarjas', ['productor_id'], unique=False)  # Prepara los acumulados por productor.
    op.create_table('movimientos_bandeja',  # Entradas y salidas de bandejas por productor.
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),  # Identidad interna del movimiento.
    sa.Column('productor_id', sa.Integer(), nullable=False),  # Productor cuyo saldo cambia.
    sa.Column('tipo_bandeja_id', sa.Integer(), nullable=False),  # Tipo de bandeja afectado.
    sa.Column('tarja_id', sa.Integer(), nullable=True),  # Tarja de origen; nulo en las salidas.
    sa.Column('tipo', sa.Enum('ENTRADA', 'SALIDA', name='tipomovimientobandeja', length=10), nullable=False),  # ENTRADA o SALIDA.
    sa.Column('cantidad', sa.Integer(), nullable=False),  # Bandejas del movimiento.
    sa.Column('anulado', sa.Boolean(), nullable=False),  # 1 = su tarja se anuló y no suma al saldo.
    sa.Column('fecha_hora', sa.DateTime(), nullable=False),  # Momento del movimiento en UTC.
    sa.CheckConstraint('cantidad > 0', name='ck_movimientos_bandeja_cantidad_positiva'),  # Al menos una bandeja.
    sa.ForeignKeyConstraint(['productor_id'], ['productores.id'], ),  # Debe ser un productor existente.
    sa.ForeignKeyConstraint(['tarja_id'], ['tarjas.id'], ),  # Debe ser una tarja existente.
    sa.ForeignKeyConstraint(['tipo_bandeja_id'], ['tipos_bandeja.id'], ),  # Debe existir en el catálogo.
    sa.PrimaryKeyConstraint('id')  # Clave primaria de movimientos.
    )
    op.create_index(op.f('ix_movimientos_bandeja_productor_id'), 'movimientos_bandeja', ['productor_id'], unique=False)  # Prepara el saldo por productor (HU15).


def downgrade() -> None:
    # Elimina primero los movimientos para respetar su clave foránea a tarjas.
    op.drop_index(op.f('ix_movimientos_bandeja_productor_id'), table_name='movimientos_bandeja')  # Primero el índice.
    op.drop_table('movimientos_bandeja')  # Después la tabla que depende de tarjas.
    op.drop_index(op.f('ix_tarjas_productor_id'), table_name='tarjas')  # Índice de tarjas.
    op.drop_table('tarjas')  # Tabla de tarjas.

    # Se elimina al final, cuando ninguna tabla puede depender de la secuencia.
    op.execute("DROP SEQUENCE seq_numero_tarja")
