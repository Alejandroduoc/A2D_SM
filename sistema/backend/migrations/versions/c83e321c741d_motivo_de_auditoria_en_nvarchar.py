"""motivo de auditoria en nvarchar

Revision ID: c83e321c741d
Revises: c4f1a7d29e30
Create Date: 2026-11-08 16:22:18.896723

"""

# Tipos usados en las anotaciones de la cadena de Alembic.
from typing import Sequence, Union

# Operaciones que Alembic ejecuta sobre SQL Server.
from alembic import op
# Tipos de la columna que cambia.
import sqlalchemy as sa


# Identificador de esta revisión.
revision: str = 'c83e321c741d'
# Se ejecuta después de las cajas con decimales y la merma en la tarja.
down_revision: Union[str, None] = 'c4f1a7d29e30'
# El proyecto conserva una única rama de migraciones.
branch_labels: Union[str, Sequence[str], None] = None
# No depende de otras revisiones.
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # HU20 es el primer motivo que escribe una persona: VARCHAR Latin1 cambiaba "→" por "->" y "✓" por "?".
    op.alter_column(
        'auditoria',  # Tabla de la bitácora (HU21).
        'motivo',  # Justificación del evento.
        existing_type=sa.String(length=255),  # VARCHAR(255) anterior.
        type_=sa.Unicode(length=255),  # NVARCHAR(255): guarda cualquier carácter.
        existing_nullable=True,  # Sigue siendo opcional; el negocio exige el motivo cuando corresponde.
    )  # Finaliza el cambio de tipo.


def downgrade() -> None:
    # Ojo: al bajar, SQL Server cambia por "?" los caracteres que no existen en Latin1 (emojis, flechas, ✓).
    # Las tildes y la ñ sí se conservan, porque existen en Windows-1252.
    op.alter_column(
        'auditoria',  # Tabla de la bitácora (HU21).
        'motivo',  # Justificación del evento.
        existing_type=sa.Unicode(length=255),  # NVARCHAR(255) de esta revisión.
        type_=sa.String(length=255),  # Vuelve a VARCHAR(255).
        existing_nullable=True,  # Sigue siendo opcional.
    )  # Finaliza el cambio de tipo.
