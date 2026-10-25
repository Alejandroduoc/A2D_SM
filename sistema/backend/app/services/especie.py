"""Reglas y auditoría de especies con coordinación de escrituras HU08."""

# Reconoce códigos completos y nombres exactos en errores de SQL Server.
import re

# Construye consultas compatibles con SQLAlchemy 2 y SQL Server.
from sqlalchemy import select
# Distingue duplicidad de otras restricciones de integridad.
from sqlalchemy.exc import IntegrityError
# Recibe la sesión cuya transacción contiene cambio y auditoría.
from sqlalchemy.orm import Session

# Acciones válidas del historial compartido de la aplicación.
from app.models.auditoria import AccionAuditoria
# Modelos necesarios para mantener el padre y consultar hijas activas.
from app.models.especie import Especie
from app.models.variedad import Variedad
# Actor autenticado proporcionado por el futuro router.
from app.models.usuario import Usuario
# Contratos de alta y cambios parciales ya normalizados.
from app.schemas.especie import EspecieCreate, EspecieUpdate
# Captura columnas y agrega eventos sin terminar la transacción.
from app.services.auditoria import instantanea, registrar_auditoria


# El router traducirá este conflicto a 409 sin exponer el error SQL.
class EspecieDuplicadaError(Exception):
    """El nombre está reservado por otra especie, incluso inactiva."""


# Distingue una referencia ausente durante una escritura de negocio.
class EspecieNoEncontradaError(Exception):
    """La especie ya no existe o la referencia no corresponde a un registro."""


# Impide habilitar hijas cuando su especie no está disponible.
class EspecieInactivaError(Exception):
    """Una variedad activa requiere una especie activa."""


# Conserva la coherencia del padre y las variedades que dependen de él.
class EspecieConVariedadesActivasError(Exception):
    """No se puede desactivar una especie que tenga variedades activas."""


# Clasifica solo la restricción de nombre de este catálogo.
def _es_nombre_duplicado(error: IntegrityError) -> bool:
    # No imprime SQL, parámetros ni mensajes del controlador.
    mensaje = str(error.orig)
    # No confunde un número mayor con un código de duplicidad completo.
    codigo = re.search(r"(?<!\d)(?:2601|2627)(?!\d)", mensaje)
    # Excluye nombres con prefijos, sufijos u otros componentes de identificador.
    restriccion = re.search(r"(?<![\w.$@#-])uq_especies_nombre(?![\w.$@#-])", mensaje, re.IGNORECASE)
    # Ambas condiciones son necesarias; SQLSTATE 23000 por sí solo no basta.
    return codigo is not None and restriccion is not None


# Consulta duplicidad con la intercalación de SQL, incluyendo especies inactivas.
def _nombre_ocupado(db: Session, nombre: str, excluir_id: int | None = None) -> bool:
    # Compara el nombre ya preparado por el schema sin casefold de Python.
    consulta = select(Especie.id).where(Especie.nombre == nombre)
    # Una corrección de presentación no entra en conflicto consigo misma.
    if excluir_id is not None:
        # Mantiene el ámbito de todos los demás registros.
        consulta = consulta.where(Especie.id != excluir_id)
    # Solo necesita saber si existe un registro, sin cargar todo el catálogo.
    return db.scalar(consulta.limit(1)) is not None


# Las lecturas normales no bloquean especialmente ni generan auditoría.
def listar_especies(db: Session, activo: bool | None = None) -> list[Especie]:
    # Incluye ambos estados cuando no se solicita un filtro.
    consulta = select(Especie)
    # False debe filtrar inactivos, no confundirse con la ausencia de filtro.
    if activo is not None:
        # La igualdad genera activo = 0 o activo = 1 en SQL Server.
        consulta = consulta.where(Especie.activo == activo)
    # Proporciona un orden estable al mantenimiento.
    return list(db.scalars(consulta.order_by(Especie.nombre, Especie.id)).all())


# Incluye registros inactivos y devuelve None cuando falta el id solicitado.
def obtener_especie(db: Session, especie_id: int) -> Especie | None:
    # No confirma, modifica ni audita una consulta de detalle.
    return db.get(Especie, especie_id)


# Punto común de coordinación para actualizar especies y escribir variedades.
def obtener_especie_bloqueada(db: Session, especie_id: int) -> Especie | None:
    # Siempre consulta y recarga antes de aplicar cambios a la instancia.
    consulta = (
        select(Especie)  # Recupera el estado vigente completo del padre.
        .where(Especie.id == especie_id)  # Limita el bloqueo a la especie afectada.
        .with_hint(Especie, "WITH (UPDLOCK, HOLDLOCK)", dialect_name="mssql")  # Mantiene el bloqueo hasta terminar la transacción.
        .execution_options(populate_existing=True)  # Sustituye atributos precargados que podrían estar antiguos.
    )  # No crea otra sesión ni termina una transacción existente.
    # El llamador decide cuándo confirmar o revertir el conjunto de negocio.
    return db.scalar(consulta)


