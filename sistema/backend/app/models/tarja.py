"""Tarjas de recepción con pesos, calidad y trazabilidad del registro."""

import enum
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


# Estados previstos para el ciclo completo de una tarja.
class EstadoTarja(str, enum.Enum):
    RECEPCIONADA = "RECEPCIONADA"
    PARCIAL = "PARCIAL"
    PROCESADA = "PROCESADA"
    ANULADA = "ANULADA"


# Conserva los datos históricos usados para calcular los kilos recibidos.
class Tarja(Base):
    __tablename__ = "tarjas"
    __table_args__ = (
        CheckConstraint(
            "cantidad_bandejas > 0",
            name="ck_tarjas_cantidad_bandejas_positiva",
        ),
        CheckConstraint(
            "kilos_brutos > 0",
            name="ck_tarjas_kilos_brutos_positivos",
        ),
        CheckConstraint(
            "peso_pallet_kg >= 0",
            name="ck_tarjas_peso_pallet_kg_no_negativo",
        ),
        CheckConstraint(
            "tara_kg > 0",
            name="ck_tarjas_tara_kg_positiva",
        ),
        CheckConstraint(
            "kilos_netos > 0",
            name="ck_tarjas_kilos_netos_positivos",
        ),
        CheckConstraint(
            "porcentaje_calidad BETWEEN 0 AND 100",
            name="ck_tarjas_porcentaje_calidad_rango",
        ),
        CheckConstraint(
            "veces_impresa >= 0",
            name="ck_tarjas_veces_impresa_no_negativa",
        ),
    )

    # Identidad interna y número operativo correlativo de la tarja.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    numero_tarja: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    # Referencias obligatorias al productor, usuario y catálogos elegidos.
    productor_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("productores.id"),
        index=True,
        nullable=False,
    )
    usuario_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("usuarios.id"),
        nullable=False,
    )
    sistema_productivo_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sistemas_productivos.id"),
        nullable=False,
    )
    variedad_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("variedades.id"),
        nullable=False,
    )
    calidad_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("calidades.id"),
        nullable=False,
    )
    tipo_bandeja_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tipos_bandeja.id"),
        nullable=False,
    )
    # Datos de pesaje conservados para reproducir el cálculo histórico.
    cantidad_bandejas: Mapped[int] = mapped_column(Integer, nullable=False)
    tara_kg: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    peso_pallet_kg: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    kilos_brutos: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    kilos_netos: Mapped[int] = mapped_column(Integer, nullable=False)
    # Calidad, fecha operacional y estado del flujo de recepción.
    porcentaje_calidad: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    fecha_recepcion: Mapped[date] = mapped_column(Date, nullable=False)
    estado: Mapped[EstadoTarja] = mapped_column(
        Enum(EstadoTarja, length=20),
        default=EstadoTarja.RECEPCIONADA,
        nullable=False,
    )
    # Momento UTC del registro y control de impresiones posteriores.
    fecha_hora: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    veces_impresa: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    impresa_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
