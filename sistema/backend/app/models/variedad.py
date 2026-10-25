"""Variedades identificadas dentro de una única especie."""

# Tipos de columna, referencia a especie y unicidad dentro de esa especie.
from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint

# Declara columnas tipadas con el mismo estilo del resto del backend.
from sqlalchemy.orm import Mapped, mapped_column

# Registra la tabla en la metadata compartida de la aplicación.
from app.core.database import Base


# Conserva identidad y clasificación al desactivar una variedad.
class Variedad(Base):
    # Nombre físico del catálogo en SQL Server.
    __tablename__ = "variedades"
    # Permite repetir un nombre únicamente en especies diferentes.
    __table_args__ = (
        # Restringe el nombre dentro de su especie, incluidos los inactivos.
        UniqueConstraint(
            "especie_id",  # Primera columna de la clave compuesta.
            "nombre",  # Nombre reservado dentro de esa especie.
            name="uq_variedades_especie_nombre",  # Permite identificar el conflicto.
        ),  # El índice de esta restricción comienza por especie_id.
    )  # No duplica el índice ni declara unicidad global del nombre.

    # Identificador interno generado por la base.
    id: Mapped[int] = mapped_column(
        Integer,  # Conserva los ids enteros definidos para los catálogos.
        primary_key=True,  # Identifica cada variedad de forma estable.
        autoincrement=True,  # SQL Server asigna el valor al insertar.
    )  # Finaliza la declaración del identificador.

    # Cada variedad debe pertenecer a una especie existente.
    especie_id: Mapped[int] = mapped_column(
        Integer,  # Coincide con el tipo de la clave de especies.
        ForeignKey("especies.id", name="fk_variedades_especie_id"),  # No configura borrado en cascada.
        nullable=False,  # Impide variedades sin especie.
    )  # La FK textual no requiere importar aquí el modelo Especie.

    # Nombre comparado con las mismas reglas SQL que el catálogo de especies.
    nombre: Mapped[str] = mapped_column(
        String(50, collation="SQL_Latin1_General_CP1_CI_AS"),  # Ignora capitalización y distingue tildes.
        nullable=False,  # Toda variedad debe tener nombre.
    )  # La unicidad se respalda mediante la restricción compuesta.

    # Permite desactivar sin borrar la variedad ni su clasificación.
    activo: Mapped[bool] = mapped_column(
        Boolean,  # Representa si la variedad está habilitada.
        default=True,  # Una variedad nueva nace activa al insertarse.
        nullable=False,  # No admite estados indefinidos.
    )  # Finaliza la declaración del estado.
