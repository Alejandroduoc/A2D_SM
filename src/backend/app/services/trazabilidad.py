"""Recorrido completo de una tarja de recepción, de solo lectura (HU23)."""

# Lee los valores que guarda la auditoría.
import json
# Pone con coma los kilos de los motivos guardados.
import re
# Compara y resta pesos exactos.
from decimal import Decimal, InvalidOperation

# Consultas de lectura.
from sqlalchemy import or_, select
# Sesión de la petición.
from sqlalchemy.orm import Session

# Eventos de la auditoría y sus acciones.
from app.models.auditoria import AccionAuditoria, Auditoria
# Embalaje de cada proceso.
from app.models.embalaje import Embalaje
# Entradas de bandejas de la tarja.
from app.models.movimiento_bandeja import MovimientoBandeja
# Procesos en que entró la tarja.
from app.models.proceso import Proceso, ProcesoTarja
# Tarja y sus estados.
from app.models.tarja import EstadoTarja, Tarja
# Nombre del responsable de cada proceso y de cada cambio.
from app.models.usuario import Usuario
# Datos de la tarja con los nombres de sus catálogos y sus kilos.
from app.services.tarja import obtener_tarja


# Nombres visibles de los campos que pueden cambiar.
ETIQUETAS_CAMPO = {
    "estado": "Estado",
    "merma_rebajada": "Merma rebajada",
    "veces_impresa": "Veces impresa",
    "cantidad_cajas": "Cajas",
    "kilos_procesados": "Kilos procesados",
    "tarja_terminada": "Tarja terminada",
    "anulado": "Anulado",
}
# Nombres visibles de los estados de una tarja.
TEXTO_ESTADO = {
    "RECEPCIONADA": "Recepcionada",
    "PARCIAL": "Parcial",
    "PROCESADA": "Procesada",
    "ANULADA": "Anulada",
}
# Cantidad bien escrita; "007" no lo es: es un texto, aunque valga lo mismo que "7".
_NUMERO = re.compile(r"-?(0|[1-9]\d*)(\.\d+)?([eE][+-]?\d+)?")


# Kilos con dos decimales y coma: 400.00 pasa a 400,00.
def _kilos(valor) -> str:
    # La auditoría guarda los decimales como texto.
    return str(Decimal(str(valor)).quantize(Decimal("0.01"))).replace(".", ",")


# Cajas sin ceros que no aportan y con coma: 40.00 pasa a 40 y 38.50 a 38,5.
def _cajas(valor) -> str:
    # Solo un número con decimales tiene ceros de sobra.
    texto = str(valor).rstrip("0").rstrip(".") if "." in str(valor) else str(valor)
    # Usa la coma de Chile.
    return texto.replace(".", ",")


# Devuelve el valor como se lee en pantalla.
def texto_valor(campo: str, valor) -> str | None:
    # Sin valor no hay texto.
    if valor is None:
        return None
    # Un booleano se lee mejor con palabras.
    if isinstance(valor, bool):
        return "Sí" if valor else "No"
    # Una lista, como los roles de un usuario, se lee separada por comas.
    if isinstance(valor, list):
        return ", ".join(str(elemento) for elemento in valor)
    # Los kilos llevan dos decimales.
    if campo == "kilos_procesados":
        return _kilos(valor)
    # Las cajas, sin ceros de sobra.
    if campo == "cantidad_cajas":
        return _cajas(valor)
    # Traduce solo el estado: otro campo puede contener esa misma palabra como texto.
    if campo == "estado":
        return TEXTO_ESTADO.get(str(valor), str(valor))
    # Los demás valores quedan igual.
    return str(valor)


# Indica si dos valores guardados representan lo mismo: "15.00" y "15" son la misma cantidad.
def valores_iguales(antes, despues) -> bool:
    # Mismo valor exacto.
    if antes == despues:
        return True
    # Un booleano no se compara como número.
    if isinstance(antes, bool) or isinstance(despues, bool):
        return False
    # Si alguno no es una cantidad bien escrita, son distintos.
    if not (_NUMERO.fullmatch(str(antes)) and _NUMERO.fullmatch(str(despues))):
        return False
    # Compara como cantidades.
    try:
        return Decimal(str(antes)) == Decimal(str(despues))
    # Un exponente imposible, como "1e99999999999999999999", no es una cantidad.
    except InvalidOperation:
        return False


