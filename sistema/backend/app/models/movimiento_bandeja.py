"""Movimientos de bandejas asociados a productores y tarjas."""

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


# Distingue las bandejas recibidas de las entregadas al productor.
class TipoMovimientoBandeja(str, enum.Enum):
    ENTRADA = "ENTRADA"
    SALIDA = "SALIDA"


# Registra cada variación del saldo de bandejas sin borrado físico.
class MovimientoBandeja(Base):
    __tablename__ = "movimientos_bandeja"
    __table_args__ = (
        CheckConstraint(
            "cantidad > 0",
            name="ck_movimientos_bandeja_cantidad_positiva",
        ),
    )

    # Identidad del movimiento y productor cuyo saldo cambia.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    productor_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("productores.id"),
        index=True,
        nullable=False,
    )
    # Tipo de bandeja afectado y tarja de origen cuando corresponde.
    tipo_bandeja_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tipos_bandeja.id"),
        nullable=False,
    )
    tarja_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("tarjas.id"),
        nullable=True,
    )
    # Sentido y cantidad del movimiento; una anulación conserva la fila.
    tipo: Mapped[TipoMovimientoBandeja] = mapped_column(
        Enum(TipoMovimientoBandeja, length=10),
        nullable=False,
    )
    cantidad: Mapped[int] = mapped_column(Integer, nullable=False)
    anulado: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Instante UTC en que se registró el movimiento.
    fecha_hora: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
