"""Reglas de negocio y auditoría de tipos de bandeja."""

# Permite reconocer el código y la restricción de duplicidad informados por SQL Server.
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
from app.models.tipo_bandeja import TipoBandeja
# Usuario autenticado responsable de cada escritura.
from app.models.usuario import Usuario
# Contratos con nombre y tara ya validados.
from app.schemas.tipo_bandeja import TipoBandejaCreate, TipoBandejaUpdate
# Captura estados y agrega el evento en la misma transacción.
from app.services.auditoria import instantanea, registrar_auditoria


# El router traduce este conflicto de negocio a HTTP 409.
class TipoBandejaDuplicadoError(Exception):
    """El nombre pertenece a otra bandeja, aunque esté inactiva."""


# El router traduce esta ausencia concurrente a HTTP 404.
class TipoBandejaNoEncontradoError(Exception):
    """La bandeja dejó de existir antes de completar la escritura."""


# Clasifica únicamente la restricción única propia de este catálogo.
def _es_nombre_duplicado(error: IntegrityError) -> bool:
    # Obtiene el mensaje original sin entregarlo al consumidor de la API.
    mensaje = str(error.orig)
    # Exige uno de los códigos completos de duplicidad de SQL Server.
    codigo = re.search(r"(?<!\d)(?:2601|2627)(?!\d)", mensaje)
    # Exige además el nombre exacto de la restricción declarada en el modelo.
    restriccion = re.search(
        r"(?<![\w.$@#-])uq_tipos_bandeja_nombre(?![\w.$@#-])",
        mensaje,
        re.IGNORECASE,
    )
    # Sólo ambos indicios justifican convertir el error en un duplicado.
    return codigo is not None and restriccion is not None


# Comprueba nombres ocupados entre registros activos e inactivos.
def _nombre_ocupado(db: Session, nombre: str, excluir_id: int | None = None) -> bool:
    # La colación CI_AS de la columna resuelve la comparación sin distinguir mayúsculas.
    consulta = select(TipoBandeja.id).where(TipoBandeja.nombre == nombre)
    # Una edición puede conservar el nombre del registro actual.
    if excluir_id is not None:
        # Excluye solamente la identidad que se está modificando.
        consulta = consulta.where(TipoBandeja.id != excluir_id)
    # Basta con conocer si existe una coincidencia.
    return db.scalar(consulta.limit(1)) is not None


# Lista el catálogo administrativo con filtro opcional de estado.
def listar_tipos_bandeja(db: Session, activo: bool | None = None) -> list[TipoBandeja]:
    # Sin filtro permite al administrador consultar ambos estados.
    consulta = select(TipoBandeja)
    # Distingue False de la ausencia de filtro.
    if activo is not None:
        # SQL Server necesita una comparación booleana, no IS TRUE/IS FALSE.
        consulta = consulta.where(TipoBandeja.activo == activo)
    # Mantiene un orden estable por nombre e identidad.
    return list(db.scalars(consulta.order_by(TipoBandeja.nombre, TipoBandeja.id)).all())


# Obtiene una bandeja de cualquier estado sin escribir ni auditar.
def obtener_tipo_bandeja(db: Session, tipo_bandeja_id: int) -> TipoBandeja | None:
    # Devuelve None cuando la identidad no existe.
    return db.get(TipoBandeja, tipo_bandeja_id)


# Recarga y bloquea una bandeja antes de calcular cambios efectivos.
def _obtener_tipo_bandeja_bloqueado(
    db: Session,
    tipo_bandeja_id: int,
) -> TipoBandeja | None:
    # Retiene el bloqueo de actualización hasta terminar la transacción.
    consulta = (
        select(TipoBandeja)
        .where(TipoBandeja.id == tipo_bandeja_id)
        .with_hint(TipoBandeja, "WITH (UPDLOCK, HOLDLOCK)", dialect_name="mssql")
        .execution_options(populate_existing=True)
    )
    # Entrega el estado vigente o None si desapareció.
    return db.scalar(consulta)


# Crea una bandeja y su auditoría como una única operación.
def crear_tipo_bandeja(
    db: Session,
    datos: TipoBandejaCreate,
    usuario: Usuario,
) -> TipoBandeja:
    # Protege consulta, inserción, auditoría y confirmación.
    try:
        # Entrega un conflicto comprensible antes de intentar insertar.
        if _nombre_ocupado(db, datos.nombre):
            # Mantiene reservado el nombre aunque el registro esté inactivo.
            raise TipoBandejaDuplicadoError("Ya existe un tipo de bandeja con ese nombre")
        # Construye el modelo únicamente con los campos admitidos por el schema.
        nuevo = TipoBandeja(**datos.model_dump())
        # Agrega la bandeja a la sesión recibida.
        db.add(nuevo)
        # Obtiene su id y valida restricciones antes de auditar.
        db.flush()
        # Registra la creación sin confirmar por separado.
        registrar_auditoria(
            db,
            usuario.id,
            "tipos_bandeja",
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
            raise TipoBandejaDuplicadoError("Ya existe un tipo de bandeja con ese nombre") from error
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
    # Devuelve la bandeja creada.
    return nuevo


# Edita nombre, tara o estado y audita sólo cambios efectivos.
def actualizar_tipo_bandeja(
    db: Session,
    tipo_bandeja: TipoBandeja,
    datos: TipoBandejaUpdate,
    usuario: Usuario,
) -> TipoBandeja:
    # Protege el bloqueo, el cambio y la auditoría hasta confirmar.
    try:
        # Relee el registro bajo bloqueo para evitar ediciones perdidas.
        vigente = _obtener_tipo_bandeja_bloqueado(db, tipo_bandeja.id)
        # La fila puede haber desaparecido después de la lectura inicial.
        if vigente is None:
            # Permite al router responder 404.
            raise TipoBandejaNoEncontradoError("Tipo de bandeja no encontrado")
        # En este catálogo los valores nulos significan conservar el dato.
        enviados = datos.model_dump(exclude_unset=True, exclude_none=True)
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
            raise TipoBandejaDuplicadoError("Ya existe un tipo de bandeja con ese nombre")
        # Captura el estado anterior bajo el mismo bloqueo.
        antes = instantanea(vigente)
        # Aplica únicamente los cambios efectivos.
        for campo, valor in cambios.items():
            # Los nombres posibles están limitados por el schema.
            setattr(vigente, campo, valor)
        # Valida restricciones y materializa el nuevo estado.
        db.flush()
        # Registra edición, activación o desactivación como UPDATE.
        registrar_auditoria(
            db,
            usuario.id,
            "tipos_bandeja",
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
            raise TipoBandejaDuplicadoError("Ya existe un tipo de bandeja con ese nombre") from error
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
    # Devuelve la bandeja actualizada.
    return vigente
