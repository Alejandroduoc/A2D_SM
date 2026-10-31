"""Rutas administrativas del catálogo de tipos de bandeja."""

# Agrupa rutas, dependencias y respuestas HTTP controladas.
from fastapi import APIRouter, Depends, HTTPException, status
# Anota la sesión entregada a cada solicitud.
from sqlalchemy.orm import Session

# Revalida el rol del usuario consultando la base.
from app.api.deps import require_rol
# Proporciona una sesión por petición.
from app.core.database import get_db
# Modelo devuelto por el servicio antes de serializarlo.
from app.models.tipo_bandeja import TipoBandeja
# Rol requerido y actor responsable de la auditoría.
from app.models.usuario import RolUsuario, Usuario
# Contratos estrictos de entrada y salida.
from app.schemas.tipo_bandeja import TipoBandejaCreate, TipoBandejaOut, TipoBandejaUpdate
# Delega consultas, reglas, bloqueos y escrituras al servicio.
from app.services.tipo_bandeja import (
    TipoBandejaDuplicadoError,
    TipoBandejaNoEncontradoError,
    actualizar_tipo_bandeja,
    crear_tipo_bandeja,
    listar_tipos_bandeja,
    obtener_tipo_bandeja,
)


# main.py agrega el prefijo general /api/v1.
router = APIRouter(prefix="/tipos-bandeja", tags=["Tipos de bandeja"])


# Lista ambos estados o el estado solicitado, sólo para administración.
@router.get("", response_model=list[TipoBandejaOut])
def listar(
    activo: bool | None = None,
    db: Session = Depends(get_db),
    usuario_administrador: Usuario = Depends(require_rol(RolUsuario.ADMINISTRADOR)),
) -> list[TipoBandeja]:
    """Lista tipos de bandeja sin modificar ni auditar."""
    # Conserva False como filtro válido de registros inactivos.
    return listar_tipos_bandeja(db, activo)


# Obtiene el detalle de una bandeja activa o inactiva.
@router.get("/{tipo_bandeja_id}", response_model=TipoBandejaOut)
def obtener(
    tipo_bandeja_id: int,
    db: Session = Depends(get_db),
    usuario_administrador: Usuario = Depends(require_rol(RolUsuario.ADMINISTRADOR)),
) -> TipoBandeja:
    """Obtiene una bandeja o responde 404 si no existe."""
    # Delega la búsqueda por identidad al servicio.
    tipo_bandeja = obtener_tipo_bandeja(db, tipo_bandeja_id)
    # Un detalle ausente se traduce a 404.
    if tipo_bandeja is None:
        # No expone información interna de SQL Server.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tipo de bandeja no encontrado")
    # FastAPI limita la respuesta con TipoBandejaOut.
    return tipo_bandeja


# Crea una bandeja y responde 201.
@router.post("", response_model=TipoBandejaOut, status_code=status.HTTP_201_CREATED)
def crear(
    datos: TipoBandejaCreate,
    db: Session = Depends(get_db),
    usuario_administrador: Usuario = Depends(require_rol(RolUsuario.ADMINISTRADOR)),
) -> TipoBandeja:
    """Crea una bandeja y registra al administrador en la auditoría."""
    # Traduce únicamente la duplicidad conocida.
    try:
        # El servicio confirma catálogo y auditoría en conjunto.
        return crear_tipo_bandeja(db, datos, usuario_administrador)
    # Un nombre reservado produce conflicto.
    except TipoBandejaDuplicadoError as error:
        # Responde con un mensaje fijo de negocio.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe un tipo de bandeja con ese nombre",
        ) from error


# PUT permite editar o cambiar estado sin borrado físico.
@router.put("/{tipo_bandeja_id}", response_model=TipoBandejaOut)
def actualizar(
    tipo_bandeja_id: int,
    datos: TipoBandejaUpdate,
    db: Session = Depends(get_db),
    usuario_administrador: Usuario = Depends(require_rol(RolUsuario.ADMINISTRADOR)),
) -> TipoBandeja:
    """Actualiza nombre, tara o estado mediante el servicio auditado."""
    # Comprueba primero la existencia del recurso.
    tipo_bandeja = obtener_tipo_bandeja(db, tipo_bandeja_id)
    # Evita delegar una identidad inexistente.
    if tipo_bandeja is None:
        # Conserva el mismo mensaje usado por el detalle.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tipo de bandeja no encontrado")
    # Traduce solamente errores de negocio conocidos.
    try:
        # El servicio recarga, bloquea, audita y confirma.
        return actualizar_tipo_bandeja(db, tipo_bandeja, datos, usuario_administrador)
    # Contempla una desaparición concurrente.
    except TipoBandejaNoEncontradoError as error:
        # Responde 404 sin detalles internos.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tipo de bandeja no encontrado") from error
    # Contempla un renombre hacia otro registro reservado.
    except TipoBandejaDuplicadoError as error:
        # Responde 409 con mensaje estable.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe un tipo de bandeja con ese nombre",
        ) from error
