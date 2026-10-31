"""Rutas administrativas del catálogo de embalajes."""

# Agrupa rutas, dependencias y respuestas HTTP controladas.
from fastapi import APIRouter, Depends, HTTPException, status
# Anota la sesión entregada a cada solicitud.
from sqlalchemy.orm import Session

# Revalida el rol del usuario consultando la base.
from app.api.deps import require_rol
# Proporciona una sesión por petición.
from app.core.database import get_db
# Modelo devuelto por el servicio antes de serializarlo.
from app.models.embalaje import Embalaje
# Rol requerido y actor responsable de la auditoría.
from app.models.usuario import RolUsuario, Usuario
# Contratos estrictos de entrada y salida.
from app.schemas.embalaje import EmbalajeCreate, EmbalajeOut, EmbalajeUpdate
# Delega consultas, reglas, bloqueos y escrituras al servicio.
from app.services.embalaje import (
    EmbalajeDuplicadoError,
    EmbalajeNoEncontradoError,
    actualizar_embalaje,
    crear_embalaje,
    listar_embalajes,
    obtener_embalaje,
)


# main.py agrega el prefijo general /api/v1.
router = APIRouter(prefix="/embalajes", tags=["Embalajes"])


# Lista ambos estados o el estado solicitado, sólo para administración.
@router.get("", response_model=list[EmbalajeOut])
def listar(
    activo: bool | None = None,
    db: Session = Depends(get_db),
    usuario_administrador: Usuario = Depends(require_rol(RolUsuario.ADMINISTRADOR)),
) -> list[Embalaje]:
    """Lista embalajes sin modificar ni auditar."""
    # Conserva False como filtro válido de registros inactivos.
    return listar_embalajes(db, activo)


# Obtiene el detalle de un embalaje activo o inactivo.
@router.get("/{embalaje_id}", response_model=EmbalajeOut)
def obtener(
    embalaje_id: int,
    db: Session = Depends(get_db),
    usuario_administrador: Usuario = Depends(require_rol(RolUsuario.ADMINISTRADOR)),
) -> Embalaje:
    """Obtiene un embalaje o responde 404 si no existe."""
    # Delega la búsqueda por identidad al servicio.
    embalaje = obtener_embalaje(db, embalaje_id)
    # Un detalle ausente se traduce a 404.
    if embalaje is None:
        # No expone información interna de SQL Server.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Embalaje no encontrado")
    # FastAPI limita la respuesta con EmbalajeOut.
    return embalaje


# Crea un embalaje fijo o a granel y responde 201.
@router.post("", response_model=EmbalajeOut, status_code=status.HTTP_201_CREATED)
def crear(
    datos: EmbalajeCreate,
    db: Session = Depends(get_db),
    usuario_administrador: Usuario = Depends(require_rol(RolUsuario.ADMINISTRADOR)),
) -> Embalaje:
    """Crea un embalaje y registra al administrador en la auditoría."""
    # Traduce únicamente la duplicidad conocida.
    try:
        # El servicio conserva null cuando corresponde a granel.
        return crear_embalaje(db, datos, usuario_administrador)
    # Un nombre reservado produce conflicto.
    except EmbalajeDuplicadoError as error:
        # Responde con un mensaje fijo de negocio.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe un embalaje con ese nombre",
        ) from error


# PUT permite editar o cambiar estado sin borrado físico.
@router.put("/{embalaje_id}", response_model=EmbalajeOut)
def actualizar(
    embalaje_id: int,
    datos: EmbalajeUpdate,
    db: Session = Depends(get_db),
    usuario_administrador: Usuario = Depends(require_rol(RolUsuario.ADMINISTRADOR)),
) -> Embalaje:
    """Actualiza nombre, kilos o estado mediante el servicio auditado."""
    # Comprueba primero la existencia del recurso.
    embalaje = obtener_embalaje(db, embalaje_id)
    # Evita delegar una identidad inexistente.
    if embalaje is None:
        # Conserva el mismo mensaje usado por el detalle.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Embalaje no encontrado")
    # Traduce solamente errores de negocio conocidos.
    try:
        # El servicio conserva el null explícito, bloquea, audita y confirma.
        return actualizar_embalaje(db, embalaje, datos, usuario_administrador)
    # Contempla una desaparición concurrente.
    except EmbalajeNoEncontradoError as error:
        # Responde 404 sin detalles internos.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Embalaje no encontrado") from error
    # Contempla un renombre hacia otro registro reservado.
    except EmbalajeDuplicadoError as error:
        # Responde 409 con mensaje estable.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe un embalaje con ese nombre",
        ) from error
