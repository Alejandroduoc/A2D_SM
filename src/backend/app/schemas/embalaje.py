"""Contratos de alta, edición y consulta de embalajes."""

# Permite conservar exactamente los decimales recibidos para los kilos.
from decimal import Decimal

# Base de los schemas, límites de campos y validadores previos a la conversión.
from pydantic import BaseModel, Field, field_validator

# Quita espacios sobrantes y unifica la escritura Unicode del nombre.
from app.core.validators import normalizar_nombre_catalogo
# Reutiliza el rechazo explícito de booleanos para pesos decimales.
from app.schemas.tipo_bandeja import validar_decimal_no_booleano


# Define los datos admitidos al crear un embalaje.
class EmbalajeCreate(BaseModel):
    """Recibe un embalaje fijo o uno a granel indicado mediante null."""

    # Rechaza campos no declarados para evitar entradas ignoradas en silencio.
    model_config = {"extra": "forbid"}
    # Nombre obligatorio de 1 a 50 caracteres después de normalizar.
    nombre: str = Field(min_length=1, max_length=50)
    # El campo es obligatorio; null significa granel y un número significa peso fijo.
    kg_por_caja: Decimal | None = Field(gt=0, max_digits=8, decimal_places=2)

    # Normaliza el nombre antes de comprobar sus límites.
    @field_validator("nombre", mode="before")
    # Vincula el validador a la clase del schema.
    @classmethod
    # Devuelve el nombre que se guardará y comparará.
    def normalizar_nombre(cls, valor: object) -> str:
        # Reutiliza el helper común de los catálogos.
        return normalizar_nombre_catalogo(valor)

    # Revisa el peso original antes de convertirlo a Decimal.
    @field_validator("kg_por_caja", mode="before")
    # Vincula el validador a la clase del schema.
    @classmethod
    # Conserva null para granel, pero rechaza booleanos.
    def rechazar_kilos_booleanos(cls, valor: object) -> object:
        # Aplica la regla común para entradas decimales.
        return validar_decimal_no_booleano(valor)


# Permite cambios parciales, incluido convertir un embalaje fijo en granel.
class EmbalajeUpdate(BaseModel):
    """Distingue entre omitir los kilos y enviarlos explícitamente como null."""

    # Rechaza cualquier campo que no pertenezca al contrato.
    model_config = {"extra": "forbid"}
    # None significa conservar el nombre y nunca persistirlo como nulo.
    nombre: str | None = Field(default=None, min_length=1, max_length=50)
    # Omitido conserva los kilos; null explícito convierte el embalaje a granel.
    kg_por_caja: Decimal | None = Field(default=None, gt=0, max_digits=8, decimal_places=2)
    # None conserva el estado; False desactiva y True activa.
    activo: bool | None = None

    # Normaliza solamente cuando se proporciona un nombre nuevo.
    @field_validator("nombre", mode="before")
    # Vincula el validador a la clase del schema.
    @classmethod
    # Admite None como señal de conservar el nombre actual.
    def normalizar_nombre(cls, valor: object) -> str | None:
        # Evita normalizar cuando no se quiere cambiar el nombre.
        if valor is None:
            # Conserva la señal que interpretará el servicio.
            return None
        # Aplica la misma normalización usada durante la creación.
        return normalizar_nombre_catalogo(valor)

    # Revisa el peso original antes de convertirlo a Decimal.
    @field_validator("kg_por_caja", mode="before")
    # Vincula el validador a la clase del schema.
    @classmethod
    # Conserva null para granel, pero rechaza booleanos.
    def rechazar_kilos_booleanos(cls, valor: object) -> object:
        # Aplica la regla común para entradas decimales.
        return validar_decimal_no_booleano(valor)


# Expone los datos públicos y la modalidad calculada del embalaje.
class EmbalajeOut(BaseModel):
    """Representa un embalaje devuelto por la API."""

    # Permite construir la salida leyendo atributos de una instancia ORM.
    model_config = {"from_attributes": True}
    # Identificador interno del embalaje.
    id: int
    # Nombre normalizado almacenado en la base.
    nombre: str
    # Peso fijo o null cuando el embalaje es a granel.
    kg_por_caja: Decimal | None
    # Estado lógico actual.
    activo: bool
    # Indica la modalidad sin depender del texto del nombre.
    es_granel: bool
