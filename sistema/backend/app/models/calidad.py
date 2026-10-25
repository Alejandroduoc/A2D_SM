"""Calidades de fruta con nombre único y desactivación lógica."""

# Tipos de columna (estado, id entero, texto) y la restricción única con nombre propio.
from sqlalchemy import Boolean, Integer, String, UniqueConstraint
# Declaran atributos tipados con el estilo SQLAlchemy 2 del proyecto.
from sqlalchemy.orm import Mapped, mapped_column

# Registra el modelo en el mismo conjunto de tablas de la aplicación.
from app.core.database import Base


# Hereda de Base: SQLAlchemy la trata como la tabla "calidades".
class Calidad(Base):
    """Representa una calidad conservando su identidad al desactivarla."""

    # Nombre de la tabla en SQL Server.
    __tablename__ = "calidades"
    # El nombre permanece reservado también para registros inactivos.
    __table_args__ = (UniqueConstraint("nombre", name="uq_calidades_nombre"),)

    # Identificador entero que SQL Server asigna al insertar (IDENTITY).
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Nombre visible de la calidad; obligatorio y único.
    nombre: Mapped[str] = mapped_column(
        # CI_AS: "Extra" y "extra" chocan como duplicados; las tildes sí se distinguen.
        String(50, collation="SQL_Latin1_General_CP1_CI_AS"),
        # Toda calidad debe tener nombre.
        nullable=False,
    )  # Finaliza la declaración del nombre.
    # Estado lógico: se desactiva en vez de borrar; nace activa.
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
