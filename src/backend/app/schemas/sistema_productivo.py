"""Contratos de alta, edición y consulta de sistemas productivos."""

# Base de los schemas, límites de campos y validadores previos a la conversión.
from pydantic import BaseModel, Field, field_validator

# Quita espacios sobrantes y unifica la escritura Unicode del nombre.
from app.core.validators import normalizar_nombre_catalogo


# Define los datos admitidos al crear un sistema productivo; la base genera id y estado.
class SistemaProductivoCreate(BaseModel):
    """Recibe únicamente el nombre de un sistema productivo nuevo."""

    # Rechaza con 422 cualquier campo no declarado.
    model_config = {"extra": "forbid"}
    # Nombre obligatorio de 1 a 50 caracteres, medido después de normalizar.
    nombre: str = Field(min_length=1, max_length=50)

    # Normaliza antes de aplicar los límites de largo.
    @field_validator("nombre", mode="before")
    # Vincula el validador a la clase del schema.
    @classmethod
    # Devuelve el nombre ya normalizado que se guardará y comparará.
    def normalizar_nombre(cls, valor: object) -> str:
        # Delega en el helper común de catálogos (también rechaza tipos no textuales).
        return normalizar_nombre_catalogo(valor)


# Permite cambios parciales: renombrar, desactivar o activar.
class SistemaProductivoUpdate(BaseModel):
    """Admite cambios parciales de nombre y estado."""

    # Rechaza campos no declarados para no ignorarlos en silencio.
    model_config = {"extra": "forbid"}
    # None significa no modificar el nombre.
    nombre: str | None = Field(default=None, min_length=1, max_length=50)
    # None conserva el estado; False desactiva y True activa.
    activo: bool | None = None

    # Normaliza el nombre nuevo antes de validar su largo.
    @field_validator("nombre", mode="before")
    # Vincula el validador a la clase del schema.
    @classmethod
    # Admite None como señal de no modificar el nombre.
    def normalizar_nombre(cls, valor: object) -> str | None:
        # No intenta normalizar un nombre que no se quiere cambiar.
        if valor is None:
            # El servicio descarta este valor con exclude_none=True.
            return None
        # Aplica la misma normalización que en la creación.
        return normalizar_nombre_catalogo(valor)


# Expone solo los campos públicos del catálogo en las respuestas.
class SistemaProductivoOut(BaseModel):
    """Expone los campos públicos del catálogo."""

    # Permite construir la respuesta leyendo atributos de una instancia ORM.
    model_config = {"from_attributes": True}
    # Identificador interno del sistema productivo.
    id: int
    # Nombre normalizado guardado en la base.
    nombre: str
    # Estado actual (activo o inactivo).
    activo: bool
