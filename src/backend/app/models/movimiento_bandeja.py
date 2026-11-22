"""Movimientos de bandejas asociados a productores y tarjas."""

# Base de los tipos de movimiento.
import enum
# Momento UTC del registro.
from datetime import datetime, timezone

# Tipos de columna y restricciones de la tabla.
from sqlalchemy import (
    Boolean,  # Marca de anulación.
    CheckConstraint,  # Regla que SQL Server comprueba en cada fila.
    DateTime,  # Fecha con hora.
    Enum,  # Tipo de movimiento guardado como texto.
    ForeignKey,  # Relación con otra tabla.
    Integer,  # Identidades y cantidades.
)  # Finaliza las importaciones de SQLAlchemy.
# Declaran atributos tipados con el estilo SQLAlchemy 2 del proyecto.
from sqlalchemy.orm import Mapped, mapped_column

# Registra el modelo en el mismo conjunto de tablas de la aplicación.
from app.core.database import Base


# Distingue las bandejas recibidas de las entregadas al productor.
class TipoMovimientoBandeja(str, enum.Enum):
    ENTRADA = "ENTRADA"  # Bandejas que llegan con una tarja.
    SALIDA = "SALIDA"  # Devoluciones al productor; llegan con la guía, después del PMV.


# Registra cada variación del saldo de bandejas sin borrado físico.
class MovimientoBandeja(Base):
    # Nombre de la tabla en SQL Server.
    __tablename__ = "movimientos_bandeja"
    # Regla que la base garantiza aunque falle la validación de la API.
    __table_args__ = (
        # Todo movimiento mueve al menos una bandeja.
        CheckConstraint(
            "cantidad > 0",
            name="ck_movimientos_bandeja_cantidad_positiva",
        ),
    )  # Finaliza las restricciones de la tabla.

    # Identidad interna generada por la base.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Productor cuyo saldo cambia.
    productor_id: Mapped[int] = mapped_column(
        Integer,  # Mismo tipo que productores.id.
        ForeignKey("productores.id"),  # Debe ser un productor existente.
        index=True,  # Prepara la consulta del saldo por productor (HU15).
        nullable=False,  # Dato obligatorio.
    )  # Finaliza la declaración del productor.
    # Tipo de bandeja afectado.
    tipo_bandeja_id: Mapped[int] = mapped_column(
        Integer,  # Mismo tipo que el catálogo.
        ForeignKey("tipos_bandeja.id"),  # Debe existir en el catálogo.
        nullable=False,  # Dato obligatorio.
    )  # Finaliza la declaración del tipo de bandeja.
    # Tarja que originó la entrada; las salidas no tienen tarja.
    tarja_id: Mapped[int | None] = mapped_column(
        Integer,  # Mismo tipo que tarjas.id.
        ForeignKey("tarjas.id"),  # Debe ser una tarja existente.
        nullable=True,  # Nulo en las salidas.
    )  # Finaliza la declaración de la tarja de origen.
    # Sentido del movimiento.
    tipo: Mapped[TipoMovimientoBandeja] = mapped_column(
        Enum(TipoMovimientoBandeja, length=10),  # Se guarda como texto.
        nullable=False,  # Dato obligatorio.
    )  # Finaliza la declaración del tipo.
    # Cantidad de bandejas del movimiento.
    cantidad: Mapped[int] = mapped_column(Integer, nullable=False)
    # Una anulación conserva la fila y deja de sumarla al saldo (HU24).
    anulado: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Instante UTC en que se registró el movimiento.
    fecha_hora: Mapped[datetime] = mapped_column(
        DateTime,  # Fecha con hora.
        default=lambda: datetime.now(timezone.utc),  # Se calcula al insertar.
        nullable=False,  # Dato obligatorio.
    )  # Finaliza la declaración de la fecha.
