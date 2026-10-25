"""Especies con nombre único y desactivación lógica."""

# Tipos de las columnas y restricción de unicidad identificable por nombre.
from sqlalchemy import Boolean, Integer, String, UniqueConstraint

# Mantiene el estilo de atributos tipados de los modelos existentes.
from sqlalchemy.orm import Mapped, mapped_column

# Comparte la metadata de la aplicación sin crear otra base declarativa.
from app.core.database import Base


# Representa una especie sin eliminar su identidad al desactivarla.
class Especie(Base):
    # Nombre físico del catálogo en SQL Server.
    __tablename__ = "especies"
    # Reserva el nombre también para registros inactivos.
    __table_args__ = (
        # La restricción única no depende del estado del registro.
        UniqueConstraint("nombre", name="uq_especies_nombre"),
    )  # No agrega un índice único adicional sobre el mismo campo.

    # Identificador interno generado por la base.
    id: Mapped[int] = mapped_column(
        Integer,  # Los catálogos del diseño usan ids enteros.
        primary_key=True,  # Identifica cada especie de forma estable.
        autoincrement=True,  # SQL Server asigna el valor al insertar.
    )  # Finaliza la declaración del identificador.

    # Nombre preparado por los schemas antes de persistirlo.
    nombre: Mapped[str] = mapped_column(
        String(50, collation="SQL_Latin1_General_CP1_CI_AS"),  # Ignora capitalización y distingue tildes.
        nullable=False,  # Toda especie debe tener nombre.
    )  # La restricción nombrada respalda la unicidad.

    # Conserva el registro y sus referencias cuando deja de ofrecerse.
    activo: Mapped[bool] = mapped_column(
        Boolean,  # Representa el estado lógico.
        default=True,  # Una especie nueva nace activa al insertarse.
        nullable=False,  # No admite estados indefinidos.
    )  # Finaliza la declaración del estado.
