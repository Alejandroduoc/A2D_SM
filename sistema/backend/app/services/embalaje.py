"""Reglas de negocio y auditoría del catálogo de embalajes."""

# Permite reconocer duplicidades informadas por SQL Server.
import re

# Construye consultas con el estilo de SQLAlchemy 2.
from sqlalchemy import select
# Distingue violaciones de restricciones de los demás errores.
from sqlalchemy.exc import IntegrityError
# Representa la sesión compartida por el catálogo y su auditoría.
from sqlalchemy.orm import Session

# Acción registrada en el historial de cambios.
from app.models.auditoria import AccionAuditoria
# Modelo mantenido por este servicio.
from app.models.embalaje import Embalaje
# Usuario autenticado responsable de cada escritura.
from app.models.usuario import Usuario
# Contratos con nombre y kilos ya validados.
from app.schemas.embalaje import EmbalajeCreate, EmbalajeUpdate
# Captura estados y agrega el evento en la misma transacción.
from app.services.auditoria import instantanea, registrar_auditoria


# El router traduce este conflicto de negocio a HTTP 409.
class EmbalajeDuplicadoError(Exception):
    """El nombre pertenece a otro embalaje, aunque esté inactivo."""


# El router traduce esta ausencia concurrente a HTTP 404.
class EmbalajeNoEncontradoError(Exception):
    """El embalaje dejó de existir antes de completar la escritura."""


# Clasifica únicamente la restricción única propia de embalajes.
def _es_nombre_duplicado(error: IntegrityError) -> bool:
    # Obtiene el mensaje original sin entregarlo al consumidor de la API.
    mensaje = str(error.orig)
    # Exige uno de los códigos completos de duplicidad de SQL Server.
    codigo = re.search(r"(?<!\d)(?:2601|2627)(?!\d)", mensaje)
    # Exige además el nombre exacto de la restricción declarada en el modelo.
    restriccion = re.search(
        r"(?<![\w.$@#-])uq_embalajes_nombre(?![\w.$@#-])",
        mensaje,
        re.IGNORECASE,
    )
    # Sólo ambos indicios justifican convertir el error en un duplicado.
    return codigo is not None and restriccion is not None


# Comprueba nombres ocupados entre embalajes activos e inactivos.
def _nombre_ocupado(db: Session, nombre: str, excluir_id: int | None = None) -> bool:
    # La colación CI_AS compara el nombre sin distinguir mayúsculas.
    consulta = select(Embalaje.id).where(Embalaje.nombre == nombre)
    # Una edición puede conservar el nombre del registro actual.
    if excluir_id is not None:
        # Excluye únicamente la identidad modificada.
        consulta = consulta.where(Embalaje.id != excluir_id)
    # Basta con conocer si existe una coincidencia.
    return db.scalar(consulta.limit(1)) is not None


# Lista el catálogo administrativo con filtro opcional de estado.
def listar_embalajes(db: Session, activo: bool | None = None) -> list[Embalaje]:
    # Sin filtro permite consultar activos e inactivos.
    consulta = select(Embalaje)
    # Distingue False de la ausencia de filtro.
    if activo is not None:
        # SQL Server necesita comparación booleana en vez de IS TRUE/IS FALSE.
        consulta = consulta.where(Embalaje.activo == activo)
    # Mantiene un orden estable por nombre e identidad.
    return list(db.scalars(consulta.order_by(Embalaje.nombre, Embalaje.id)).all())


# Obtiene un embalaje de cualquier estado sin escribir ni auditar.
def obtener_embalaje(db: Session, embalaje_id: int) -> Embalaje | None:
    # Devuelve None cuando la identidad no existe.
    return db.get(Embalaje, embalaje_id)


# Recarga y bloquea un embalaje antes de calcular cambios efectivos.
def _obtener_embalaje_bloqueado(db: Session, embalaje_id: int) -> Embalaje | None:
    # Retiene el bloqueo de actualización hasta terminar la transacción.
    consulta = (
        select(Embalaje)
        .where(Embalaje.id == embalaje_id)
        .with_hint(Embalaje, "WITH (UPDLOCK, HOLDLOCK)", dialect_name="mssql")
        .execution_options(populate_existing=True)
    )
    # Entrega el estado vigente o None si desapareció.
    return db.scalar(consulta)


