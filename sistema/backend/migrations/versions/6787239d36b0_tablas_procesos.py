"""tablas procesos

Revision ID: 6787239d36b0
Revises: 87d3341cb7a7
Create Date: 2026-11-03 22:19:05.349095

"""

# Tipos usados por las anotaciones de la revisión de Alembic.
from typing import Sequence, Union

# Operaciones DDL que Alembic ejecutará sobre SQL Server.
from alembic import op
# Tipos de columnas y restricciones que se materializan en la base.
import sqlalchemy as sa


# Identificador inmutable de esta nueva migración de HU18.
revision: str = '6787239d36b0'
# Declara que las tablas de E3 son el estado inmediatamente anterior.
down_revision: Union[str, None] = '87d3341cb7a7'
# El proyecto mantiene una sola línea principal de migraciones.
branch_labels: Union[str, Sequence[str], None] = None
# Esta migración no depende de revisiones ajenas a la cadena principal.
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # La secuencia entrega un número único aun cuando dos operadores guarden a la vez.
    op.execute(
        "CREATE SEQUENCE seq_numero_proceso "
        "AS INT START WITH 1 INCREMENT BY 1"
    )
    # Crea la cabecera antes del detalle que la referencia mediante clave foránea.
    op.create_table(
        'procesos',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),  # Identidad interna.
        sa.Column('folio', sa.String(length=10), nullable=False),  # Folio P más correlativo.
        sa.Column('usuario_id', sa.String(length=36), nullable=False),  # Usuario que registró.
        sa.Column('embalaje_id', sa.Integer(), nullable=False),  # Embalaje aplicado al proceso.
        sa.Column('fecha_elaboracion', sa.Date(), nullable=False),  # Día declarado de elaboración.
        sa.Column('fecha_hora', sa.DateTime(), nullable=False),  # Registro UTC del sistema.
        sa.Column('cantidad_cajas', sa.Integer(), nullable=False),  # Suma calculada del detalle.
        sa.Column('kilos_salida', sa.Numeric(precision=10, scale=2), nullable=False),  # Salida calculada.
        sa.Column('anulado', sa.Boolean(), nullable=False),  # Marca lógica de HU25.
        sa.CheckConstraint('cantidad_cajas > 0', name='ck_procesos_cantidad_cajas_positiva'),  # Total válido.
        sa.CheckConstraint('kilos_salida > 0', name='ck_procesos_kilos_salida_positivos'),  # Peso válido.
        sa.ForeignKeyConstraint(['embalaje_id'], ['embalajes.id']),  # Requiere embalaje existente.
        sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id']),  # Requiere usuario existente.
        sa.PrimaryKeyConstraint('id'),  # Clave interna de la cabecera.
        sa.UniqueConstraint('folio', name='uq_procesos_folio'),  # Un folio de proceso no se repite.
    )
    # Acelera la consulta de procesos registrados con un embalaje determinado.
    op.create_index(op.f('ix_procesos_embalaje_id'), 'procesos', ['embalaje_id'], unique=False)
    # Acelera filtros posteriores por el usuario que registró el proceso.
    op.create_index(op.f('ix_procesos_usuario_id'), 'procesos', ['usuario_id'], unique=False)
    # Crea el detalle después de disponer de las cabeceras y tarjas referenciadas.
    op.create_table(
        'proceso_tarjas',
        sa.Column('proceso_id', sa.Integer(), nullable=False),  # Proceso al que pertenece la fila.
        sa.Column('tarja_id', sa.Integer(), nullable=False),  # Tarja de recepción consumida.
        sa.Column('cantidad_cajas', sa.Integer(), nullable=False),  # Cajas de esta tarja.
        sa.Column('kilos_procesados', sa.Numeric(precision=10, scale=2), nullable=False),  # Kilos de esta fila.
        sa.Column('tarja_terminada', sa.Boolean(), nullable=False),  # Marca de término en este proceso.
        sa.CheckConstraint('cantidad_cajas > 0', name='ck_proceso_tarjas_cantidad_cajas_positiva'),  # Cajas válidas.
        sa.CheckConstraint('kilos_procesados > 0', name='ck_proceso_tarjas_kilos_procesados_positivos'),  # Peso válido.
        sa.ForeignKeyConstraint(['proceso_id'], ['procesos.id']),  # Requiere cabecera existente.
        sa.ForeignKeyConstraint(['tarja_id'], ['tarjas.id']),  # Requiere tarja existente.
        sa.PrimaryKeyConstraint('proceso_id', 'tarja_id'),  # Impide repetir una tarja en el mismo proceso.
    )
    # Acelera el saldo, trazabilidad y recálculo de estado desde una tarja.
    op.create_index(op.f('ix_proceso_tarjas_tarja_id'), 'proceso_tarjas', ['tarja_id'], unique=False)


def downgrade() -> None:
    # Elimina primero el índice que depende de la tabla de detalle.
    op.drop_index(op.f('ix_proceso_tarjas_tarja_id'), table_name='proceso_tarjas')
    # Elimina el detalle antes de la cabecera para respetar su clave foránea.
    op.drop_table('proceso_tarjas')
    # Elimina el índice asociado al usuario de la cabecera.
    op.drop_index(op.f('ix_procesos_usuario_id'), table_name='procesos')
    # Elimina el índice asociado al embalaje de la cabecera.
    op.drop_index(op.f('ix_procesos_embalaje_id'), table_name='procesos')
    # Elimina la cabecera cuando ya no tiene filas dependientes.
    op.drop_table('procesos')
    # Elimina al final la secuencia exclusiva de E4.
    op.execute("DROP SEQUENCE seq_numero_proceso")
