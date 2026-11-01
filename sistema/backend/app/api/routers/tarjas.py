"""Rutas de registro y consulta de tarjas de recepción."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.database import get_db
from app.models.tarja import Tarja
from app.models.usuario import RolUsuario, Usuario
from app.schemas.tarja import PendientesProductorOut, TarjaCreate, TarjaOut
from app.services.tarja import (
    CatalogoNoValidoError,
    KilosNetosNoValidosError,
    obtener_tarja,
    pendientes_productor,
    registrar_tarja,
)


# Solo recepción y administración pueden acceder al módulo.
router = APIRouter(
    prefix="/tarjas",
    tags=["Tarjas"],
    dependencies=[
        Depends(
            require_roles(
                RolUsuario.OPERADOR_RECEPCION,
                RolUsuario.ADMINISTRADOR,
            )
        )
    ],
)


# Registra una tarja, su entrada de bandejas y sus auditorías.
@router.post("", response_model=TarjaOut, status_code=status.HTTP_201_CREATED)
def crear(
    datos: TarjaCreate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> Tarja:
    try:
        return registrar_tarja(db, datos, usuario)
    except (CatalogoNoValidoError, KilosNetosNoValidosError) as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error


# Debe declararse antes de /{tarja_id} para no interpretar "pendientes" como id.
@router.get("/pendientes", response_model=PendientesProductorOut)
def pendientes(
    productor_id: int = Query(gt=0),
    db: Session = Depends(get_db),
) -> PendientesProductorOut:
    cantidad, kilos = pendientes_productor(db, productor_id)
    return PendientesProductorOut(
        productor_id=productor_id,
        tarjas_sin_procesar=cantidad,
        kilos_sin_procesar=kilos,
    )


# Obtiene el detalle persistido de una tarja.
@router.get("/{tarja_id}", response_model=TarjaOut)
def obtener(tarja_id: int, db: Session = Depends(get_db)) -> Tarja:
    tarja = obtener_tarja(db, tarja_id)
    if tarja is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tarja no encontrada",
        )
    return tarja