# Lista los campos conocidos que cambiaron en un evento.
def _cambios(antes: dict, despues: dict) -> list[dict]:
    # Prepara el resultado.
    cambios = []
    # Solo los campos con nombre visible: la hora de impresión ya se explica en el motivo.
    for campo, etiqueta in ETIQUETAS_CAMPO.items():
        # Si el campo no está en el evento, no se informa.
        if campo not in antes or campo not in despues:
            continue
        # Agrega los que cambiaron.
        if not valores_iguales(antes[campo], despues[campo]):
            cambios.append({"campo": etiqueta, "antes": texto_valor(campo, antes[campo]), "despues": texto_valor(campo, despues[campo])})
    # Entrega los cambios.
    return cambios


# Lee un JSON guardado por la auditoría.
def _leer(valor: str | None) -> dict:
    # Sin instantánea, un diccionario vacío.
    return json.loads(valor) if valor else {}


# Describe en una frase lo que pasó en un evento.
def _descripcion(evento: Auditoria, antes: dict, despues: dict, folios: dict[int, str]) -> str:
    # Eventos de la tarja.
    if evento.tabla == "tarjas":
        # El alta se describe; los demás cambios tienen su motivo.
        if evento.accion == AccionAuditoria.INSERT:
            return "Tarja registrada"
        # Impresión, merma, edición o anulación de un proceso, con los kilos en coma.
        if evento.motivo:
            return re.sub(r"(\d)\.(\d{2}) kg", r"\1,\2 kg", evento.motivo)
        # La anulación de la tarja no lleva motivo.
        if despues.get("estado") == EstadoTarja.ANULADA.value:
            return "Tarja anulada"
        # El estado cambia cuando entra a un proceso.
        return "Cambió el estado de la tarja" if antes.get("estado") != despues.get("estado") else "Tarja modificada"
    # Eventos de sus bandejas.
    if evento.tabla == "movimientos_bandeja":
        # Una tarja genera una sola entrada.
        if evento.accion == AccionAuditoria.INSERT:
            return f"Entrada de {despues.get('cantidad')} bandejas"
        # Lo único que cambia después es la anulación.
        return "Entrada de bandejas anulada"
    # Cabecera de un proceso: solo se muestra su anulación.
    if evento.tabla == "procesos":
        return f"Proceso {folios.get(int(evento.registro_id), evento.registro_id)} anulado"
    # Eventos de su fila en un proceso: la clave es "proceso:tarja".
    folio = folios.get(int(evento.registro_id.split(":")[0]), "desconocido")
    # Entró al proceso.
    if evento.accion == AccionAuditoria.INSERT:
        return f"Entró al proceso {folio}: {_cajas(despues.get('cantidad_cajas'))} cajas y {_kilos(despues.get('kilos_procesados'))} kg"
    # La quitaron del proceso y sus kilos volvieron.
    if evento.accion == AccionAuditoria.DELETE:
        return f"Salió del proceso {folio}: volvieron {_kilos(antes.get('kilos_procesados'))} kg"
    # Cambiaron sus cajas, sus kilos o su marca.
    return f"Cambió en el proceso {folio}"


