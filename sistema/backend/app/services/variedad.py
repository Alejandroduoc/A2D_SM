"""Reglas y auditoría de variedades coordinadas mediante su especie."""

# Reconoce únicamente los errores de la restricción de nombres de variedades.
import re

# Construye lecturas y comprobaciones con igualdad compatible con SQL Server.
from sqlalchemy import select
# Distingue conflictos de integridad de los demás errores.
from sqlalchemy.exc import IntegrityError
# La sesión recibida contiene catálogo, bloqueo y evento de auditoría.
from sqlalchemy.orm import Session

# Acciones que admite el historial compartido.
from app.models.auditoria import AccionAuditoria
# Actor autenticado y modelo de la variedad que se mantiene.
from app.models.usuario import Usuario
from app.models.variedad import Variedad
# Contratos sin reasignación de especie durante la edición.
from app.schemas.variedad import VariedadCreate, VariedadUpdate
# Captura y registro de eventos dentro de la misma sesión.
from app.services.auditoria import instantanea, registrar_auditoria
# Comparte el punto de coordinación del padre sin un ciclo entre servicios.
from app.services.especie import EspecieInactivaError, EspecieNoEncontradaError, obtener_especie_bloqueada


# El router posterior traducirá el conflicto de nombre dentro de una especie a 409.
class VariedadDuplicadaError(Exception):
    """El nombre está reservado en esa especie, incluso por una variedad inactiva."""


# Distingue registros ausentes durante una escritura del resultado de una lista vacía.
class VariedadNoEncontradaError(Exception):
    """La variedad ya no existe o no corresponde a la especie bloqueada."""


# Clasifica únicamente el código y la restricción exacta del nombre por especie.
def _es_nombre_duplicado(error: IntegrityError) -> bool:
    # No expone detalles ODBC, SQL ni parámetros al consumidor.
    mensaje = str(error.orig)
    # Requiere un código completo, no un número que simplemente lo contenga.
    codigo = re.search(r"(?<!\d)(?:2601|2627)(?!\d)", mensaje)
    # No acepta nombres con prefijos, sufijos u otros componentes de identificador.
    restriccion = re.search(r"(?<![\w.$@#-])uq_variedades_especie_nombre(?![\w.$@#-])", mensaje, re.IGNORECASE)
    # Un error de FK o un SQLSTATE genérico no equivalen a duplicidad.
    return codigo is not None and restriccion is not None


# La unicidad se consulta en SQL dentro de la especie, incluyendo inactivos.
def _nombre_ocupado(db: Session, especie_id: int, nombre: str, excluir_id: int | None = None) -> bool:
    # Usa la comparación de las columnas CI_AS sin casefold de Python.
    consulta = select(Variedad.id).where(Variedad.especie_id == especie_id, Variedad.nombre == nombre)
    # Permite corregir presentación propia sin confundirla con otro registro.
    if excluir_id is not None:
        # Mantiene el ámbito de los otros ids de la misma especie.
        consulta = consulta.where(Variedad.id != excluir_id)
    # No carga más información que la necesaria para comprobar existencia.
    return db.scalar(consulta.limit(1)) is not None


# Filtra sin confirmar ni añadir eventos, con orden estable entre especies.
def listar_variedades(db: Session, activo: bool | None = None, especie_id: int | None = None) -> list[Variedad]:
    # Sin filtros devuelve todos los registros de ambos estados.
    consulta = select(Variedad)
    # False representa un filtro real de inactivos.
    if activo is not None:
        # Evita IS 0/IS 1, que no es la comparación booleana de SQL Server.
        consulta = consulta.where(Variedad.activo == activo)
    # Una especie sin coincidencias devuelve una lista vacía.
    if especie_id is not None:
        # No exige un detalle de especie para una consulta de listado.
        consulta = consulta.where(Variedad.especie_id == especie_id)
    # Ordena primero por clasificación y después por nombre e identidad.
    return list(db.scalars(consulta.order_by(Variedad.especie_id, Variedad.nombre, Variedad.id)).all())


