"""Calidades de fruta con nombre único y desactivación lógica."""

from sqlalchemy import Boolean, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Calidad(Base):
    """Representa una calidad conservando su identidad al desactivarla."""

    __tablename__ = "calidades"
    # El nombre permanece reservado también para registros inactivos.
    __table_args__ = (UniqueConstraint("nombre", name="uq_calidades_nombre"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(
        String(50, collation="SQL_Latin1_General_CP1_CI_AS"),
        nullable=False,
    )
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
