"""Contratos de la consulta de trazabilidad de una tarja (HU23)."""

# Día de elaboración y momento de cada cambio.
from datetime import date, datetime
# Pesos exactos, sin float.
from decimal import Decimal

# Base de los schemas.
from pydantic import BaseModel

# Datos de la tarja, con sus catálogos y sus kilos.
from app.schemas.tarja import TarjaDetalleOut


# Un proceso en que entró la tarja.
class ProcesoDeTarjaOut(BaseModel):
    """Folio, resultado y si sigue vigente."""

    # Identificador del proceso.
    id: int
    # Folio P más el correlativo.
    folio: str
    # Día de elaboración.
    fecha_elaboracion: date
    # Nombre del embalaje.
    embalaje: str
    # Cajas de la tarja en este proceso.
    cantidad_cajas: Decimal
    # Kilos de la tarja en este proceso.
    kilos_procesados: Decimal
    # El operador la dio por terminada en este proceso.
    tarja_terminada: bool
    # Un proceso anulado no cuenta en sus kilos.
    anulado: bool
    # Nombre de quien lo registró; nunca sus credenciales.
    registrado_por: str


# Un campo que cambió.
class CambioOut(BaseModel):
    """Valor anterior y valor nuevo, como se leen en pantalla."""

    # Nombre visible del campo.
    campo: str
    # Valor anterior.
    antes: str | None
    # Valor nuevo.
    despues: str | None


# Un evento del historial de la tarja.
class EventoTarjaOut(BaseModel):
    """Quién, cuándo y qué pasó."""

    # Momento del cambio, en UTC.
    fecha_hora: datetime
    # Nombre del responsable; nunca sus credenciales.
    usuario: str
    # Qué pasó, en una frase.
    descripcion: str
    # Campos que cambiaron.
    cambios: list[CambioOut]


# Recorrido completo de una tarja (HU23).
class TrazabilidadOut(BaseModel):
    """Recepción, procesos, kilos e historial."""

    # Productor y datos de la recepción, con sus kilos procesados y pendientes.
    tarja: TarjaDetalleOut
    # Kilos netos menos procesados; nula si la tarja está anulada.
    merma: Decimal | None
    # Verdadero mientras la tarja no esté terminada.
    merma_provisional: bool
    # Procesos en que entró, también los anulados.
    procesos: list[ProcesoDeTarjaOut]
    # Sus cambios, en orden de ocurrencia.
    historial: list[EventoTarjaOut]
