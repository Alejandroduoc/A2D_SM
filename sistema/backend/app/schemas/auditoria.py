"""Contratos de lectura de la bitácora de auditoría (HU22)."""

# Fechas de los filtros y de cada evento.
from datetime import date, datetime

# Contratos Pydantic de la API.
from pydantic import BaseModel, Field

# Acciones que guarda la auditoría de HU21.
from app.models.auditoria import AccionAuditoria
# Campo con su valor anterior y su valor nuevo, igual que en el historial de HU23.
from app.schemas.trazabilidad import CambioOut


class UsuarioAuditoriaOut(BaseModel):
    """Identificador y nombre público de un actor de auditoría."""

    # Identificador que se envía como filtro.
    id: str
    # Nombre que se muestra en el selector.
    nombre_completo: str


class DatoAuditoriaOut(BaseModel):
    """Un campo del registro afectado, como se lee en pantalla."""

    # Nombre legible del campo.
    campo: str
    # Valor como texto; nulo si el campo no tenía valor.
    valor: str | None


class EventoAuditoriaOut(BaseModel):
    """Una operación registrada, sin credenciales."""

    # Identificador del evento.
    id: int
    # Momento del evento, en UTC.
    fecha_hora: datetime
    # Identificador del responsable.
    usuario_id: str
    # Nombre del responsable; nunca sus credenciales.
    usuario: str
    # Tabla afectada, con su nombre técnico.
    tabla: str
    # Identificador del registro afectado.
    registro_id: str
    # Creación, modificación o eliminación.
    accion: AccionAuditoria
    # Solo en una modificación: los campos que cambiaron (criterio 2).
    cambios: list[CambioOut]
    # Todos los campos del registro: los nuevos o, en una eliminación, los anteriores.
    datos: list[DatoAuditoriaOut]
    # Justificación, cuando la operación la tiene.
    motivo: str | None


class BitacoraOut(BaseModel):
    """Página de eventos y metadatos para informar resultados truncados."""

    # Eventos de esta página.
    items: list[EventoAuditoriaOut]
    # Eventos que cumplen los filtros, en todas las páginas.
    total: int
    # Tamaño de la página pedida.
    limite: int
    # Eventos saltados antes de esta página.
    offset: int
    # Verdadero si quedan eventos después de esta página.
    hay_mas: bool


class BitacoraFiltros(BaseModel):
    """Filtros validados que usa internamente el servicio."""

    # Responsable exacto.
    usuario_id: str | None = None
    # Primer día, en hora de Chile.
    fecha_desde: date | None = None
    # Último día, en hora de Chile.
    fecha_hasta: date | None = None
    # Tabla exacta.
    tabla: str | None = Field(default=None, max_length=50)
    # Acción exacta.
    accion: AccionAuditoria | None = None