# Reúne el historial de la tarja, en orden de ocurrencia (HU23 criterio 2).
def _historial(db: Session, tarja_id: int) -> list[dict]:
    # Movimientos de bandejas que generó la tarja.
    movimientos = [str(i) for i in db.scalars(select(MovimientoBandeja.id).where(MovimientoBandeja.tarja_id == tarja_id))]
    # Eventos de la tarja, de sus bandejas y de sus filas de proceso, también de las ya quitadas.
    consulta = (
        select(Auditoria, Usuario.nombre_completo)  # Evento y responsable, nunca sus credenciales.
        .join(Usuario, Auditoria.usuario_id == Usuario.id)  # Todo evento tiene responsable.
        .where(
            or_(
                (Auditoria.tabla == "tarjas") & (Auditoria.registro_id == str(tarja_id)),  # La tarja.
                (Auditoria.tabla == "movimientos_bandeja") & Auditoria.registro_id.in_(movimientos),  # Sus bandejas.
                (Auditoria.tabla == "proceso_tarjas") & Auditoria.registro_id.like(f"%:{tarja_id}"),  # Sus filas: "proceso:tarja".
            )  # Finaliza las condiciones.
        )  # Finaliza el filtro.
    )  # Finaliza la consulta.
    # Lee los eventos.
    filas = db.execute(consulta).all()
    # Procesos en que estuvo, incluidos los que ya no tienen su fila.
    ids_proceso = {int(fila.Auditoria.registro_id.split(":")[0]) for fila in filas if fila.Auditoria.tabla == "proceso_tarjas"}
    # Sus folios.
    folios = dict(db.execute(select(Proceso.id, Proceso.folio).where(Proceso.id.in_(ids_proceso))).all())
    # Anular un proceso puede no cambiar el estado de la tarja: su evento también es parte del recorrido.
    filas_proceso = db.execute(
        select(Auditoria, Usuario.nombre_completo)  # Evento y responsable.
        .join(Usuario, Auditoria.usuario_id == Usuario.id)  # Todo evento tiene responsable.
        .where(
            Auditoria.tabla == "procesos",  # Cabeceras.
            Auditoria.registro_id.in_([str(i) for i in ids_proceso]),  # De sus procesos.
            Auditoria.accion == AccionAuditoria.UPDATE,  # El alta ya se ve en la fila de la tarja.
        )  # Finaliza los filtros.
    ).all()  # Devuelve todos.
    # Prepara el resultado.
    historial = []
    # Recorre los eventos en orden de ocurrencia.
    for fila in sorted(list(filas) + list(filas_proceso), key=lambda f: f.Auditoria.id):
        # Evento.
        evento = fila.Auditoria
        # Valores guardados.
        antes, despues = _leer(evento.valores_antes), _leer(evento.valores_despues)
        # De la cabecera solo importa la anulación: los totales se ven en la fila de la tarja.
        if evento.tabla == "procesos" and not (despues.get("anulado") and not antes.get("anulado")):
            continue
        # Agrega el evento.
        historial.append({
            "fecha_hora": evento.fecha_hora,  # Cuándo, en UTC.
            "usuario": fila.nombre_completo,  # Quién.
            "descripcion": _descripcion(evento, antes, despues, folios),  # Qué pasó.
            # Lo que cambió: el alta y la salida ya se explican en la descripción.
            "cambios": _cambios(antes, despues) if evento.accion == AccionAuditoria.UPDATE else [],
        })  # Finaliza el evento.
    # Entrega el historial.
    return historial


# Obtiene el recorrido completo de una tarja por su número (HU23 criterio 1).
def trazabilidad_tarja(db: Session, numero_tarja: int) -> dict | None:
    # Busca la tarja por el número que conoce el usuario.
    tarja_id = db.scalar(select(Tarja.id).where(Tarja.numero_tarja == numero_tarja))
    # Devuelve None si no existe; el router resuelve el 404.
    if tarja_id is None:
        return None
    # Datos de la recepción, con sus catálogos y sus kilos.
    tarja = obtener_tarja(db, tarja_id)
    # Procesos en que entró, también los anulados: son parte de su recorrido.
    procesos = db.execute(
        select(
            ProcesoTarja.cantidad_cajas,  # Resultado: cajas.
            ProcesoTarja.kilos_procesados,  # Resultado: kilos.
            ProcesoTarja.tarja_terminada,  # Marca del operador.
            Proceso.id,  # Identificador del proceso.
            Proceso.folio,  # Folio.
            Proceso.fecha_elaboracion,  # Día de elaboración.
            Proceso.anulado,  # Un proceso anulado no cuenta.
            Embalaje.nombre.label("embalaje"),  # Nombre del embalaje.
            Usuario.nombre_completo.label("registrado_por"),  # Solo el nombre.
        )  # Finaliza las columnas.
        .join(Proceso, ProcesoTarja.proceso_id == Proceso.id)  # Une con la cabecera.
        .join(Embalaje, Proceso.embalaje_id == Embalaje.id)  # Y con su embalaje.
        .join(Usuario, Proceso.usuario_id == Usuario.id)  # Y con quien lo registró.
        .where(ProcesoTarja.tarja_id == tarja_id)  # Solo esta tarja.
        .order_by(Proceso.id)  # Orden de registro.
    ).all()  # Devuelve todos.
    # Una tarja anulada no tiene merma; en las demás es lo que no salió en cajas.
    merma = None if tarja["estado"] == EstadoTarja.ANULADA.value else Decimal(tarja["kilos_netos"]) - tarja["kilos_procesados"]
    # Reúne el recorrido.
    return {
        "tarja": tarja,  # Productor y datos de la recepción.
        "merma": merma,  # Calculada, nunca guardada.
        "merma_provisional": tarja["estado"] != EstadoTarja.PROCESADA.value,  # Definitiva solo si terminó.
        "procesos": [dict(proceso._mapping) for proceso in procesos],  # Sus procesos.
        "historial": _historial(db, tarja_id),  # Sus cambios.
    }  # Finaliza la respuesta.
