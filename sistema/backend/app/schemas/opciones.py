"""Contratos de salida de las listas de solo lectura para los formularios (HU11)."""

# Tara exacta de la bandeja, sin errores de redondeo binario.
from decimal import Decimal

# Base de los schemas; aquí solo se definen respuestas, no datos de entrada.
from pydantic import BaseModel


# Elemento de una lista de selección: especies, variedades, calidades y sistemas productivos.
class OpcionOut(BaseModel):
    # Permite construir la respuesta leyendo atributos de una instancia ORM.
    model_config = {"from_attributes": True}

    # Identificador que el formulario enviará al guardar la recepción.
    id: int
    # Texto que ve el operador en la lista.
    nombre: str


# Elemento de la lista de tipos de bandeja: la tara es necesaria para calcular los kilos netos (E3).
class OpcionBandejaOut(BaseModel):
    # Permite construir la respuesta leyendo atributos de una instancia ORM.
    model_config = {"from_attributes": True}

    # Identificador que el formulario enviará al guardar la recepción.
    id: int
    # Texto que ve el operador en la lista.
    nombre: str
    # Tara en kg; en JSON llega como texto ("1.50") para no perder decimales.
    peso_tara_kg: Decimal


# Elemento del buscador de productores, sin datos de contacto ni estado.
class ProductorOpcionOut(BaseModel):
    # Permite construir la respuesta leyendo atributos de una instancia ORM.
    model_config = {"from_attributes": True}

    # Identificador que el formulario enviará al guardar la recepción.
    id: int
    # RUT normalizado (cuerpo-DV sin puntos), para distinguir productores con nombres parecidos.
    rut: str
    # Nombre o razón social que ve el operador en la lista.
    razon_social: str
