"""ampliar folio proceso

Revision ID: 988c85041cdb
Revises: 6787239d36b0
Create Date: 2026-11-03 22:24:58.186846

"""

# Tipos usados en las anotaciones de la cadena de Alembic.
from typing import Sequence, Union

# Expone las operaciones de cambio de esquema para SQL Server.
from alembic import op
# Representa los tipos de columna antes y después de la ampliación.
import sqlalchemy as sa


# Identificador inmutable de la corrección técnica del folio.
revision: str = '988c85041cdb'
# Esta corrección se ejecuta después de crear las tablas de procesos.
down_revision: Union[str, None] = '6787239d36b0'
# El proyecto conserva una única rama de migraciones.
branch_labels: Union[str, Sequence[str], None] = None
# No existen dependencias adicionales fuera de la revisión previa.
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Amplía el folio para conservar P más los diez dígitos posibles de un INT.
    op.alter_column(
        'procesos',  # Tabla que conserva las cabeceras de E4.
        'folio',  # Columna única generada desde seq_numero_proceso.
        existing_type=sa.VARCHAR(length=10, collation='SQL_Latin1_General_CP1_CI_AS'),  # Tipo original.
        type_=sa.String(length=11),  # Nuevo tamaño técnico sin máximo operativo artificial.
        existing_nullable=False,  # El folio sigue siendo obligatorio.
    )


def downgrade() -> None:
    # SQL Server no reduce el largo mientras la unicidad depende de la columna.
    op.drop_constraint(
        'uq_procesos_folio',  # Restricción única creada en la migración anterior.
        'procesos',  # Tabla que contiene el folio.
        type_='unique',  # Indica que se elimina una restricción UNIQUE.
    )
    # Restaura el tamaño previo si se vuelve al estado original de la revisión.
    op.alter_column(
        'procesos',  # Tabla que se revierte.
        'folio',  # Columna que vuelve a su longitud anterior.
        existing_type=sa.String(length=11),  # Tipo de esta revisión.
        type_=sa.VARCHAR(length=10, collation='SQL_Latin1_General_CP1_CI_AS'),  # Tipo previo.
        existing_nullable=False,  # El folio continúa siendo obligatorio.
    )
    # Restaura la misma unicidad que existía antes de ampliar la columna.
    op.create_unique_constraint(
        'uq_procesos_folio',  # Nombre estable usado por las dos revisiones.
        'procesos',  # Tabla que recupera la restricción.
        ['folio'],  # El folio debe seguir sin repetirse.
    )
