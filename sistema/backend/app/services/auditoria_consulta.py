"""Consultas de solo lectura de la bitácora de auditoría (HU22)."""

# Convierte los días de Chile a límites UTC y conserva la hora de cada evento.
from datetime import date, datetime, time, timedelta, timezone
# Interpreta el JSON de valores guardado por HU21.
import json
# Reconoce fechas y cantidades guardadas como texto.
import re

# Construye consultas SQLAlchemy y cuenta resultados.
from sqlalchemy import func, select
# Entrega la sesión de la petición.
from sqlalchemy.orm import Session

# Modelo de auditoría y acciones permitidas.
from app.models.auditoria import AccionAuditoria, Auditoria
# Modelo de usuario para mostrar solo su nombre público.
from app.models.usuario import Usuario
# Contrato de filtros.
from app.schemas.auditoria import BitacoraFiltros
# Zona horaria de la planta, con su horario de verano e invierno.
from app.schemas.tarja import ZONA_CHILE
# Misma comparación y mismos textos que el historial de HU23.
from app.services.trazabilidad import ETIQUETAS_CAMPO, texto_valor, valores_iguales


# Fecha y hora como la guarda la auditoría, con o sin zona.
_FECHA_HORA = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d{6})?(\+00:00)?")
# Fecha sin hora, como la de recepción.
_FECHA = re.compile(r"\d{4}-\d{2}-\d{2}")
# Cantidad con decimales, como la guarda la auditoría.
_DECIMAL = re.compile(r"-?\d+\.\d+")


def _limite_utc(dia: date, fin: bool) -> datetime:
    """Convierte el inicio o el final exclusivo de un día chileno a UTC."""

    # El final exclusivo es el comienzo del día siguiente.
    fecha = dia + timedelta(days=1) if fin else dia
    # La base existente almacena DateTime sin tz, pero con valor UTC.
    return datetime.combine(fecha, time.min, ZONA_CHILE).astimezone(timezone.utc).replace(tzinfo=None)


def _leer_valores(texto: str | None) -> dict:
    """Lee una instantánea guardada, siempre sin password_hash."""

    # NULL significa que la operación no tenía ese estado.
    valores = json.loads(texto) if texto else {}
    # No debe llegar a la respuesta aunque una auditoría antigua lo contenga.
    valores.pop("password_hash", None)
    # Entrega los campos que se pueden mostrar.
    return valores


def _nombre_campo(campo: str) -> str:
    """Nombre legible: el de HU23 si existe; si no, el de la columna sin guiones bajos."""

    # kilos_netos pasa a "Kilos netos".
    return ETIQUETAS_CAMPO.get(campo) or campo.replace("_", " ").capitalize()


def _texto(campo: str, valor) -> str | None:
    """Presenta un valor como las demás pantallas: hora de Chile, fecha DD-MM-AAAA y decimales con coma."""

    # Una fecha y hora guardada está en UTC: se muestra en la hora de la planta.
    if isinstance(valor, str) and _FECHA_HORA.fullmatch(valor):
        try:
            # Con o sin zona escrita, la auditoría guarda UTC.
            momento = datetime.fromisoformat(valor).replace(tzinfo=timezone.utc)
            # La misma hora que muestra la columna Fecha.
            return momento.astimezone(ZONA_CHILE).strftime("%d-%m-%Y %H:%M:%S")
        # Un texto que solo parece una fecha no debe romper la página: se muestra tal cual.
        except (ValueError, OverflowError):
            return valor
    # Una fecha sin hora no cambia de zona: solo se ordena como se lee en Chile.
    if isinstance(valor, str) and _FECHA.fullmatch(valor):
        return "-".join(reversed(valor.split("-")))
    # Lo demás, con los mismos textos del historial de HU23.
    texto = texto_valor(campo, valor)
    # Las cantidades con decimales llevan coma.
    return texto.replace(".", ",") if texto and _DECIMAL.fullmatch(texto) else texto


def _cambios(antes: dict, despues: dict) -> list[dict]:
    """Lista todos los campos que cambiaron, no solo los conocidos por HU23."""

    # Un campo puede estar en un solo lado; se conserva el orden en que se guardó.
    campos = dict.fromkeys([*antes, *despues])
    # Devuelve únicamente lo que cambió, con su valor anterior y su valor nuevo.
    return [
        {
            "campo": _nombre_campo(campo),  # Nombre legible.
            "antes": _texto(campo, antes.get(campo)),  # Valor anterior.
            "despues": _texto(campo, despues.get(campo)),  # Valor nuevo.
        }
        for campo in campos  # Recorre todos los campos del evento.
        if not valores_iguales(antes.get(campo), despues.get(campo))  # "5.00" y "5" no son un cambio.
    ]