# Crea una especie y su evento INSERT en una única transacción.
def crear_especie(db: Session, datos: EspecieCreate, usuario: Usuario) -> Especie:
    # Incluye consultas y validaciones previas en el control de rollback.
    try:
        # Los registros inactivos también reservan su nombre.
        if _nombre_ocupado(db, datos.nombre):
            # El router posterior traducirá esta excepción de negocio a 409.
            raise EspecieDuplicadaError("Ya existe una especie con ese nombre")
        # El modelo asigna activo=True y la base genera el id.
        nueva = Especie(**datos.model_dump())
        # Agrega el catálogo a la sesión compartida.
        db.add(nueva)
        # Obtiene identidad y estado inicial antes de capturar el evento.
        db.flush()
        # El registrador agrega el historial sin confirmar por su cuenta.
        registrar_auditoria(
            db, usuario.id, "especies", nueva.id, AccionAuditoria.INSERT,
            despues=instantanea(nueva),  # Conserva las tres columnas del alta.
        )  # Catálogo e historial se confirman juntos.
        # La restricción única resuelve también carreras que superen la preconsulta.
        db.commit()
    # No convierte otras restricciones en conflictos de nombre.
    except IntegrityError as error:
        # Revierte catálogo y evento antes de clasificar.
        db.rollback()
        # Solo el código de duplicidad y la restricción exacta justifican 409.
        if _es_nombre_duplicado(error):
            # Conserva el diagnóstico original como causa, fuera del mensaje público.
            raise EspecieDuplicadaError("Ya existe una especie con ese nombre") from error
        # Propaga, por ejemplo, una FK inválida de auditoría.
        raise
    # Incluye errores de negocio, bloqueo, auditoría, timeout y deadlock.
    except Exception:
        # No deja cambios parciales ni reintenta automáticamente.
        db.rollback()
        # Conserva el error para la capa superior.
        raise
    # Un fallo posterior a la confirmación no se presenta como rollback del commit.
    db.refresh(nueva)
    # Devuelve el estado persistido del catálogo.
    return nueva


# Renombra o cambia el estado después de recargar bajo bloqueo de especie.
def actualizar_especie(db: Session, especie: Especie, datos: EspecieUpdate, usuario: Usuario) -> Especie:
    # Protege también la espera del bloqueo y las reglas anteriores a modificar.
    try:
        # No usa la instantánea potencialmente antigua recibida del router.
        vigente = obtener_especie_bloqueada(db, especie.id)
        # El registro podría haber desaparecido desde su consulta inicial.
        if vigente is None:
            # No construye una actualización ni un evento sobre una identidad ausente.
            raise EspecieNoEncontradaError("Especie no encontrada")
        # Mantiene False y omite campos no enviados o marcados como conservar.
        enviados = datos.model_dump(exclude_unset=True, exclude_none=True)
        # Calcula diferencias únicamente contra el registro recargado.
        cambios = {campo: valor for campo, valor in enviados.items() if getattr(vigente, campo) != valor}
        # El bloqueo permanece hasta que el llamador cierre o termine su transacción.
        if not cambios:
            # No confirma ni audita una operación sin diferencias.
            return vigente
        # La igualdad SQL excluye el propio id y conserva las reglas CI_AS.
        if "nombre" in cambios and _nombre_ocupado(db, cambios["nombre"], vigente.id):
            # No aplica cambios parciales antes de resolver el conflicto.
            raise EspecieDuplicadaError("Ya existe una especie con ese nombre")
        # Solo una transición efectiva a inactiva necesita comprobar las hijas.
        if cambios.get("activo") is False:
            # El bloqueo del padre coordina esta consulta con todas las escrituras de variedades.
            hija_activa = db.scalar(select(Variedad.id).where(Variedad.especie_id == vigente.id, Variedad.activo == True).limit(1))
            # No desactiva hijas automáticamente ni guarda un renombrado parcial.
            if hija_activa is not None:
                # Rechaza la operación completa mientras exista una variedad activa.
                raise EspecieConVariedadesActivasError("No se puede desactivar una especie con variedades activas")
        # Captura el estado actual, no el anterior a la espera del bloqueo.
        antes = instantanea(vigente)
        # Aplica exclusivamente los cambios permitidos por el schema.
        for campo, valor in cambios.items():
            # Mantiene identidad y relaciones de la especie.
            setattr(vigente, campo, valor)
        # Verifica restricciones antes de preparar el historial.
        db.flush()
        # Desactivación y reactivación también son modificaciones UPDATE.
        registrar_auditoria(db, usuario.id, "especies", vigente.id, AccionAuditoria.UPDATE, antes=antes, despues=instantanea(vigente))
        # Confirma una sola vez el cambio y la auditoría bajo el mismo bloqueo.
        db.commit()
    # Incluye conflictos de unicidad aparecidos después de la preconsulta.
    except IntegrityError as error:
        # Libera el bloqueo y revierte todo el cambio antes de clasificar.
        db.rollback()
        # No confunde una restricción ajena con el nombre de especie.
        if _es_nombre_duplicado(error):
            # El mensaje público no incluye SQL ni parámetros.
            raise EspecieDuplicadaError("Ya existe una especie con ese nombre") from error
        # Conserva el error de integridad original.
        raise
    # Las excepciones de negocio también deben terminar la operación pendiente.
    except Exception:
        # No libera anticipadamente el bloqueo con un commit intermedio.
        db.rollback()
        # Propaga sin reintentos automáticos.
        raise
    # Recarga fuera del bloque de rollback de una escritura ya confirmada.
    db.refresh(vigente)
    # Conserva el mismo id y las variedades existentes.
    return vigente
