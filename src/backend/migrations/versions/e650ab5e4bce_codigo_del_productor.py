"""codigo del productor

Revision ID: e650ab5e4bce
Revises: 30d78ce03230
Create Date: 2026-11-01 18:31:44.435289

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e650ab5e4bce'  # Identificador de esta migración.
down_revision: Union[str, None] = '30d78ce03230'  # Migración anterior: tipos de bandeja y embalajes (HU10).
branch_labels: Union[str, Sequence[str], None] = None  # Sin ramas de migraciones.
depends_on: Union[str, Sequence[str], None] = None  # Sin dependencias adicionales.


def upgrade() -> None:
    # La secuencia mantiene el correlativo independiente del id interno.
    op.execute(
        "CREATE SEQUENCE seq_codigo_productor "
        "AS INT START WITH 1 INCREMENT BY 1"
    )

    # Primero admite nulos para poder actualizar los registros existentes.
    op.add_column(
        "productores",  # Tabla del catálogo de productores.
        sa.Column("codigo", sa.Integer(), nullable=True),  # Nullable: las filas existentes aún no tienen código.
    )
    op.execute(
        "UPDATE productores "
        "SET codigo = NEXT VALUE FOR seq_codigo_productor"
    )

    # Después del relleno, el código queda obligatorio y único.
    op.alter_column(
        "productores",  # Tabla del catálogo de productores.
        "codigo",  # Columna del código.
        existing_type=sa.Integer(),  # Alembic necesita el tipo actual en SQL Server.
        nullable=False,  # Desde aquí todo productor debe tener código.
    )
    op.create_unique_constraint(
        "uq_productores_codigo",  # Nombre explícito para poder quitarla en el downgrade.
        "productores",  # Tabla del catálogo de productores.
        ["codigo"],  # Dos productores no pueden compartir código.
    )

    # Las altas futuras reciben el siguiente valor directamente en SQL Server.
    op.execute(
        "ALTER TABLE productores ADD CONSTRAINT df_productores_codigo "
        "DEFAULT (NEXT VALUE FOR seq_codigo_productor) FOR codigo"
    )


def downgrade() -> None:
    # Revierte las dependencias en orden antes de eliminar la secuencia.
    op.execute(
        "ALTER TABLE productores DROP CONSTRAINT df_productores_codigo"
    )
    op.drop_constraint(
        "uq_productores_codigo",  # Nombre explícito para poder quitarla en el downgrade.
        "productores",  # Tabla del catálogo de productores.
        type_="unique",  # Indica que es una restricción única.
    )
    op.drop_column("productores", "codigo")
    op.execute("DROP SEQUENCE seq_codigo_productor")
