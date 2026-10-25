"""Reglas de negocio y auditoría de sistemas productivos."""

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
from app.models.sistema_productivo import SistemaProductivo
# Usuario autenticado que el router entrega como responsable.
from app.models.usuario import Usuario
# Contratos con el nombre ya normalizado.
from app.schemas.sistema_productivo import SistemaProductivoCreate, SistemaProductivoUpdate
# Captura estados y agrega la auditoría a la misma sesión (HU21).
from app.services.auditoria import instantanea, registrar_auditoria


# Señala un nombre ocupado; el router lo traduce a HTTP 409.
class SistemaProductivoDuplicadoError(Exception):
    """El nombre pertenece a otro sistema productivo, incluso inactivo."""


# Señala que el registro desapareció entre la búsqueda y la escritura; el router responde 404.
class SistemaProductivoNoEncontradoError(Exception):
    """El sistema dejó de existir antes de completar la escritura."""


# Clasifica solo las violaciones de la restricción única de este catálogo.
def _es_nombre_duplicado(error: IntegrityError) -> bool:
    """Reconoce solamente la restricción única propia de este catálogo."""
    # Lee el mensaje original de SQL Server sin exponerlo al cliente.
    mensaje = str(error.orig)
    # 2601 y 2627 son los códigos de duplicidad de SQL Server (sin aceptar números que los contengan).
    codigo = re.search(r"(?<!\d)(?:2601|2627)(?!\d)", mensaje)
    # Exige el nombre exacto de la restricción, sin prefijos ni sufijos.
    restriccion = re.search(
        r"(?<![\w.$@#-])uq_sistemas_productivos_nombre(?![\w.$@#-])",  # Nombre declarado en el modelo.
        mensaje,  # Texto donde se busca.
        re.IGNORECASE,  # SQL Server puede variar las mayúsculas del nombre.
    )  # Finaliza la búsqueda de la restricción.
    # Solo ambos indicios juntos justifican un 409.
    return codigo is not None and restriccion is not None


# Comprueba antes de escribir si otro registro ya usa el nombre.
def _nombre_ocupado(db: Session, nombre: str, excluir_id: int | None = None) -> bool:
    """Consulta activos e inactivos con la colación definida en la tabla."""
    # Busca cualquier sistema productivo con ese nombre, activo o inactivo.
    consulta = select(SistemaProductivo.id).where(SistemaProductivo.nombre == nombre)
    # Al editar, excluye el propio registro.
    if excluir_id is not None:
        # Agrega el filtro de identidad distinta.
        consulta = consulta.where(SistemaProductivo.id != excluir_id)
    # Basta con encontrar una fila.
    return db.scalar(consulta.limit(1)) is not None


# Lista el catálogo para el mantenimiento administrativo.
def listar_sistemas_productivos(
    db: Session,  # Sesión de la petición.
    activo: bool | None = None,  # None = todos; True/False = un estado.
) -> list[SistemaProductivo]:
    """Lista el catálogo completo o el estado solicitado."""
    # Parte sin filtro: el administrador puede ver ambos estados.
    consulta = select(SistemaProductivo)
    # Distingue False (inactivos) de None (todos).
    if activo is not None:
        # SQL Server traduce la comparación a activo = 0 o 1 (no usar .is_()).
        consulta = consulta.where(SistemaProductivo.activo == activo)
    # Devuelve una lista con orden estable.
    return list(
        # Ejecuta la consulta y obtiene los modelos.
        db.scalars(
            # Ordena por nombre y luego por id.
            consulta.order_by(SistemaProductivo.nombre, SistemaProductivo.id),
        ).all(),  # Materializa todos los resultados.
    )  # Finaliza la conversión a lista.


# Busca por clave primaria sin modificar ni auditar.
def obtener_sistema_productivo(
    db: Session,  # Sesión de la petición.
    sistema_productivo_id: int,  # Id solicitado.
) -> SistemaProductivo | None:
    """Obtiene un sistema productivo de cualquier estado."""
    # Devuelve None si no existe; el router resuelve el 404.
    return db.get(SistemaProductivo, sistema_productivo_id)


# Relee el registro con bloqueo para que dos ediciones simultáneas no se pisen.
def _obtener_sistema_productivo_bloqueado(
    db: Session,  # Sesión de la edición.
    sistema_productivo_id: int,  # Registro que se va a editar.
) -> SistemaProductivo | None:
    """Recarga y bloquea el registro durante su actualización."""
    # Prepara la lectura bloqueante de la fila.
    consulta = (
        select(SistemaProductivo)  # Lee la fila completa.
        .where(SistemaProductivo.id == sistema_productivo_id)  # Solo el registro que se edita.
        .with_hint(
            SistemaProductivo,  # Tabla sobre la que aplica el hint.
            "WITH (UPDLOCK, HOLDLOCK)",  # Bloqueo de actualización en SQL Server.
            dialect_name="mssql",  # Solo se aplica en SQL Server.
        )  # Finaliza el hint de bloqueo.
        .execution_options(populate_existing=True)  # Reemplaza los valores en memoria por los de la base.
    )  # Finaliza la consulta.
    # Devuelve el sistema vigente o None si ya no existe.
    return db.scalar(consulta)


