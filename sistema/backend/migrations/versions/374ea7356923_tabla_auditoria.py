"""HU21 — Incorpora la tabla de auditoría al inicio de E2.

Prepara el historial de cambios de productores que utilizará HU07.

Revision ID: 374ea7356923
Revises: 5e84fd3d65d7
Create Date: 2026-10-24 14:43:28.925041

"""
# Tipos para las anotaciones de los identificadores del historial.
from typing import Sequence, Union

# Operaciones que Alembic ejecuta para modificar el esquema.
from alembic import op
# Tipos y restricciones usados al crear las columnas y la tabla.
import sqlalchemy as sa


# Identifica esta migración dentro del historial de Alembic.
revision: str = '374ea7356923'
# Enlaza esta migración con la última revisión de E1.
down_revision: Union[str, None] = '5e84fd3d65d7'
# Esta revisión no declara etiquetas de rama.
branch_labels: Union[str, Sequence[str], None] = None
# No requiere revisiones adicionales fuera de su antecesora.
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Crea la tabla de auditoría y los índices de consulta del historial."""
    # Crea únicamente la tabla nueva, sin modificar las tablas de E1.
    op.create_table('auditoria',
    # Identificador de auditoría BIGINT, generado por SQL Server con IDENTITY.
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    # UUID del usuario responsable, con el mismo tipo que usuarios.id.
    sa.Column('usuario_id', sa.String(length=36), nullable=False),
    # Nombre de la tabla de negocio afectada.
    sa.Column('tabla', sa.String(length=50), nullable=False),
    # Identificador del registro afectado, almacenado como texto.
    sa.Column('registro_id', sa.String(length=36), nullable=False),
    # Acción del evento; la desactivación de un productor se registra como UPDATE.
    sa.Column('accion', sa.Enum('INSERT', 'UPDATE', 'DELETE', name='accionauditoria', length=10), nullable=False),
    # JSON anterior en texto Unicode extenso; puede ser nulo en una creación.
    sa.Column('valores_antes', sa.UnicodeText(), nullable=True),
    # JSON posterior en texto Unicode extenso; admite ausencia de estado posterior.
    sa.Column('valores_despues', sa.UnicodeText(), nullable=True),
    # Justificación opcional que podrá exigir el servicio de negocio.
    sa.Column('motivo', sa.String(length=255), nullable=True),
    # Fecha obligatoria; el ORM proporciona el valor calculado en UTC.
    sa.Column('fecha_hora', sa.DateTime(), nullable=False),
    # Vincula el evento con un usuario existente, sin borrado en cascada.
    sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ),
    # Garantiza que cada evento tenga un identificador único.
    sa.PrimaryKeyConstraint('id')
    )
    # Facilita las búsquedas de eventos por fecha y hora.
    op.create_index(op.f('ix_auditoria_fecha_hora'), 'auditoria', ['fecha_hora'], unique=False)
    # Facilita las búsquedas de eventos por tabla afectada.
    op.create_index(op.f('ix_auditoria_tabla'), 'auditoria', ['tabla'], unique=False)
    # Facilita las búsquedas de eventos por usuario responsable.
    op.create_index(op.f('ix_auditoria_usuario_id'), 'auditoria', ['usuario_id'], unique=False)


def downgrade() -> None:
    """Revierte los índices y la tabla en orden inverso al de su creación."""
    # Retira primero el último índice creado, correspondiente al usuario.
    op.drop_index(op.f('ix_auditoria_usuario_id'), table_name='auditoria')
    # Retira el índice de la tabla afectada.
    op.drop_index(op.f('ix_auditoria_tabla'), table_name='auditoria')
    # Retira el índice de fecha antes de eliminar la tabla.
    op.drop_index(op.f('ix_auditoria_fecha_hora'), table_name='auditoria')
    # Elimina la tabla y su contenido; la prueba debe hacerse con la tabla vacía.
    op.drop_table('auditoria')
