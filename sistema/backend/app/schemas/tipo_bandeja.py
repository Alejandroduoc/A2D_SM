"""Contratos de alta, edición y consulta de tipos de bandeja."""

# Permite conservar exactamente los decimales recibidos para la tara.
from decimal import Decimal

# Base de los schemas, límites de campos y validadores previos a la conversión.
from pydantic import BaseModel, Field, field_validator

# Quita espacios sobrantes y unifica la escritura Unicode del nombre.
from app.core.validators import normalizar_nombre_catalogo


# Rechaza booleanos antes de que Pydantic pueda convertirlos en números.
def validar_decimal_no_booleano(valor: object) -> object:
    # En Python un booleano también se considera entero, pero no es un peso válido.
    if isinstance(valor, bool):
        # Informa un error de validación asociado al campo decimal recibido.
        raise ValueError("El peso debe ser un número decimal")
    # Conserva números y textos para que Pydantic los convierta a Decimal.
    return valor


# Define los datos admitidos al crear un tipo de bandeja.
class TipoBandejaCreate(BaseModel):
    """Recibe el nombre y la tara positiva de una bandeja nueva."""

    # Rechaza campos no declarados para evitar entradas ignoradas en silencio.
    model_config = {"extra": "forbid"}
    # Nombre obligatorio de 1 a 50 caracteres después de normalizar.
    nombre: str = Field(min_length=1, max_length=50)
    # Tara obligatoria, positiva, con hasta seis dígitos y dos decimales.
    peso_tara_kg: Decimal = Field(gt=0, max_digits=6, decimal_places=2)

    # Normaliza el nombre antes de comprobar sus límites.
    @field_validator("nombre", mode="before")
    # Vincula el validador a la clase del schema.
    @classmethod
    # Devuelve el nombre que se guardará y comparará.
    def normalizar_nombre(cls, valor: object) -> str:
        # Reutiliza el helper común de los catálogos.
        return normalizar_nombre_catalogo(valor)

    # Revisa el tipo original antes de convertirlo a Decimal.
    @field_validator("peso_tara_kg", mode="before")
    # Vincula el validador a la clase del schema.
    @classmethod
    # Impide que True y False se interpreten como uno y cero.
    def rechazar_tara_booleana(cls, valor: object) -> object:
        # Aplica la regla común para entradas decimales.
        return validar_decimal_no_booleano(valor)


# Permite cambios parciales del nombre, la tara o el estado.
class TipoBandejaUpdate(BaseModel):
    """Admite cambios parciales sin confundir ausencia con valores falsos."""

    # Rechaza cualquier campo que no pertenezca al contrato.
    model_config = {"extra": "forbid"}
    # None significa conservar el nombre actual.
    nombre: str | None = Field(default=None, min_length=1, max_length=50)
    # None significa conservar la tara actual.
    peso_tara_kg: Decimal | None = Field(default=None, gt=0, max_digits=6, decimal_places=2)
    # None conserva el estado; False desactiva y True activa.
    activo: bool | None = None

    # Normaliza solamente cuando se proporciona un nombre nuevo.
    @field_validator("nombre", mode="before")
    # Vincula el validador a la clase del schema.
    @classmethod
    # Admite None como señal de conservar el valor actual.
    def normalizar_nombre(cls, valor: object) -> str | None:
        # Evita normalizar cuando no se quiere cambiar el nombre.
        if valor is None:
            # Conserva la señal que interpretará el servicio.
            return None
        # Aplica la misma normalización usada durante la creación.
        return normalizar_nombre_catalogo(valor)

    # Revisa la tara original antes de convertirla a Decimal.
    @field_validator("peso_tara_kg", mode="before")
    # Vincula el validador a la clase del schema.
    @classmethod
    # Permite None, pero rechaza valores booleanos.
    def rechazar_tara_booleana(cls, valor: object) -> object:
        # Aplica la regla común para entradas decimales.
        return validar_decimal_no_booleano(valor)


# Expone únicamente los datos públicos de una bandeja.
class TipoBandejaOut(BaseModel):
    """Representa un tipo de bandeja devuelto por la API."""

    # Permite construir la salida leyendo atributos de una instancia ORM.
    model_config = {"from_attributes": True}
    # Identificador interno del tipo de bandeja.
    id: int
    # Nombre normalizado almacenado en la base.
    nombre: str
    # Tara configurada para cálculos posteriores.
    peso_tara_kg: Decimal
    # Estado lógico actual.
    activo: bool
