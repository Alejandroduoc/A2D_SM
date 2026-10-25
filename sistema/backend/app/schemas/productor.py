# Busca caracteres no permitidos en el teléfono.
import re

# Base de los schemas, límites de campos y validadores previos a la conversión.
from pydantic import BaseModel, Field, field_validator

# Reutiliza el cálculo de Módulo 11, la representación común del RUT y la limpieza de textos.
from app.core.validators import (
    normalizar_nombre_catalogo,  # Quita espacios de más; rechaza tipos que no son texto.
    normalizar_rut,  # Deja el RUT como cuerpo-DV sin puntos.
    normalizar_texto_opcional,  # Igual que el anterior, pero un texto vacío pasa a None.
    validar_rut_chileno,  # Dígito verificador Módulo 11.
)  # Finaliza las importaciones de validadores.

# Teléfono: dígitos, espacios, guiones, paréntesis y un "+" inicial opcional.
_PATRON_TELEFONO = re.compile(r"^\+?[0-9 ()\-]+$")


# Revisa el RUT recibido y lo devuelve normalizado (compartido por alta y edición).
def _rut(valor: object) -> str:
    # Evita pasar números, nulos u otros objetos a las expresiones regulares.
    if not isinstance(valor, str):
        # Pydantic convierte este rechazo en un error de validación del campo.
        raise ValueError("El RUT debe ser texto")
    # Comprueba el dígito verificador antes de modificar la presentación.
    if not validar_rut_chileno(valor):
        # Informa una entrada inválida sin acceder a la base de datos.
        raise ValueError("RUT inválido")
    # Devuelve el valor que se guardará y sobre el que se mide max_length.
    return normalizar_rut(valor)


# Exige que el teléfono tenga solo caracteres de teléfono y al menos 6 dígitos.
def _telefono(valor: str | None) -> str | None:
    # Sin teléfono no hay nada que revisar.
    if valor is None:
        return None
    # Rechaza letras y símbolos (por ejemplo "<script>" o "abc").
    if not _PATRON_TELEFONO.match(valor):
        raise ValueError("El teléfono solo admite números, espacios, guiones, paréntesis y + inicial")
    # Un teléfono con menos de 6 dígitos no es utilizable.
    if sum(caracter.isdigit() for caracter in valor) < 6:
        raise ValueError("El teléfono debe tener al menos 6 dígitos")
    return valor


# Define los datos admitidos al crear un productor; la base genera id y estado.
class ProductorCreate(BaseModel):
    # Rechaza campos no declarados (por ejemplo "id" o "activo") en vez de ignorarlos.
    model_config = {"extra": "forbid"}

    # El largo se comprueba después de validar y normalizar el RUT recibido.
    rut: str = Field(max_length=12)
    # Exige una razón social de 3 a 150 caracteres, contados después de quitar espacios de más.
    razon_social: str = Field(min_length=3, max_length=150)
    # Admite omitir la dirección; un texto vacío o solo con espacios se guarda como NULL.
    direccion: str | None = Field(default=None, max_length=200)
    # Admite omitir el teléfono; un texto vacío o solo con espacios se guarda como NULL.
    telefono: str | None = Field(default=None, max_length=20)

    # Revisa la entrada original antes de aplicar el límite del texto normalizado.
    @field_validator("rut", mode="before")
    @classmethod
    def validar_y_normalizar_rut(cls, valor: object) -> str:
        return _rut(valor)

    # "   " queda como "" y falla min_length=3; dobles espacios se reducen a uno.
    @field_validator("razon_social", mode="before")
    @classmethod
    def normalizar_razon_social(cls, valor: object) -> str:
        return normalizar_nombre_catalogo(valor)

    # Limpia espacios y deja None si el texto queda vacío.
    @field_validator("direccion", "telefono", mode="before")
    @classmethod
    def normalizar_opcionales(cls, valor: object) -> str | None:
        return normalizar_texto_opcional(valor)

    # Revisa el formato después de limpiar y de comprobar el largo.
    @field_validator("telefono")
    @classmethod
    def validar_telefono(cls, valor: str | None) -> str | None:
        return _telefono(valor)


# Permite cambios parciales, incluida la corrección del RUT sin cambiar el id.
class ProductorUpdate(BaseModel):
    # Rechaza campos no declarados.
    model_config = {"extra": "forbid"}

    # None significa no modificar el RUT; un texto debe pasar las reglas del alta.
    rut: str | None = Field(default=None, max_length=12)
    # Permite conservar la razón social o reemplazarla dentro de los mismos límites.
    razon_social: str | None = Field(default=None, min_length=3, max_length=150)
    # None conserva la dirección actual; no representa una orden de vaciarla.
    direccion: str | None = Field(default=None, max_length=200)
    # None conserva el teléfono actual.
    telefono: str | None = Field(default=None, max_length=20)
    # False debe conservarse como cambio para permitir la desactivación.
    activo: bool | None = None

    # Aplica validación y normalización antes de comprobar el largo final del RUT.
    @field_validator("rut", mode="before")
    @classmethod
    def validar_y_normalizar_rut(cls, valor: object) -> str | None:
        # None: el servicio descartará este valor con exclude_none=True.
        if valor is None:
            return None
        return _rut(valor)

    # Misma limpieza que en el alta; None conserva la razón social actual.
    @field_validator("razon_social", mode="before")
    @classmethod
    def normalizar_razon_social(cls, valor: object) -> str | None:
        if valor is None:
            return None
        return normalizar_nombre_catalogo(valor)

    # Un texto vacío no puede significar "no cambiar" sin avisar: se rechaza.
    # Quitar la dirección o el teléfono queda pendiente de una decisión del equipo.
    @field_validator("direccion", "telefono", mode="before")
    @classmethod
    def normalizar_opcionales(cls, valor: object) -> str | None:
        if valor is None:
            return None
        texto = normalizar_texto_opcional(valor)
        if texto is None:
            raise ValueError("No se puede dejar vacío; omite el campo para conservar el valor actual")
        return texto

    # Revisa el formato del teléfono nuevo.
    @field_validator("telefono")
    @classmethod
    def validar_telefono(cls, valor: str | None) -> str | None:
        return _telefono(valor)


# Expone únicamente los seis campos del diseño de productores.
class ProductorOut(BaseModel):
    # Identidad interna que se mantiene al corregir el RUT o desactivar el registro.
    id: int
    # RUT almacenado con su representación normalizada.
    rut: str
    # Nombre o razón social actual del productor.
    razon_social: str
    # Dirección actual, que puede no estar informada.
    direccion: str | None
    # Teléfono actual, que puede no estar informado.
    telefono: str | None
    # Estado actual que permite conservar productores desactivados.
    activo: bool

    # Permite construir la respuesta leyendo atributos de una instancia ORM.
    model_config = {"from_attributes": True}