# Crea un embalaje fijo o a granel junto con su auditoría.
def crear_embalaje(db: Session, datos: EmbalajeCreate, usuario: Usuario) -> Embalaje:
    # Protege consulta, inserción, auditoría y confirmación.
    try:
        # Entrega un conflicto comprensible antes de intentar insertar.
        if _nombre_ocupado(db, datos.nombre):
            # Mantiene reservado el nombre aunque el embalaje esté inactivo.
            raise EmbalajeDuplicadoError("Ya existe un embalaje con ese nombre")
        # Conserva kg_por_caja=None cuando la creación corresponde a granel.
        nuevo = Embalaje(**datos.model_dump())
        # Agrega el embalaje a la sesión recibida.
        db.add(nuevo)
        # Obtiene su id y valida restricciones antes de auditar.
        db.flush()
        # Registra la creación sin confirmar por separado.
        registrar_auditoria(
            db,
            usuario.id,
            "embalajes",
            nuevo.id,
            AccionAuditoria.INSERT,
            despues=instantanea(nuevo),
        )
        # Confirma conjuntamente el catálogo y su evento.
        db.commit()
    # También cubre dos altas concurrentes con el mismo nombre.
    except IntegrityError as error:
        # Revierte tanto el registro como cualquier auditoría pendiente.
        db.rollback()
        # Traduce sólo la restricción única de nombres.
        if _es_nombre_duplicado(error):
            # Conserva el error original como causa para diagnóstico.
            raise EmbalajeDuplicadoError("Ya existe un embalaje con ese nombre") from error
        # Propaga cualquier otra violación de integridad.
        raise
    # Reglas de negocio y fallos inesperados también requieren rollback.
    except Exception:
        # Deja la sesión limpia para el llamador.
        db.rollback()
        # Mantiene la excepción original.
        raise
    # Recarga los valores persistidos después de confirmar.
    db.refresh(nuevo)
    # Devuelve el embalaje creado.
    return nuevo


# Edita nombre, kilos o estado y conserva el null explícito para granel.
def actualizar_embalaje(
    db: Session,
    embalaje: Embalaje,
    datos: EmbalajeUpdate,
    usuario: Usuario,
) -> Embalaje:
    # Protege el bloqueo, el cambio y la auditoría hasta confirmar.
    try:
        # Relee el registro bajo bloqueo para evitar ediciones perdidas.
        vigente = _obtener_embalaje_bloqueado(db, embalaje.id)
        # La fila puede haber desaparecido después de la lectura inicial.
        if vigente is None:
            # Permite al router responder 404.
            raise EmbalajeNoEncontradoError("Embalaje no encontrado")
        # Conserva kg_por_caja=None cuando fue enviado explícitamente.
        enviados = datos.model_dump(exclude_unset=True)
        # nombre=None y activo=None significan conservar sus valores actuales.
        enviados = {
            campo: valor
            for campo, valor in enviados.items()
            if campo == "kg_por_caja" or valor is not None
        }
        # Omite asignaciones equivalentes para no generar auditoría vacía.
        cambios = {
            campo: valor
            for campo, valor in enviados.items()
            if getattr(vigente, campo) != valor
        }
        # Una petición sin diferencias no confirma ni audita.
        if not cambios:
            # Devuelve el estado recargado.
            return vigente
        # Verifica la reserva del nombre antes de modificar atributos.
        if "nombre" in cambios and _nombre_ocupado(db, cambios["nombre"], vigente.id):
            # El router lo traduce a conflicto.
            raise EmbalajeDuplicadoError("Ya existe un embalaje con ese nombre")
        # Captura el estado anterior bajo el mismo bloqueo.
        antes = instantanea(vigente)
        # Aplica únicamente los cambios efectivos, incluido null explícito.
        for campo, valor in cambios.items():
            # Los nombres posibles están limitados por el schema.
            setattr(vigente, campo, valor)
        # Valida restricciones y materializa el nuevo estado.
        db.flush()
        # Registra edición, conversión a granel o cambio de estado como UPDATE.
        registrar_auditoria(
            db,
            usuario.id,
            "embalajes",
            vigente.id,
            AccionAuditoria.UPDATE,
            antes=antes,
            despues=instantanea(vigente),
        )
        # Confirma el cambio y su historial juntos.
        db.commit()
    # Cubre renombres concurrentes que superen la preconsulta.
    except IntegrityError as error:
        # Revierte catálogo, auditoría y bloqueo.
        db.rollback()
        # Traduce únicamente la restricción propia del nombre.
        if _es_nombre_duplicado(error):
            # Conserva el diagnóstico original como causa.
            raise EmbalajeDuplicadoError("Ya existe un embalaje con ese nombre") from error
        # Propaga las demás restricciones.
        raise
    # Incluye reglas de negocio y errores inesperados.
    except Exception:
        # Revierte todo antes de propagar.
        db.rollback()
        # Mantiene la excepción original.
        raise
    # Recarga el registro confirmado.
    db.refresh(vigente)
    # Devuelve el embalaje actualizado.
    return vigente
