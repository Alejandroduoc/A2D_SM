"""Rutas administrativas del catálogo de calidades."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_rol
from app.core.database import get_db
from app.models.calidad import Calidad
from app.models.usuario import RolUsuario, Usuario
from app.schemas.calidad import CalidadCreate, CalidadOut, CalidadUpdate
from app.services.calidad import (
    CalidadDuplicadaError,
    CalidadNoEncontradaError,
    actualizar_calidad,
    crear_calidad,
    listar_calidades,
    obtener_calidad,
)


router = APIRouter(prefix="/calidades", tags=["Calidades"])


@router.get("", response_model=list[CalidadOut])
def listar(
    activo: bool | None = None,
    db: Session = Depends(get_db),
    usuario_administrador: Usuario = Depends(
        require_rol(RolUsuario.ADMINISTRADOR),
    ),
) -> list[Calidad]:
    """Lista ambos estados o el estado solicitado por el administrador."""
    return listar_calidades(db, activo)


@router.get("/{calidad_id}", response_model=CalidadOut)
def obtener(
    calidad_id: int,
    db: Session = Depends(get_db),
    usuario_administrador: Usuario = Depends(
        require_rol(RolUsuario.ADMINISTRADOR),
    ),
) -> Calidad:
    """Obtiene una calidad activa o inactiva."""
    calidad = obtener_calidad(db, calidad_id)
    if calidad is None:
        raise HTTPException(status_code=404, detail="Calidad no encontrada")
    return calidad


@router.post("", response_model=CalidadOut, status_code=status.HTTP_201_CREATED)
def crear(
    datos: CalidadCreate,
    db: Session = Depends(get_db),
    usuario_administrador: Usuario = Depends(
        require_rol(RolUsuario.ADMINISTRADOR),
    ),
) -> Calidad:
    """Crea una calidad e identifica al administrador en su auditoría."""
    try:
        return crear_calidad(db, datos, usuario_administrador)
    except CalidadDuplicadaError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una calidad con ese nombre",
        ) from error


@router.put("/{calidad_id}", response_model=CalidadOut)
def actualizar(
    calidad_id: int,
    datos: CalidadUpdate,
    db: Session = Depends(get_db),
    usuario_administrador: Usuario = Depends(
        require_rol(RolUsuario.ADMINISTRADOR),
    ),
) -> Calidad:
    """Renombra o cambia el estado sin admitir borrado físico."""
    calidad = obtener_calidad(db, calidad_id)
    if calidad is None:
        raise HTTPException(status_code=404, detail="Calidad no encontrada")
    try:
        return actualizar_calidad(db, calidad, datos, usuario_administrador)
    except CalidadNoEncontradaError as error:
        raise HTTPException(status_code=404, detail="Calidad no encontrada") from error
    except CalidadDuplicadaError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una calidad con ese nombre",
        ) from error
