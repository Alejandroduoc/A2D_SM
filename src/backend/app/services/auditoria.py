"""
El servicio de negocio proporciona la sesión, captura los estados y controla
el flush, el commit y el rollback de sus cambios y de la auditoría asociada.
"""

# Convierte las instantáneas a texto JSON para conservarlas en la auditoría.
import json

# Permite anotar modelos y valores de columnas de distintos tipos.
from typing import Any

# Representa la sesión que recibe el servicio desde la operación de negocio.
from sqlalchemy.orm import Session

# Acción permitida y modelo donde se almacena cada evento de auditoría.
from app.models.auditoria import AccionAuditoria, Auditoria


# Captura las columnas del objeto, omitiendo los atributos indicados.
def instantanea(objeto: Any, excluir: frozenset[str] | set[str] = frozenset()) -> dict[str, Any]:
    """Devuelve los valores de las columnas, sin incluir relaciones del ORM.

    Al capturar usuarios, el llamador debe excluir password_hash.
    Los valores mutables de futuras columnas necesitarán una copia propia.
    """
    # Crea un diccionario independiente para esta captura del estado.
    valores: dict[str, Any] = {}  # Recorre las columnas del modelo sin acceder a detalles internos del ORM.
    for columna in objeto.__table__.columns:
        nombre = columna.key # Obtiene el nombre del atributo que corresponde a la columna.
        if nombre in excluir: # Omite atributos sensibles o ajenos al historial de la operación.
            continue # Continúa con la siguiente columna sin copiar este atributo.
        # Lee el atributo del modelo y lo incorpora a la instantánea.
        valores[nombre] = getattr(objeto, nombre)
    # Entrega el estado capturado al servicio que realiza la operación.
    return valores


# Serializa una instantánea y conserva la diferencia entre None y un dict vacío.
def _a_json(valores: dict[str, Any] | None) -> str | None:
    """Conserva Unicode y representa como texto fechas y otros tipos no JSON."""
    # La ausencia de instantánea debe guardarse como NULL, no como texto JSON.
    if valores is None:
        # Mantiene el valor nulo que espera el modelo de auditoría.
        return None
    # Conserva tildes y ñ; default=str convierte fechas y Decimal a texto.
    return json.dumps(valores, ensure_ascii=False, default=str)


# Agrega el evento a la misma sesión que contiene los cambios de negocio.
def registrar_auditoria(
    db: Session,  # Sesión existente cuya transacción controla el llamador.
    usuario_id: str,  # Identificador del usuario responsable de la operación.
    tabla: str,  # Tabla de negocio definida por el servicio que registra el cambio.
    registro_id: int | str,  # Identificador entero o textual del registro afectado.
    accion: AccionAuditoria,  # Acción correspondiente a la operación de negocio.
    antes: dict[str, Any] | None = None,  # Estado anterior, sin datos sensibles.
    despues: dict[str, Any] | None = None,  # Estado posterior, sin datos sensibles.
    motivo: str | None = None,  # Justificación cuando el negocio la requiere.
) -> Auditoria:
    """Prepara y agrega un evento sin confirmar, revertir ni hacer flush.

    El llamador debe entregar instantáneas sin contraseñas ni hashes y validar
    el motivo cuando la operación lo exija. El modelo genera id y fecha_hora
    al insertar mediante el flush del llamador.
    """
    # Construye el evento sin asignar los campos generados al insertar.
    auditoria = Auditoria(
        usuario_id=usuario_id,  # Conserva la identidad del responsable.
        tabla=tabla,  # Identifica la tabla afectada por el cambio.
        registro_id=str(registro_id),  # Unifica ids enteros y UUID como texto.
        accion=accion,  # Conserva la acción indicada por la operación.
        valores_antes=_a_json(antes),  # Serializa el estado previo o conserva NULL.
        valores_despues=_a_json(despues),  # Serializa el estado posterior o conserva NULL.
        motivo=motivo,  # Conserva el motivo sin exigirlo para todas las acciones.
    )  # Finaliza la preparación del evento de auditoría.
    # Añade el evento a la sesión recibida para compartir su transacción.
    db.add(auditoria)
    # Devuelve la misma instancia para que el llamador pueda consultarla.
    return auditoria
