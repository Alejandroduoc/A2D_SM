"""Productores con RUT único y estado para conservar su historial."""

# Tipos de las seis columnas previstas para el catálogo de productores.
from sqlalchemy import Boolean, Integer, String

# Declaran atributos tipados con el estilo SQLAlchemy 2 del proyecto.
from sqlalchemy.orm import Mapped, mapped_column

# Registra el modelo en el mismo conjunto de tablas de la aplicación.
from app.core.database import Base


# Representa al productor mediante un id interno que no cambia al corregir su RUT.
class Productor(Base):
    # Nombre de la tabla del catálogo en SQL Server.
    __tablename__ = "productores"

    # Identificador interno generado por la base de datos.
    id: Mapped[int] = mapped_column(
        Integer,  # El diseño de A2D_SM utiliza un entero, no un UUID.
        primary_key=True,  # Identifica de forma única cada productor.
        autoincrement=True,  # La base asigna el id al insertar el registro.
    )  # Finaliza la declaración del identificador interno.

    # Guarda el RUT normalizado y respalda su unicidad en SQL Server.
    rut: Mapped[str] = mapped_column(
        String(12),  # Coincide con el largo definido en el diseño.
        unique=True,  # Impide guardar dos veces el mismo RUT normalizado.
        index=True,  # Prepara la búsqueda de productores por RUT.
        nullable=False,  # Todo productor debe identificar su RUT.
    )  # Finaliza la declaración del RUT del productor.

    # Nombre o razón social que identifica al productor en las operaciones.
    razon_social: Mapped[str] = mapped_column(
        String(150),  # Limita la razón social al largo del diseño.
        nullable=False,  # Todo productor debe tener una razón social.
    )  # Finaliza la declaración de la razón social.

    # Dirección opcional para los datos de contacto del productor.
    direccion: Mapped[str | None] = mapped_column(
        String(200),  # Admite hasta 200 caracteres de dirección.
        nullable=True,  # Permite crear productores sin dirección informada.
    )  # Finaliza la declaración de la dirección.

    # Teléfono opcional, almacenado como texto para conservar su formato.
    telefono: Mapped[str | None] = mapped_column(
        String(20),  # Admite prefijos y separadores dentro del largo acordado.
        nullable=True,  # Permite crear productores sin teléfono informado.
    )  # Finaliza la declaración del teléfono.

    # Permite desactivar al productor conservando su identidad y su historial.
    activo: Mapped[bool] = mapped_column(
        Boolean,  # Representa si el productor está habilitado.
        default=True,  # Un productor nuevo nace activo al insertarse.
        nullable=False,  # Todo productor debe tener un estado definido.
    )  # Finaliza la declaración del estado del productor.
