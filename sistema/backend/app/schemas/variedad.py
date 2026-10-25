"""Contratos de variedades con especie fijada durante el alta."""

# Define campos y validadores para las entradas y respuestas del catálogo.
from pydantic import BaseModel, Field, field_validator

# Comparte la misma preparación de nombres utilizada para especies.
from app.core.validators import normalizar_nombre_catalogo


# Recibe la clasificación inicial sin aceptar identidad ni estado del cliente.
class VariedadCreate(BaseModel):
    # Rechaza entradas que no pertenecen al contrato del alta.
    model_config = {"extra": "forbid"}

    # Exige un entero positivo, sin convertir textos, booleanos o decimales.
    especie_id: int = Field(gt=0, strict=True)
    # Aplica los límites después de normalizar el nombre.
    nombre: str = Field(min_length=1, max_length=50)

    # Prepara el valor original antes de validar el largo.
    @field_validator("nombre", mode="before")
    # Vincula la validación a la clase del schema.
    @classmethod
    # Rechaza None y cualquier tipo distinto de texto mediante el helper.
    def normalizar_nombre(cls, valor: object) -> str:
        # Conserva letras, tildes y capitalización y unifica los espacios.
        return normalizar_nombre_catalogo(valor)


# Permite corregir nombre y estado sin cambiar la especie de una variedad.
class VariedadUpdate(BaseModel):
    # Un especie_id enviado aquí se rechaza en vez de ignorarse silenciosamente.
    model_config = {"extra": "forbid"}

    # None conserva el nombre actual; un texto nuevo debe tener de 1 a 50 caracteres.
    nombre: str | None = Field(default=None, min_length=1, max_length=50)
    # Conserva False para solicitar desactivación y None para no modificar.
    activo: bool | None = None

    # Normaliza antes de comprobar la longitud del nombre nuevo.
    @field_validator("nombre", mode="before")
    # Habilita la validación durante la construcción de la clase de entrada.
    @classmethod
    # Admite explícitamente None como señal de conservar el dato.
    def normalizar_nombre(cls, valor: object) -> str | None:
        # No pasa al helper una ausencia de cambio de nombre.
        if valor is None:
            # El servicio posterior conservará el valor almacenado.
            return None
        # Comparte las mismas reglas textuales del alta y del catálogo de especies.
        return normalizar_nombre_catalogo(valor)


# Devuelve solo los cuatro campos públicos de la variedad.
class VariedadOut(BaseModel):
    # Permite construir respuestas desde atributos de los modelos ORM.
    model_config = {"from_attributes": True}

    # Identificador interno estable de la variedad.
    id: int
    # Identificador de la especie a la que pertenece.
    especie_id: int
    # Nombre normalizado sin alterar sus tildes o capitalización.
    nombre: str
    # Estado lógico que permite conservar el historial del registro.
    activo: bool
