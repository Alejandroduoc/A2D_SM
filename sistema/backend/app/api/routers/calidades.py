"""Rutas administrativas del catálogo de calidades."""

# Agrupa rutas, inyecta dependencias y construye respuestas HTTP controladas.
from fastapi import APIRouter, Depends, HTTPException, status
# Anota la sesión que FastAPI entrega a cada solicitud.
from sqlalchemy.orm import Session

# Autorización jerárquica que consulta el usuario y sus roles en la base.
from app.api.deps import require_rol
# Proporciona una sesión por petición.
from app.core.database import get_db
# Modelo que devuelve el servicio antes de serializarlo.
from app.models.calidad import Calidad
# Rol requerido y usuario responsable de las operaciones.
from app.models.usuario import RolUsuario, Usuario
# Validan la entrada y limitan la salida a los campos públicos.
from app.schemas.calidad import CalidadCreate, CalidadOut, CalidadUpdate
# Delega consultas, escrituras y auditoría al servicio.
from app.services.calidad import (
    CalidadDuplicadaError,  # Nombre ocupado → 409.
    CalidadNoEncontradaError,  # Registro desaparecido durante la edición → 404.
    actualizar_calidad,  # Renombra o cambia el estado con auditoría.
    crear_calidad,  # Crea la calidad y su auditoría juntas.
    listar_calidades,  # Lista con filtro opcional de estado.
    obtener_calidad,  # Busca por id; None si no existe.
)  # Finaliza las importaciones del servicio.


# main.py agrega el prefijo general /api/v1.
router = APIRouter(prefix="/calidades", tags=["Calidades"])


# Lista el catálogo; solo el administrador.
@router.get("", response_model=list[CalidadOut])
# Recibe el filtro opcional y la sesión de la petición.
def listar(
    activo: bool | None = None,  # Sin filtro devuelve ambos estados.
    db: Session = Depends(get_db),  # Sesión de la petición.
    usuario_administrador: Usuario = Depends(
        require_rol(RolUsuario.ADMINISTRADOR),  # Exige administrador también para leer.
    ),  # La autorización ocurre antes de ejecutar el endpoint.
) -> list[Calidad]:
    """Lista ambos estados o el estado solicitado por el administrador."""
    # Delega la consulta al servicio.
    return listar_calidades(db, activo)


# Detalle de una calidad; solo el administrador.
@router.get("/{calidad_id}", response_model=CalidadOut)
# Recibe el id y la sesión de la petición.
def obtener(
    calidad_id: int,  # Id interno solicitado.
    db: Session = Depends(get_db),  # Sesión de la petición.
    usuario_administrador: Usuario = Depends(
        require_rol(RolUsuario.ADMINISTRADOR),  # Restringe la lectura al administrador.
    ),  # La autorización ocurre antes de ejecutar el endpoint.
) -> Calidad:
    """Obtiene una calidad activa o inactiva."""
    # Busca la calidad por id.
    calidad = obtener_calidad(db, calidad_id)
    # Traduce la ausencia a 404.
    if calidad is None:
        # Mensaje sin información interna de la base.
        raise HTTPException(status_code=404, detail="Calidad no encontrada")
    # FastAPI serializa el modelo con CalidadOut.
    return calidad


# Alta de una calidad; responde 201.
@router.post("", response_model=CalidadOut, status_code=status.HTTP_201_CREATED)
# El responsable sale de la autorización, no del cuerpo de la petición.
def crear(
    datos: CalidadCreate,  # Nombre validado y normalizado.
    db: Session = Depends(get_db),  # Sesión de la petición.
    usuario_administrador: Usuario = Depends(
        require_rol(RolUsuario.ADMINISTRADOR),  # Autoriza y entrega el actor de la auditoría.
    ),  # La autorización ocurre antes de ejecutar el endpoint.
) -> Calidad:
    """Crea una calidad e identifica al administrador en su auditoría."""
    # Limita la traducción de errores al conflicto conocido.
    try:
        # El servicio confirma la calidad y su auditoría.
        return crear_calidad(db, datos, usuario_administrador)
    # Solo el nombre duplicado se traduce a 409.
    except CalidadDuplicadaError as error:
        # Mensaje fijo, sin detalles del controlador SQL.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,  # Conflicto de unicidad.
            detail="Ya existe una calidad con ese nombre",  # Mensaje de negocio.
        ) from error  # Conserva la causa para diagnóstico.


# Edición: renombrar, desactivar o activar (no hay DELETE).
@router.put("/{calidad_id}", response_model=CalidadOut)
# Recibe el id, los cambios parciales y la sesión.
def actualizar(
    calidad_id: int,  # Id interno que se edita.
    datos: CalidadUpdate,  # Cambios validados; activo=False desactiva.
    db: Session = Depends(get_db),  # Sesión de la petición.
    usuario_administrador: Usuario = Depends(
        require_rol(RolUsuario.ADMINISTRADOR),  # Autoriza y entrega el actor de la auditoría.
    ),  # La autorización ocurre antes de ejecutar el endpoint.
) -> Calidad:
    """Renombra o cambia el estado sin admitir borrado físico."""
    # Busca antes de editar.
    calidad = obtener_calidad(db, calidad_id)
    # Responde 404 sin intentar modificar ni auditar.
    if calidad is None:
        # Mismo mensaje que el detalle.
        raise HTTPException(status_code=404, detail="Calidad no encontrada")
    # Traduce solo los errores de negocio conocidos.
    try:
        # El servicio aplica los cambios efectivos, audita y confirma.
        return actualizar_calidad(db, calidad, datos, usuario_administrador)
    # El registro desapareció durante la edición.
    except CalidadNoEncontradaError as error:
        # Responde 404 conservando la causa.
        raise HTTPException(status_code=404, detail="Calidad no encontrada") from error
    # El nuevo nombre pertenece a otra calidad.
    except CalidadDuplicadaError as error:
        # Responde 409 sin detalles internos.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,  # Conflicto de unicidad.
            detail="Ya existe una calidad con ese nombre",  # Mensaje de negocio.
        ) from error  # Conserva la causa para diagnóstico.
