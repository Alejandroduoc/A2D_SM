"""Tipos de bandeja con tara propia y desactivación lógica."""

# Permite tipar con precisión decimal el peso de tara almacenado.
from decimal import Decimal

# Tipos de columna y restricciones aplicadas también por SQL Server.
from sqlalchemy import Boolean, CheckConstraint, Integer, Numeric, String, UniqueConstraint
# Declaran atributos tipados con el estilo SQLAlchemy 2 del proyecto.
from sqlalchemy.orm import Mapped, mapped_column

# Registra el modelo en el conjunto de tablas de la aplicación.
from app.core.database import Base


# Hereda de Base para representar la tabla de tipos de bandeja.
class TipoBandeja(Base):
    """Representa una bandeja reutilizable con una tara positiva."""

    # Nombre de la tabla en SQL Server.
    __tablename__ = "tipos_bandeja"
    # Conserva nombres únicos y evita pesos nulos, iguales a cero o negativos.
    __table_args__ = (
        # El nombre permanece reservado aunque la bandeja esté inactiva.
        UniqueConstraint("nombre", name="uq_tipos_bandeja_nombre"),
        # La tara siempre debe representar un peso estrictamente positivo.
        CheckConstraint(
            "peso_tara_kg > 0",
            name="ck_tipos_bandeja_peso_tara_kg_positivo",
        ),
    )  # Finaliza las restricciones de la tabla.

    # Identificador entero que SQL Server asigna al insertar.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Nombre visible de la bandeja, comparado sin distinguir mayúsculas.
    nombre: Mapped[str] = mapped_column(
        # Mantiene el mismo criterio de comparación de los demás catálogos.
        String(50, collation="SQL_Latin1_General_CP1_CI_AS"),
        # Toda bandeja debe tener un nombre.
        nullable=False,
    )  # Finaliza la declaración del nombre.
    # Peso propio de la bandeja con hasta cuatro enteros y dos decimales.
    peso_tara_kg: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    # Estado lógico: la bandeja nace activa y nunca se elimina físicamente.
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