# El detalle normal incluye inactivos y no adquiere el bloqueo especial.
def obtener_variedad(db: Session, variedad_id: int) -> Variedad | None:
    # El router interpretará None sin que esta lectura genere auditoría.
    return db.get(Variedad, variedad_id)


# Solo se llama después de adquirir el bloqueo de la especie.
def _obtener_variedad_bloqueada(db: Session, variedad_id: int) -> Variedad | None:
    # Recarga los atributos antes de calcular diferencias o capturar instantáneas.
    consulta = (
        select(Variedad)  # Recupera el estado vigente completo de la hija.
        .where(Variedad.id == variedad_id)  # Limita el bloqueo al registro afectado.
        .with_hint(Variedad, "WITH (UPDLOCK, HOLDLOCK)", dialect_name="mssql")  # Retiene el bloqueo hasta terminar la transacción.
        .execution_options(populate_existing=True)  # Descarta atributos precargados que hayan quedado antiguos.
    )  # No confirma ni revierte por su cuenta.
    # Devuelve None si el registro desapareció antes de bloquearlo.
    return db.scalar(consulta)


# Confirma el alta junto con su INSERT después de coordinar el estado del padre.
def crear_variedad(db: Session, datos: VariedadCreate, usuario: Usuario) -> Variedad:
    # Protege consultas, reglas y bloqueos además de la escritura.
    try:
        # Siempre adquiere primero el bloqueo del padre en la sesión recibida.
        especie = obtener_especie_bloqueada(db, datos.especie_id)
        # Una referencia ausente no es una duplicidad de nombre.
        if especie is None:
            # El router posterior responderá 404 sin detalles de SQL.
            raise EspecieNoEncontradaError("Especie no encontrada")
        # No permite habilitar una hija bajo una especie inactiva.
        if not especie.activo:
            # El bloqueo impide una desactivación concurrente entre consulta y commit.
            raise EspecieInactivaError("La especie debe estar activa para habilitar una variedad")
        # Los nombres de variedades inactivas siguen reservados en su especie.
        if _nombre_ocupado(db, especie.id, datos.nombre):
            # El mismo nombre en otra especie sí está permitido.
            raise VariedadDuplicadaError("Ya existe una variedad con ese nombre en la especie")
        # El schema aporta nombre y especie; el modelo asigna activo=True.
        nueva = Variedad(**datos.model_dump())
        # Conserva el registro en la misma sesión que bloqueó el padre.
        db.add(nueva)
        # Obtiene id y estado antes de capturar el alta.
        db.flush()
        # El registrador agrega el evento sin confirmar ni liberar el bloqueo.
        registrar_auditoria(db, usuario.id, "variedades", nueva.id, AccionAuditoria.INSERT, despues=instantanea(nueva))
        # Confirma una única vez catálogo y auditoría.
        db.commit()
    # La restricción compuesta protege también carreras que superen la preconsulta.
    except IntegrityError as error:
        # Revierte antes de clasificar y libera los bloqueos de esta operación.
        db.rollback()
        # Solo la restricción exacta de esta tabla justifica el conflicto de nombre.
        if _es_nombre_duplicado(error):
            # Conserva el diagnóstico como causa sin ponerlo en el mensaje público.
            raise VariedadDuplicadaError("Ya existe una variedad con ese nombre en la especie") from error
        # Propaga otras restricciones, incluida una FK inválida de auditoría.
        raise
    # Incluye reglas de negocio, timeout, deadlock y errores de serialización.
    except Exception:
        # No deja filas parciales ni reintenta escrituras automáticamente.
        db.rollback()
        # El llamador recibirá el error original.
        raise
    # Un error posterior al commit no puede deshacer una confirmación ya realizada.
    db.refresh(nueva)
    # Devuelve las cuatro columnas persistidas de la variedad.
    return nueva


