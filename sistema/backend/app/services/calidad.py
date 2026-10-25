"""Reglas de negocio y auditoría del catálogo de calidades."""

# Permite reconocer el código de error y el nombre de la restricción en el mensaje del controlador.
import re

# Construye consultas con el estilo de SQLAlchemy 2.
from sqlalchemy import select
# Distingue las violaciones de restricciones de los demás errores.
from sqlalchemy.exc import IntegrityError
# Anota la sesión que comparte el cambio con su auditoría.
from sqlalchemy.orm import Session

# Acciones que se guardan en cada evento del historial.
from app.models.auditoria import AccionAuditoria
# Modelo del catálogo que consulta y modifica este servicio.
from app.models.calidad import Calidad
# Usuario autenticado que el router entrega como responsable.
from app.models.usuario import Usuario
# Contratos con el nombre ya normalizado.
from app.schemas.calidad import CalidadCreate, CalidadUpdate
# Captura estados y agrega la auditoría a la misma sesión (HU21).
from app.services.auditoria import instantanea, registrar_auditoria


# Señala un nombre ocupado; el router lo traduce a HTTP 409.
class CalidadDuplicadaError(Exception):
    """El nombre ya pertenece a una calidad activa o inactiva."""


# Señala que el registro desapareció entre la búsqueda y la escritura; el router responde 404.
class CalidadNoEncontradaError(Exception):
    """La calidad dejó de existir antes de completar la escritura."""


# Clasifica solo las violaciones de la restricción única de calidades.
def _es_nombre_duplicado(error: IntegrityError) -> bool:
    """Reconoce solamente la restricción única propia de calidades."""
    # Lee el mensaje original de SQL Server sin exponerlo al cliente.
    mensaje = str(error.orig)
    # 2601 y 2627 son los códigos de duplicidad de SQL Server (sin aceptar números que los contengan).
    codigo = re.search(r"(?<!\d)(?:2601|2627)(?!\d)", mensaje)
    # Exige el nombre exacto de la restricción, sin prefijos ni sufijos.
    restriccion = re.search(
        r"(?<![\w.$@#-])uq_calidades_nombre(?![\w.$@#-])",  # Nombre declarado en el modelo.
        mensaje,  # Texto donde se busca.
        re.IGNORECASE,  # SQL Server puede variar las mayúsculas del nombre.
    )  # Finaliza la búsqueda de la restricción.
    # Solo ambos indicios juntos justifican un 409.
    return codigo is not None and restriccion is not None


# Comprueba antes de escribir si otro registro ya usa el nombre.
def _nombre_ocupado(db: Session, nombre: str, excluir_id: int | None = None) -> bool:
    """Consulta ambos estados usando la comparación CI_AS de SQL Server."""
    # Busca cualquier calidad con ese nombre, activa o inactiva.
    consulta = select(Calidad.id).where(Calidad.nombre == nombre)
    # Al editar, excluye el propio registro.
    if excluir_id is not None:
        # Agrega el filtro de identidad distinta.
        consulta = consulta.where(Calidad.id != excluir_id)
    # Basta con encontrar una fila.
    return db.scalar(consulta.limit(1)) is not None


# Lista el catálogo para el mantenimiento administrativo.
def listar_calidades(db: Session, activo: bool | None = None) -> list[Calidad]:
    """Lista calidades en un orden estable y conserva el filtro False."""
    # Parte sin filtro: el administrador puede ver ambos estados.
    consulta = select(Calidad)
    # Distingue False (inactivas) de None (todas).
    if activo is not None:
        # SQL Server traduce la comparación a activo = 0 o 1 (no usar .is_()).
        consulta = consulta.where(Calidad.activo == activo)
    # Ordena por nombre y luego por id para un orden estable.
    return list(db.scalars(consulta.order_by(Calidad.nombre, Calidad.id)).all())


# Busca por clave primaria sin modificar ni auditar.
def obtener_calidad(db: Session, calidad_id: int) -> Calidad | None:
    """Obtiene una calidad de cualquier estado sin modificarla."""
    # Devuelve None si no existe; el router resuelve el 404.
    return db.get(Calidad, calidad_id)


# Relee el registro con bloqueo para que dos ediciones simultáneas no se pisen.
def _obtener_calidad_bloqueada(db: Session, calidad_id: int) -> Calidad | None:
    """Recarga y bloquea el registro hasta terminar la transacción."""
    # Prepara la lectura bloqueante de la fila.
    consulta = (
        select(Calidad)  # Lee la fila completa.
        .where(Calidad.id == calidad_id)  # Solo el registro que se edita.
        .with_hint(Calidad, "WITH (UPDLOCK, HOLDLOCK)", dialect_name="mssql")  # Bloqueo de actualización en SQL Server.
        .execution_options(populate_existing=True)  # Reemplaza los valores en memoria por los de la base.
    )  # Finaliza la consulta.
    # Devuelve la calidad vigente o None si ya no existe.
    return db.scalar(consulta)


