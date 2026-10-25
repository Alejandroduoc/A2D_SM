"""Sistemas productivos independientes de los demás catálogos."""

from sqlalchemy import Boolean, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SistemaProductivo(Base):
    """Representa una forma de producción con desactivación lógica."""

    __tablename__ = "sistemas_productivos"
    # La unicidad abarca sistemas activos e inactivos.
    __table_args__ = (
        UniqueConstraint("nombre", name="uq_sistemas_productivos_nombre"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(
        String(50, collation="SQL_Latin1_General_CP1_CI_AS"),
        nullable=False,
    )
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
