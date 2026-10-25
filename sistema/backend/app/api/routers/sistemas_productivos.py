"""Rutas administrativas del catálogo de sistemas productivos."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_rol
from app.core.database import get_db
from app.models.sistema_productivo import SistemaProductivo
from app.models.usuario import RolUsuario, Usuario
from app.schemas.sistema_productivo import (
    SistemaProductivoCreate,
    SistemaProductivoOut,
    SistemaProductivoUpdate,
)
from app.services.sistema_productivo import (
    SistemaProductivoDuplicadoError,
    SistemaProductivoNoEncontradoError,
    actualizar_sistema_productivo,
    crear_sistema_productivo,
    listar_sistemas_productivos,
    obtener_sistema_productivo,
)


router = APIRouter(
    prefix="/sistemas-productivos",
    tags=["Sistemas productivos"],
)


@router.get("", response_model=list[SistemaProductivoOut])
def listar(
    activo: bool | None = None,
    db: Session = Depends(get_db),
    usuario_administrador: Usuario = Depends(
        require_rol(RolUsuario.ADMINISTRADOR),
    ),
) -> list[SistemaProductivo]:
    """Lista el catálogo completo o un estado explícito."""
    return listar_sistemas_productivos(db, activo)


@router.get("/{sistema_productivo_id}", response_model=SistemaProductivoOut)
def obtener(
    sistema_productivo_id: int,
    db: Session = Depends(get_db),
    usuario_administrador: Usuario = Depends(
        require_rol(RolUsuario.ADMINISTRADOR),
    ),
) -> SistemaProductivo:
    """Obtiene un sistema productivo de cualquier estado."""
    sistema = obtener_sistema_productivo(db, sistema_productivo_id)
    if sistema is None:
        raise HTTPException(
            status_code=404,
            detail="Sistema productivo no encontrado",
        )
    return sistema


@router.post(
    "",
    response_model=SistemaProductivoOut,
    status_code=status.HTTP_201_CREATED,
)
def crear(
    datos: SistemaProductivoCreate,
    db: Session = Depends(get_db),
    usuario_administrador: Usuario = Depends(
        require_rol(RolUsuario.ADMINISTRADOR),
    ),
) -> SistemaProductivo:
    """Crea el sistema productivo con auditoría del actor autenticado."""
    try:
        return crear_sistema_productivo(db, datos, usuario_administrador)
    except SistemaProductivoDuplicadoError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe un sistema productivo con ese nombre",
        ) from error


@router.put("/{sistema_productivo_id}", response_model=SistemaProductivoOut)
def actualizar(
    sistema_productivo_id: int,
    datos: SistemaProductivoUpdate,
    db: Session = Depends(get_db),
    usuario_administrador: Usuario = Depends(
        require_rol(RolUsuario.ADMINISTRADOR),
    ),
) -> SistemaProductivo:
    """Actualiza nombre o estado manteniendo la identidad del catálogo."""
    sistema = obtener_sistema_productivo(db, sistema_productivo_id)
    if sistema is None:
        raise HTTPException(
            status_code=404,
            detail="Sistema productivo no encontrado",
        )
    try:
        return actualizar_sistema_productivo(
            db,
            sistema,
            datos,
            usuario_administrador,
        )
    except SistemaProductivoNoEncontradoError as error:
        raise HTTPException(
            status_code=404,
            detail="Sistema productivo no encontrado",
        ) from error
    except SistemaProductivoDuplicadoError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe un sistema productivo con ese nombre",
        ) from error
