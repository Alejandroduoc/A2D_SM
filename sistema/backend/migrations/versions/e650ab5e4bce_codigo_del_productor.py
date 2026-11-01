"""codigo del productor

Revision ID: e650ab5e4bce
Revises: 30d78ce03230
Create Date: 2026-11-01 18:31:44.435289

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e650ab5e4bce'
down_revision: Union[str, None] = '30d78ce03230'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # La secuencia mantiene el correlativo independiente del id interno.
    op.execute(
        "CREATE SEQUENCE seq_codigo_productor "
        "AS INT START WITH 1 INCREMENT BY 1"
    )

    # Primero admite nulos para poder actualizar los registros existentes.
    op.add_column(
        "productores",
        sa.Column("codigo", sa.Integer(), nullable=True),
    )
    op.execute(
        "UPDATE productores "
        "SET codigo = NEXT VALUE FOR seq_codigo_productor"
    )

    # Después del relleno, el código queda obligatorio y único.
    op.alter_column(
        "productores",
        "codigo",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.create_unique_constraint(
        "uq_productores_codigo",
        "productores",
        ["codigo"],
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
        "uq_productores_codigo",
        "productores",
        type_="unique",
    )
    op.drop_column("productores", "codigo")
    op.execute("DROP SEQUENCE seq_codigo_productor")
