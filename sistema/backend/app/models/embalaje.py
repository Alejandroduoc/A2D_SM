"""Embalajes con peso fijo por caja o modalidad a granel."""

# Permite tipar con precisión decimal los kilos configurados por caja.
from decimal import Decimal

# Tipos de columna y restricciones aplicadas también por SQL Server.
from sqlalchemy import Boolean, CheckConstraint, Integer, Numeric, String, UniqueConstraint
# Declaran atributos tipados con el estilo SQLAlchemy 2 del proyecto.
from sqlalchemy.orm import Mapped, mapped_column

# Registra el modelo en el conjunto de tablas de la aplicación.
from app.core.database import Base


# Hereda de Base para representar el catálogo de embalajes.
class Embalaje(Base):
    """Representa un embalaje fijo o a granel sin depender de su nombre."""

    # Nombre de la tabla en SQL Server.
    __tablename__ = "embalajes"
    # Conserva nombres únicos y admite solo kilos positivos o un valor nulo.
    __table_args__ = (
        # El nombre permanece reservado aunque el embalaje esté inactivo.
        UniqueConstraint("nombre", name="uq_embalajes_nombre"),
        # NULL identifica granel; cualquier peso fijo debe ser mayor que cero.
        CheckConstraint(
            "kg_por_caja IS NULL OR kg_por_caja > 0",
            name="ck_embalajes_kg_por_caja_positivo_o_nulo",
        ),
    )  # Finaliza las restricciones de la tabla.

    # Identificador entero que SQL Server asigna al insertar.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Nombre visible del embalaje, comparado sin distinguir mayúsculas.
    nombre: Mapped[str] = mapped_column(
        # Mantiene el mismo criterio de comparación de los demás catálogos.
        String(50, collation="SQL_Latin1_General_CP1_CI_AS"),
        # Todo embalaje debe tener un nombre.
        nullable=False,
    )  # Finaliza la declaración del nombre.
    # Peso fijo por caja; queda nulo cuando el embalaje se pesa a granel.
    kg_por_caja: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    # Estado lógico: el embalaje nace activo y nunca se elimina físicamente.
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Expone la modalidad como dato calculado para los schemas de respuesta.
    @property
    # Un valor nulo representa granel, sin interpretar el texto del nombre.
    def es_granel(self) -> bool:
        # Devuelve verdadero únicamente cuando no existe un peso fijo por caja.
        return self.kg_por_caja is None