# Corrige datos o estado conservando id y especie, con orden de bloqueos padre-hija.
def actualizar_variedad(db: Session, variedad: Variedad, datos: VariedadUpdate, usuario: Usuario) -> Variedad:
    # También protege la identificación y recarga previa de registros.
    try:
        # La asociación es fija por contrato y sirve para identificar al padre.
        especie_id = variedad.especie_id
        # No adquiere un bloqueo de actualización sobre la hija antes del padre.
        especie = obtener_especie_bloqueada(db, especie_id)
        # No puede escribir si desapareció la referencia de especie.
        if especie is None:
            # Mantiene la excepción de negocio del catálogo padre.
            raise EspecieNoEncontradaError("Especie no encontrada")
        # Solo ahora bloquea y recarga los datos de la variedad.
        vigente = _obtener_variedad_bloqueada(db, variedad.id)
        # Confirma identidad y asociación antes de calcular cambios.
        if vigente is None or vigente.especie_id != especie.id:
            # No reasigna silenciosamente un registro a otro padre.
            raise VariedadNoEncontradaError("Variedad no encontrada en la especie")
        # Los campos nulos conservan datos; False solicita una desactivación.
        enviados = datos.model_dump(exclude_unset=True, exclude_none=True)
        # Compara contra el estado vigente después de esperar ambos bloqueos.
        cambios = {campo: valor for campo, valor in enviados.items() if getattr(vigente, campo) != valor}
        # El llamador debe terminar la transacción para liberar los bloqueos adquiridos.
        if not cambios:
            # No confirma ni genera historial para valores equivalentes.
            return vigente
        # Comprobar otros registros de la misma especie permite cambios de presentación propia.
        if "nombre" in cambios and _nombre_ocupado(db, especie.id, cambios["nombre"], vigente.id):
            # No modifica ningún atributo antes de resolver la duplicidad.
            raise VariedadDuplicadaError("Ya existe una variedad con ese nombre en la especie")
        # Una corrección que deje activa la variedad también exige padre activo.
        if cambios.get("activo", vigente.activo) and not especie.activo:
            # Una variedad que siga inactiva sí puede corregir su nombre bajo padre inactivo.
            raise EspecieInactivaError("La especie debe estar activa para habilitar una variedad")
        # El historial anterior corresponde a los atributos recargados bajo bloqueo.
        antes = instantanea(vigente)
        # El schema impide que estos cambios incluyan especie_id o id.
        for campo, valor in cambios.items():
            # Mantiene identidad y clasificación histórica de la variedad.
            setattr(vigente, campo, valor)
        # Comprueba restricciones reales antes de registrar el evento.
        db.flush()
        # Incluye renombrado, desactivación y reactivación como UPDATE.
        registrar_auditoria(db, usuario.id, "variedades", vigente.id, AccionAuditoria.UPDATE, antes=antes, despues=instantanea(vigente))
        # El commit conjunto es también el punto de liberación del bloqueo de especie.
        db.commit()
    # Maneja conflictos SQL que no fueron visibles en la preconsulta.
    except IntegrityError as error:
        # Revierte catálogo, evento y bloqueos antes de clasificar el conflicto.
        db.rollback()
        # No transforma errores de otras restricciones en nombres duplicados.
        if _es_nombre_duplicado(error):
            # No expone SQL, parámetros ni mensajes ODBC al cliente.
            raise VariedadDuplicadaError("Ya existe una variedad con ese nombre en la especie") from error
        # Conserva el error de integridad original.
        raise
    # Las reglas de estado y los errores de bloqueo también necesitan rollback.
    except Exception:
        # Revierte todo el cambio sin confirmaciones intermedias.
        db.rollback()
        # No reintenta automáticamente ante deadlock o timeout.
        raise
    # Mantiene la recarga fuera del bloque que ya confirmó la operación.
    db.refresh(vigente)
    # Devuelve el registro actualizado con su misma especie e identidad.
    return vigente
