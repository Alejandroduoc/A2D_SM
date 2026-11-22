"""Sistemas productivos independientes de los demás catálogos."""

# Tipos de columna (estado, id entero, texto) y la restricción única con nombre propio.
from sqlalchemy import Boolean, Integer, String, UniqueConstraint
# Declaran atributos tipados con el estilo SQLAlchemy 2 del proyecto.
from sqlalchemy.orm import Mapped, mapped_column

# Registra el modelo en el mismo conjunto de tablas de la aplicación.
from app.core.database import Base


# Hereda de Base: SQLAlchemy la trata como la tabla "sistemas_productivos".
class SistemaProductivo(Base):
    """Representa una forma de producción con desactivación lógica."""

    # Nombre de la tabla en SQL Server.
    __tablename__ = "sistemas_productivos"
    # La unicidad abarca sistemas activos e inactivos.
    __table_args__ = (
        # Nombre explícito para reconocer el conflicto en el servicio.
        UniqueConstraint("nombre", name="uq_sistemas_productivos_nombre"),
    )  # Finaliza las opciones de la tabla.

    # Identificador entero que SQL Server asigna al insertar (IDENTITY).
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Nombre visible del sistema productivo (ej. orgánico, convencional); obligatorio y único.
    nombre: Mapped[str] = mapped_column(
        # CI_AS: ignora mayúsculas al comparar y distingue tildes.
        String(50, collation="SQL_Latin1_General_CP1_CI_AS"),
        # Todo sistema productivo debe tener nombre.
        nullable=False,
    )  # Finaliza la declaración del nombre.
    # Estado lógico: se desactiva en vez de borrar; nace activo.
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