def _datos(valores: dict) -> list[dict]:
    """Presenta todos los campos de una instantánea, como se leen en pantalla."""

    # Mantiene el orden en que se guardaron.
    return [{"campo": _nombre_campo(campo), "valor": _texto(campo, valor)} for campo, valor in valores.items()]


def consultar_bitacora(
    db: Session,
    filtros: BitacoraFiltros,
    limite: int,
    offset: int,
) -> dict:
    """Devuelve eventos paginados y sus nombres, sin exponer password_hash."""

    # Reúne las condiciones que comparten el conteo y la página.
    condiciones = []
    # Filtra por el actor exacto cuando se selecciona un usuario.
    if filtros.usuario_id:
        condiciones.append(Auditoria.usuario_id == filtros.usuario_id)
    # Convierte el comienzo del día chileno a UTC antes de comparar.
    if filtros.fecha_desde:
        condiciones.append(Auditoria.fecha_hora >= _limite_utc(filtros.fecha_desde, False))
    # Usa un límite exclusivo para incluir todo el día hasta las 23:59:59.
    if filtros.fecha_hasta:
        condiciones.append(Auditoria.fecha_hora < _limite_utc(filtros.fecha_hasta, True))
    # El nombre de tabla se compara literalmente para evitar búsquedas ambiguas.
    if filtros.tabla:
        condiciones.append(Auditoria.tabla == filtros.tabla)
    # Filtra por la acción elegida.
    if filtros.accion:
        condiciones.append(Auditoria.accion == filtros.accion)
    # Cuenta el total antes de aplicar la página solicitada.
    total = db.scalar(select(func.count()).select_from(Auditoria).where(*condiciones)) or 0
    # Lee solo la página necesaria y une el nombre público del usuario.
    filas = db.execute(
        select(Auditoria, Usuario.nombre_completo)  # Evento y responsable, nunca sus credenciales.
        .join(Usuario, Auditoria.usuario_id == Usuario.id)  # Todo evento tiene responsable.
        .where(*condiciones)  # Filtros elegidos.
        .order_by(Auditoria.id.desc())  # Primero lo más reciente.
        .offset(offset)  # Salta las páginas anteriores.
        .limit(limite + 1)  # Una fila de más indica si queda otra página.
    ).all()
    # La fila adicional permite informar si existen resultados fuera de la página.
    hay_mas = len(filas) > limite
    # Nunca se devuelve la fila adicional.
    filas = filas[:limite]
    # Prepara los eventos de la respuesta.
    items = []
    # Recorre la página.
    for evento, nombre in filas:
        # Convierte el JSON guardado en campos y quita las credenciales.
        antes, despues = _leer_valores(evento.valores_antes), _leer_valores(evento.valores_despues)
        # Expone únicamente las columnas públicas definidas por el schema.
        items.append(
            {
                "id": evento.id,  # Identificador del evento.
                "fecha_hora": evento.fecha_hora,  # Cuándo, en UTC.
                "usuario_id": evento.usuario_id,  # Quién, por identificador.
                "usuario": nombre,  # Quién, por nombre.
                "tabla": evento.tabla,  # Tabla afectada.
                "registro_id": evento.registro_id,  # Registro afectado.
                "accion": evento.accion,  # Qué operación fue.
                # Solo una modificación tiene valor anterior y valor nuevo del mismo campo.
                "cambios": _cambios(antes, despues) if evento.accion == AccionAuditoria.UPDATE else [],
                # Los datos más recientes del registro; una eliminación solo tiene los anteriores.
                "datos": _datos(despues or antes),
                "motivo": evento.motivo,  # Justificación, si tiene.
            }
        )
    # Devuelve metadatos suficientes para que la pantalla informe paginación.
    return {"items": items, "total": total, "limite": limite, "offset": offset, "hay_mas": hay_mas}


def usuarios_de_bitacora(db: Session) -> list[dict]:
    """Lista actores con id y nombre, sin reutilizar GET /auth/usuarios."""

    # Incluye usuarios activos e inactivos porque ambos pueden tener historial.
    filas = db.execute(
        select(Usuario.id, Usuario.nombre_completo)  # Solo el identificador y el nombre.
        .join(Auditoria, Auditoria.usuario_id == Usuario.id)  # Solo quienes tienen eventos.
        .distinct()  # Una vez por persona.
        .order_by(Usuario.nombre_completo, Usuario.id)  # Orden estable para el selector.
    ).all()
    # Devuelve solo las dos propiedades necesarias para el filtro.
    return [{"id": usuario_id, "nombre_completo": nombre} for usuario_id, nombre in filas]


def tablas_de_bitacora(db: Session) -> list[str]:
    """Lista las tablas que tienen eventos, para llenar el filtro."""

    # Una vez por tabla y en orden alfabético.
    return list(db.scalars(select(Auditoria.tabla).distinct().order_by(Auditoria.tabla)))
