"""Reglas de negocio y auditoría de sistemas productivos."""

import re

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.auditoria import AccionAuditoria
from app.models.sistema_productivo import SistemaProductivo
from app.models.usuario import Usuario
from app.schemas.sistema_productivo import SistemaProductivoCreate, SistemaProductivoUpdate
from app.services.auditoria import instantanea, registrar_auditoria


class SistemaProductivoDuplicadoError(Exception):
    """El nombre pertenece a otro sistema productivo, incluso inactivo."""


class SistemaProductivoNoEncontradoError(Exception):
    """El sistema dejó de existir antes de completar la escritura."""


def _es_nombre_duplicado(error: IntegrityError) -> bool:
    """Reconoce solamente la restricción única propia de este catálogo."""
    mensaje = str(error.orig)
    codigo = re.search(r"(?<!\d)(?:2601|2627)(?!\d)", mensaje)
    restriccion = re.search(
        r"(?<![\w.$@#-])uq_sistemas_productivos_nombre(?![\w.$@#-])",
        mensaje,
        re.IGNORECASE,
    )
    return codigo is not None and restriccion is not None


def _nombre_ocupado(db: Session, nombre: str, excluir_id: int | None = None) -> bool:
    """Consulta activos e inactivos con la colación definida en la tabla."""
    consulta = select(SistemaProductivo.id).where(SistemaProductivo.nombre == nombre)
    if excluir_id is not None:
        consulta = consulta.where(SistemaProductivo.id != excluir_id)
    return db.scalar(consulta.limit(1)) is not None


def listar_sistemas_productivos(
    db: Session,
    activo: bool | None = None,
) -> list[SistemaProductivo]:
    """Lista el catálogo completo o el estado solicitado."""
    consulta = select(SistemaProductivo)
    if activo is not None:
        consulta = consulta.where(SistemaProductivo.activo == activo)
    return list(
        db.scalars(
            consulta.order_by(SistemaProductivo.nombre, SistemaProductivo.id),
        ).all(),
    )


def obtener_sistema_productivo(
    db: Session,
    sistema_productivo_id: int,
) -> SistemaProductivo | None:
    """Obtiene un sistema productivo de cualquier estado."""
    return db.get(SistemaProductivo, sistema_productivo_id)


def _obtener_sistema_productivo_bloqueado(
    db: Session,
    sistema_productivo_id: int,
) -> SistemaProductivo | None:
    """Recarga y bloquea el registro durante su actualización."""
    consulta = (
        select(SistemaProductivo)
        .where(SistemaProductivo.id == sistema_productivo_id)
        .with_hint(
            SistemaProductivo,
            "WITH (UPDLOCK, HOLDLOCK)",
            dialect_name="mssql",
        )
        .execution_options(populate_existing=True)
    )
    return db.scalar(consulta)


def crear_sistema_productivo(
    db: Session,
    datos: SistemaProductivoCreate,
    usuario: Usuario,
) -> SistemaProductivo:
    """Crea el sistema y su evento INSERT de forma atómica."""
    try:
        if _nombre_ocupado(db, datos.nombre):
            raise SistemaProductivoDuplicadoError(
                "Ya existe un sistema productivo con ese nombre",
            )
        nuevo = SistemaProductivo(**datos.model_dump())
        db.add(nuevo)
        db.flush()
        registrar_auditoria(
            db,
            usuario.id,
            "sistemas_productivos",
            nuevo.id,
            AccionAuditoria.INSERT,
            despues=instantanea(nuevo),
        )
        db.commit()
    except IntegrityError as error:
        db.rollback()
        if _es_nombre_duplicado(error):
            raise SistemaProductivoDuplicadoError(
                "Ya existe un sistema productivo con ese nombre",
            ) from error
        raise
    except Exception:
        db.rollback()
        raise
    db.refresh(nuevo)
    return nuevo


def actualizar_sistema_productivo(
    db: Session,
    sistema_productivo: SistemaProductivo,
    datos: SistemaProductivoUpdate,
    usuario: Usuario,
) -> SistemaProductivo:
    """Aplica cambios efectivos con auditoría y una única confirmación."""
    try:
        vigente = _obtener_sistema_productivo_bloqueado(
            db,
            sistema_productivo.id,
        )
        if vigente is None:
            raise SistemaProductivoNoEncontradoError(
                "Sistema productivo no encontrado",
            )
        enviados = datos.model_dump(exclude_unset=True, exclude_none=True)
        cambios = {
            campo: valor
            for campo, valor in enviados.items()
            if getattr(vigente, campo) != valor
        }
        if not cambios:
            return vigente
        if "nombre" in cambios and _nombre_ocupado(db, cambios["nombre"], vigente.id):
            raise SistemaProductivoDuplicadoError(
                "Ya existe un sistema productivo con ese nombre",
            )
        antes = instantanea(vigente)
        for campo, valor in cambios.items():
            setattr(vigente, campo, valor)
        db.flush()
        registrar_auditoria(
            db,
            usuario.id,
            "sistemas_productivos",
            vigente.id,
            AccionAuditoria.UPDATE,
            antes=antes,
            despues=instantanea(vigente),
        )
        db.commit()
    except IntegrityError as error:
        db.rollback()
        if _es_nombre_duplicado(error):
            raise SistemaProductivoDuplicadoError(
                "Ya existe un sistema productivo con ese nombre",
            ) from error
        raise
    except Exception:
        db.rollback()
        raise
    db.refresh(vigente)
    return vigente
