"""renombrar rol supervisor a gerencia

Revision ID: 5e84fd3d65d7
Revises: 4e5b5d399259
Create Date: 2026-10-03 19:18:09.037209

Decisión del equipo (2026-10-03): el rol intermedio se llama "gerencia", como
en los documentos de Fase 1 y 2. Solo cambian datos, no la estructura:
usuario_roles.rol es VARCHAR(18) sin restricción CHECK, así que "GERENCIA"
cabe sin modificar la columna. La migración inicial no se toca porque ya
está aplicada en las bases del equipo.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '5e84fd3d65d7'
down_revision: Union[str, None] = '4e5b5d399259'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLAlchemy guarda el NOMBRE del enum (RolUsuario.GERENCIA → "GERENCIA"),
    # no su valor ("gerencia"). Se renombran las filas que ya existían.
    op.execute("UPDATE usuario_roles SET rol = 'GERENCIA' WHERE rol = 'SUPERVISOR'")


def downgrade() -> None:
    # Deshace el cambio de datos para volver al nombre anterior.
    op.execute("UPDATE usuario_roles SET rol = 'SUPERVISOR' WHERE rol = 'GERENCIA'")
