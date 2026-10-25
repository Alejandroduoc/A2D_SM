"""Reglas de negocio y auditoría del catálogo de calidades."""

import re

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.auditoria import AccionAuditoria
from app.models.calidad import Calidad
from app.models.usuario import Usuario
from app.schemas.calidad import CalidadCreate, CalidadUpdate
from app.services.auditoria import instantanea, registrar_auditoria


class CalidadDuplicadaError(Exception):
    """El nombre ya pertenece a una calidad activa o inactiva."""


class CalidadNoEncontradaError(Exception):
    """La calidad dejó de existir antes de completar la escritura."""


def _es_nombre_duplicado(error: IntegrityError) -> bool:
    """Reconoce solamente la restricción única propia de calidades."""
    mensaje = str(error.orig)
    codigo = re.search(r"(?<!\d)(?:2601|2627)(?!\d)", mensaje)
    restriccion = re.search(
        r"(?<![\w.$@#-])uq_calidades_nombre(?![\w.$@#-])",
        mensaje,
        re.IGNORECASE,
    )
    return codigo is not None and restriccion is not None


def _nombre_ocupado(db: Session, nombre: str, excluir_id: int | None = None) -> bool:
    """Consulta ambos estados usando la comparación CI_AS de SQL Server."""
    consulta = select(Calidad.id).where(Calidad.nombre == nombre)
    if excluir_id is not None:
        consulta = consulta.where(Calidad.id != excluir_id)
    return db.scalar(consulta.limit(1)) is not None


def listar_calidades(db: Session, activo: bool | None = None) -> list[Calidad]:
    """Lista calidades en un orden estable y conserva el filtro False."""
    consulta = select(Calidad)
    if activo is not None:
        consulta = consulta.where(Calidad.activo == activo)
    return list(db.scalars(consulta.order_by(Calidad.nombre, Calidad.id)).all())


def obtener_calidad(db: Session, calidad_id: int) -> Calidad | None:
    """Obtiene una calidad de cualquier estado sin modificarla."""
    return db.get(Calidad, calidad_id)


def _obtener_calidad_bloqueada(db: Session, calidad_id: int) -> Calidad | None:
    """Recarga y bloquea el registro hasta terminar la transacción."""
    consulta = (
        select(Calidad)
        .where(Calidad.id == calidad_id)
        .with_hint(Calidad, "WITH (UPDLOCK, HOLDLOCK)", dialect_name="mssql")
        .execution_options(populate_existing=True)
    )
    return db.scalar(consulta)


def crear_calidad(db: Session, datos: CalidadCreate, usuario: Usuario) -> Calidad:
    """Crea la calidad y su auditoría INSERT en una sola transacción."""
    try:
        if _nombre_ocupado(db, datos.nombre):
            raise CalidadDuplicadaError("Ya existe una calidad con ese nombre")
        nueva = Calidad(**datos.model_dump())
        db.add(nueva)
        db.flush()
        registrar_auditoria(
            db,
            usuario.id,
            "calidades",
            nueva.id,
            AccionAuditoria.INSERT,
            despues=instantanea(nueva),
        )
        db.commit()
    except IntegrityError as error:
        db.rollback()
        if _es_nombre_duplicado(error):
            raise CalidadDuplicadaError("Ya existe una calidad con ese nombre") from error
        raise
    except Exception:
        db.rollback()
        raise
    db.refresh(nueva)
    return nueva


def actualizar_calidad(
    db: Session,
    calidad: Calidad,
    datos: CalidadUpdate,
    usuario: Usuario,
) -> Calidad:
    """Aplica cambios efectivos y los audita bajo bloqueo del registro."""
    try:
        vigente = _obtener_calidad_bloqueada(db, calidad.id)
        if vigente is None:
            raise CalidadNoEncontradaError("Calidad no encontrada")
        enviados = datos.model_dump(exclude_unset=True, exclude_none=True)
        cambios = {
            campo: valor
            for campo, valor in enviados.items()
            if getattr(vigente, campo) != valor
        }
        if not cambios:
            return vigente
        if "nombre" in cambios and _nombre_ocupado(db, cambios["nombre"], vigente.id):
            raise CalidadDuplicadaError("Ya existe una calidad con ese nombre")
        antes = instantanea(vigente)
        for campo, valor in cambios.items():
            setattr(vigente, campo, valor)
        db.flush()
        registrar_auditoria(
            db,
            usuario.id,
            "calidades",
            vigente.id,
            AccionAuditoria.UPDATE,
            antes=antes,
            despues=instantanea(vigente),
        )
        db.commit()
    except IntegrityError as error:
        db.rollback()
        if _es_nombre_duplicado(error):
            raise CalidadDuplicadaError("Ya existe una calidad con ese nombre") from error
        raise
    except Exception:
        db.rollback()
        raise
    db.refresh(vigente)
    return vigente
