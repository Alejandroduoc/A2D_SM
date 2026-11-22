"""cajas con decimales y merma en tarja

Revision ID: c4f1a7d29e30
Revises: 988c85041cdb
Create Date: 2026-11-03 23:30:00.000000

"""

# Tipos usados en las anotaciones de la cadena de Alembic.
from typing import Sequence, Union

# Operaciones que Alembic ejecuta sobre SQL Server.
from alembic import op
# Tipos de las columnas que cambian.
import sqlalchemy as sa


# Identificador de esta revisión.
revision: str = 'c4f1a7d29e30'
# Se ejecuta después de ampliar el folio.
down_revision: Union[str, None] = '988c85041cdb'
# El proyecto conserva una única rama de migraciones.
branch_labels: Union[str, Sequence[str], None] = None
# No depende de otras revisiones.
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQL Server no cambia el tipo de una columna mientras un CHECK depende de ella.
    op.drop_constraint('ck_procesos_cantidad_cajas_positiva', 'procesos', type_='check')
    # Un saldo menor que una caja debe poder entrar a un proceso: las cajas admiten decimales.
    op.alter_column(
        'procesos',  # Cabecera del proceso.
        'cantidad_cajas',  # Suma de las cajas de sus filas.
        existing_type=sa.Integer(),  # Tipo anterior.
        type_=sa.Numeric(precision=10, scale=2),  # Mismo tipo que los kilos.
        existing_nullable=False,  # Sigue siendo obligatoria.
    )  # Finaliza el cambio de la cabecera.
    # Repone la regla de la cabecera.
    op.create_check_constraint('ck_procesos_cantidad_cajas_positiva', 'procesos', 'cantidad_cajas > 0')
    # Lo mismo en el detalle.
    op.drop_constraint('ck_proceso_tarjas_cantidad_cajas_positiva', 'proceso_tarjas', type_='check')
    # Cajas de una tarja dentro del proceso.
    op.alter_column(
        'proceso_tarjas',  # Detalle del proceso.
        'cantidad_cajas',  # Cajas de esta tarja.
        existing_type=sa.Integer(),  # Tipo anterior.
        type_=sa.Numeric(precision=10, scale=2),  # Mismo tipo que los kilos.
        existing_nullable=False,  # Sigue siendo obligatoria.
    )  # Finaliza el cambio del detalle.
    # Repone la regla del detalle.
    op.create_check_constraint('ck_proceso_tarjas_cantidad_cajas_positiva', 'proceso_tarjas', 'cantidad_cajas > 0')
    # La merma pertenece a la tarja de recepción, no al proceso: también puede ser de una tarja sin procesos.
    op.add_column(
        'tarjas',  # Tarja de recepción.
        sa.Column('merma_rebajada', sa.Boolean(), server_default=sa.false(), nullable=False),  # Las tarjas existentes parten en 0.
    )  # Finaliza la columna nueva.


def downgrade() -> None:
    # Una tarja rebajada que tiene procesos conserva su cierre con la marca del modelo anterior.
    op.execute(
        "UPDATE proceso_tarjas SET tarja_terminada = 1 "
        "WHERE EXISTS (SELECT 1 FROM tarjas t WHERE t.id = proceso_tarjas.tarja_id AND t.merma_rebajada = 1) "
        "AND proceso_id = (SELECT MAX(pt.proceso_id) FROM proceso_tarjas pt "
        "JOIN procesos p ON p.id = pt.proceso_id "
        "WHERE pt.tarja_id = proceso_tarjas.tarja_id AND p.anulado = 0)"
    )
    # Una tarja rebajada sin procesos no se podía cerrar en el modelo anterior: vuelve a recepcionada.
    op.execute(
        "UPDATE tarjas SET estado = 'RECEPCIONADA' "
        "WHERE merma_rebajada = 1 AND NOT EXISTS ("
        "SELECT 1 FROM proceso_tarjas pt JOIN procesos p ON p.id = pt.proceso_id "
        "WHERE pt.tarja_id = tarjas.id AND p.anulado = 0)"
    )
    # Quita también el valor por defecto que SQL Server asoció a la columna.
    op.drop_column('tarjas', 'merma_rebajada', mssql_drop_default=True)
    # El modelo anterior solo admite cajas enteras: una fracción cuenta como una caja completa.
    op.execute("UPDATE proceso_tarjas SET cantidad_cajas = CEILING(cantidad_cajas)")
    # La cabecera vuelve a ser la suma de sus filas.
    op.execute(
        "UPDATE procesos SET cantidad_cajas = "
        "(SELECT SUM(pt.cantidad_cajas) FROM proceso_tarjas pt WHERE pt.proceso_id = procesos.id)"
    )
    # SQL Server no cambia el tipo mientras el CHECK dependa de la columna.
    op.drop_constraint('ck_proceso_tarjas_cantidad_cajas_positiva', 'proceso_tarjas', type_='check')
    # Vuelve a cajas enteras en el detalle.
    op.alter_column(
        'proceso_tarjas',  # Detalle del proceso.
        'cantidad_cajas',  # Cajas de esta tarja.
        existing_type=sa.Numeric(precision=10, scale=2),  # Tipo de esta revisión.
        type_=sa.Integer(),  # Tipo anterior.
        existing_nullable=False,  # Sigue siendo obligatoria.
    )  # Finaliza el cambio del detalle.
    # Repone la regla del detalle.
    op.create_check_constraint('ck_proceso_tarjas_cantidad_cajas_positiva', 'proceso_tarjas', 'cantidad_cajas > 0')
    # Lo mismo en la cabecera.
    op.drop_constraint('ck_procesos_cantidad_cajas_positiva', 'procesos', type_='check')
    # Vuelve a cajas enteras en la cabecera.
    op.alter_column(
        'procesos',  # Cabecera del proceso.
        'cantidad_cajas',  # Suma de las cajas de sus filas.
        existing_type=sa.Numeric(precision=10, scale=2),  # Tipo de esta revisión.
        type_=sa.Integer(),  # Tipo anterior.
        existing_nullable=False,  # Sigue siendo obligatoria.
    )  # Finaliza el cambio de la cabecera.
    # Repone la regla de la cabecera.
    op.create_check_constraint('ck_procesos_cantidad_cajas_positiva', 'procesos', 'cantidad_cajas > 0')