# Alta de un sistema productivo con su evento INSERT en la misma transacción.
def crear_sistema_productivo(
    db: Session,  # Sesión que comparte el alta con su auditoría.
    datos: SistemaProductivoCreate,  # Nombre validado y normalizado.
    usuario: Usuario,  # Responsable autenticado.
) -> SistemaProductivo:
    """Crea el sistema y su evento INSERT de forma atómica."""
    # Protege la consulta previa, la escritura, la auditoría y el commit.
    try:
        # La comprobación previa da un mensaje claro en el caso normal.
        if _nombre_ocupado(db, datos.nombre):
            # El router convierte este error en 409.
            raise SistemaProductivoDuplicadoError(
                "Ya existe un sistema productivo con ese nombre",  # Mensaje de negocio.
            )  # Finaliza el error de duplicado.
        # Crea el objeto solo con los campos permitidos por el schema.
        nuevo = SistemaProductivo(**datos.model_dump())
        # Lo agrega a la sesión recibida.
        db.add(nuevo)
        # Obtiene el id y el estado inicial antes de auditar.
        db.flush()
        # Agrega el evento INSERT a la misma transacción.
        registrar_auditoria(
            db,  # Misma sesión del alta.
            usuario.id,  # Responsable autenticado.
            "sistemas_productivos",  # Tabla afectada.
            nuevo.id,  # Id generado por el flush.
            AccionAuditoria.INSERT,  # Creación del registro.
            despues=instantanea(nuevo),  # Estado completo creado.
        )  # El registrador no confirma la transacción.
        # Confirma una sola vez el sistema y su auditoría.
        db.commit()
    # El índice único cubre también altas simultáneas que superan la consulta previa.
    except IntegrityError as error:
        # Revierte el cambio y la auditoría pendiente.
        db.rollback()
        # Solo la restricción de nombre se traduce a duplicado.
        if _es_nombre_duplicado(error):
            # Conserva la causa original para diagnóstico.
            raise SistemaProductivoDuplicadoError(
                "Ya existe un sistema productivo con ese nombre",  # Mensaje de negocio.
            ) from error  # Encadena el error de la base.
        # Otras restricciones se propagan sin cambiarlas.
        raise
    # Cualquier otro fallo también revierte la operación completa.
    except Exception:
        # Deja la sesión limpia antes de propagar.
        db.rollback()
        # Mantiene la excepción original.
        raise
    # Recarga fuera del bloque de escritura ya confirmado.
    db.refresh(nuevo)
    # Entrega el sistema persistido al router.
    return nuevo


# Edición de nombre o estado con su evento UPDATE.
def actualizar_sistema_productivo(
    db: Session,  # Sesión que comparte el cambio con su auditoría.
    sistema_productivo: SistemaProductivo,  # Registro que el router ya encontró.
    datos: SistemaProductivoUpdate,  # Cambios validados y nombre normalizado.
    usuario: Usuario,  # Responsable autenticado.
) -> SistemaProductivo:
    """Aplica cambios efectivos con auditoría y una única confirmación."""
    # Protege la lectura bloqueante y toda la escritura previa al commit.
    try:
        # Relee y bloquea la fila para trabajar sobre su estado vigente.
        vigente = _obtener_sistema_productivo_bloqueado(
            db,  # Misma sesión.
            sistema_productivo.id,  # Registro que se edita.
        )  # Finaliza la lectura bloqueante.
        # Puede haber desaparecido después de la búsqueda del router.
        if vigente is None:
            # El router responde 404.
            raise SistemaProductivoNoEncontradoError(
                "Sistema productivo no encontrado",  # Mensaje de negocio.
            )  # Finaliza el error de no encontrado.
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
        # Si cambia el nombre, comprueba que no pertenezca a otro sistema.
        if "nombre" in cambios and _nombre_ocupado(db, cambios["nombre"], vigente.id):
            # El router convierte este error en 409.
            raise SistemaProductivoDuplicadoError(
                "Ya existe un sistema productivo con ese nombre",  # Mensaje de negocio.
            )  # Finaliza el error de duplicado.
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
            "sistemas_productivos",  # Tabla afectada.
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
            raise SistemaProductivoDuplicadoError(
                "Ya existe un sistema productivo con ese nombre",  # Mensaje de negocio.
            ) from error  # Encadena el error de la base.
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
    # Entrega el sistema persistido al router.
    return vigente