# Alta de una calidad con su evento INSERT en la misma transacción.
def crear_calidad(db: Session, datos: CalidadCreate, usuario: Usuario) -> Calidad:
    """Crea la calidad y su auditoría INSERT en una sola transacción."""
    # Protege la consulta previa, la escritura, la auditoría y el commit.
    try:
        # La comprobación previa da un mensaje claro en el caso normal.
        if _nombre_ocupado(db, datos.nombre):
            # El router convierte este error en 409.
            raise CalidadDuplicadaError("Ya existe una calidad con ese nombre")
        # Crea el objeto solo con los campos permitidos por el schema.
        nueva = Calidad(**datos.model_dump())
        # Lo agrega a la sesión recibida.
        db.add(nueva)
        # Obtiene el id y el estado inicial antes de auditar.
        db.flush()
        # Agrega el evento INSERT a la misma transacción.
        registrar_auditoria(
            db,  # Misma sesión del alta.
            usuario.id,  # Responsable autenticado.
            "calidades",  # Tabla afectada.
            nueva.id,  # Id generado por el flush.
            AccionAuditoria.INSERT,  # Creación del registro.
            despues=instantanea(nueva),  # Estado completo creado.
        )  # El registrador no confirma la transacción.
        # Confirma una sola vez la calidad y su auditoría.
        db.commit()
    # El índice único cubre también altas simultáneas que superan la consulta previa.
    except IntegrityError as error:
        # Revierte el cambio y la auditoría pendiente.
        db.rollback()
        # Solo la restricción de nombre se traduce a duplicado.
        if _es_nombre_duplicado(error):
            # Conserva la causa original para diagnóstico.
            raise CalidadDuplicadaError("Ya existe una calidad con ese nombre") from error
        # Otras restricciones se propagan sin cambiarlas.
        raise
    # Cualquier otro fallo también revierte la operación completa.
    except Exception:
        # Deja la sesión limpia antes de propagar.
        db.rollback()
        # Mantiene la excepción original.
        raise
    # Recarga fuera del bloque de escritura ya confirmado.
    db.refresh(nueva)
    # Entrega la calidad persistida al router.
    return nueva


# Edición de nombre o estado con su evento UPDATE.
def actualizar_calidad(
    db: Session,  # Sesión que comparte el cambio con su auditoría.
    calidad: Calidad,  # Registro que el router ya encontró.
    datos: CalidadUpdate,  # Cambios validados y nombre normalizado.
    usuario: Usuario,  # Responsable autenticado.
) -> Calidad:
    """Aplica cambios efectivos y los audita bajo bloqueo del registro."""
    # Protege la lectura bloqueante y toda la escritura previa al commit.
    try:
        # Relee y bloquea la fila para trabajar sobre su estado vigente.
        vigente = _obtener_calidad_bloqueada(db, calidad.id)
        # Puede haber desaparecido después de la búsqueda del router.
        if vigente is None:
            # El router responde 404.
            raise CalidadNoEncontradaError("Calidad no encontrada")
        # Toma solo los campos enviados y no nulos (False se conserva).
        enviados = datos.model_dump(exclude_unset=True, exclude_none=True)
        # Deja solo los valores distintos del estado actual.
        cambios = {
            campo: valor  # Nuevo valor del campo.
            for campo, valor in enviados.items()  # Recorre los campos enviados.
            if getattr(vigente, campo) != valor  # Omite los que no cambian.
        }  # Finaliza la selección de cambios efectivos.
        # Una edición sin diferencias no se confirma ni se audita.
        if not cambios:
            # El bloqueo se libera cuando la sesión de la petición termina.
            return vigente
        # Si cambia el nombre, comprueba que no pertenezca a otra calidad.
        if "nombre" in cambios and _nombre_ocupado(db, cambios["nombre"], vigente.id):
            # El router convierte este error en 409.
            raise CalidadDuplicadaError("Ya existe una calidad con ese nombre")
        # Captura el estado anterior antes de modificar.
        antes = instantanea(vigente)
        # Aplica cada cambio efectivo.
        for campo, valor in cambios.items():
            # Asigna el nuevo valor al atributo correspondiente.
            setattr(vigente, campo, valor)
        # Envía el cambio y valida restricciones antes de auditar.
        db.flush()
        # Agrega el evento UPDATE a la misma transacción.
        registrar_auditoria(
            db,  # Misma sesión de la edición.
            usuario.id,  # Responsable autenticado.
            "calidades",  # Tabla afectada.
            vigente.id,  # Identidad del registro editado.
            AccionAuditoria.UPDATE,  # Renombre, desactivación o reactivación.
            antes=antes,  # Estado anterior completo.
            despues=instantanea(vigente),  # Estado posterior completo.
        )  # El registrador no confirma la transacción.
        # Confirma una sola vez el cambio y su auditoría.
        db.commit()
    # Cubre renombres simultáneos que choquen con la restricción única.
    except IntegrityError as error:
        # Revierte el cambio y la auditoría pendiente.
        db.rollback()
        # Solo la restricción de nombre se traduce a duplicado.
        if _es_nombre_duplicado(error):
            # Conserva la causa original para diagnóstico.
            raise CalidadDuplicadaError("Ya existe una calidad con ese nombre") from error
        # Otras restricciones se propagan sin cambiarlas.
        raise
    # Cualquier otro fallo también revierte la operación completa.
    except Exception:
        # Deja la sesión limpia antes de propagar.
        db.rollback()
        # Mantiene la excepción original.
        raise
    # Recarga fuera del bloque de escritura ya confirmado.
    db.refresh(vigente)
    # Entrega la calidad persistida al router.
    return vigente
