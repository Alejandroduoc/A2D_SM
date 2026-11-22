"""Contratos de alta, edición y consulta de especies."""

# Define contratos, límites y validadores previos a la comprobación del largo.
from pydantic import BaseModel, Field, field_validator

# Reutiliza la preparación común de los nombres de catálogos.
from app.core.validators import normalizar_nombre_catalogo


# El cliente aporta únicamente el nombre; la base asigna identidad y estado.
class EspecieCreate(BaseModel):
    # Rechaza campos ajenos al contrato en lugar de ignorarlos.
    model_config = {"extra": "forbid"}

    # Mide el nombre después de preparar Unicode y espacios.
    nombre: str = Field(min_length=1, max_length=50)

    # Normaliza antes de aplicar los límites del campo.
    @field_validator("nombre", mode="before")
    # Vincula el validador a la clase sin requerir una instancia previa.
    @classmethod
    # El helper rechaza también None y cualquier otro valor no textual.
    def normalizar_nombre(cls, valor: object) -> str:
        # Conserva capitalización y tildes según el contrato del catálogo.
        return normalizar_nombre_catalogo(valor)


# Admite cambios parciales y cuerpos vacíos sin inventar modificaciones.
class EspecieUpdate(BaseModel):
    # No permite reasignar ids ni enviar datos de auditoría como cambios.
    model_config = {"extra": "forbid"}

    # None significa conservar el nombre; el texto se prepara y valida.
    nombre: str | None = Field(default=None, min_length=1, max_length=50)
    # None conserva el estado y False permite solicitar la desactivación.
    activo: bool | None = None

    # Prepara el nombre antes de comprobar su largo.
    @field_validator("nombre", mode="before")
    # Permite ejecutar la validación durante la construcción del schema.
    @classmethod
    # Distingue la señal de conservar el dato de un nuevo texto.
    def normalizar_nombre(cls, valor: object) -> str | None:
        # Las actualizaciones posteriores descartarán None al preparar cambios.
        if valor is None:
            # No intenta normalizar una ausencia de modificación.
            return None
        # Usa la misma normalización y comprobación de tipo que el alta.
        return normalizar_nombre_catalogo(valor)


# Expone solo los tres campos públicos previstos para una especie.
class EspecieOut(BaseModel):
    # Permite leer directamente atributos de los modelos ORM.
    model_config = {"from_attributes": True}

    # Identidad interna que se conserva al renombrar o desactivar.
    id: int
    # Nombre normalizado que conserva su capitalización y tildes.
    nombre: str
    # Estado lógico del registro.
    activo: bool
