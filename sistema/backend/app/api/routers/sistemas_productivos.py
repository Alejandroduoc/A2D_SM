"""Rutas administrativas del catálogo de sistemas productivos."""

# Agrupa rutas, inyecta dependencias y construye respuestas HTTP controladas.
from fastapi import APIRouter, Depends, HTTPException, status
# Anota la sesión que FastAPI entrega a cada solicitud.
from sqlalchemy.orm import Session

# Autorización jerárquica que consulta el usuario y sus roles en la base.
from app.api.deps import require_rol
# Proporciona una sesión por petición.
from app.core.database import get_db
# Modelo que devuelve el servicio antes de serializarlo.
from app.models.sistema_productivo import SistemaProductivo
# Rol requerido y usuario responsable de las operaciones.
from app.models.usuario import RolUsuario, Usuario
# Validan la entrada y limitan la salida a los campos públicos.
from app.schemas.sistema_productivo import (
    SistemaProductivoCreate,  # Datos de alta.
    SistemaProductivoOut,  # Respuesta pública.
    SistemaProductivoUpdate,  # Cambios parciales.
)  # Finaliza las importaciones de schemas.
# Delega consultas, escrituras y auditoría al servicio.
from app.services.sistema_productivo import (
    SistemaProductivoDuplicadoError,  # Nombre ocupado → 409.
    SistemaProductivoNoEncontradoError,  # Registro desaparecido durante la edición → 404.
    actualizar_sistema_productivo,  # Renombra o cambia el estado con auditoría.
    crear_sistema_productivo,  # Crea el sistema y su auditoría juntas.
    listar_sistemas_productivos,  # Lista con filtro opcional de estado.
    obtener_sistema_productivo,  # Busca por id; None si no existe.
)  # Finaliza las importaciones del servicio.


# main.py agrega el prefijo general /api/v1.
router = APIRouter(
    prefix="/sistemas-productivos",  # Ruta base del catálogo.
    tags=["Sistemas productivos"],  # Sección en /docs.
)  # Finaliza la creación del router.


# Lista el catálogo; solo el administrador.
@router.get("", response_model=list[SistemaProductivoOut])
# Recibe el filtro opcional y la sesión de la petición.
def listar(
    activo: bool | None = None,  # Sin filtro devuelve ambos estados.
    db: Session = Depends(get_db),  # Sesión de la petición.
    usuario_administrador: Usuario = Depends(
        require_rol(RolUsuario.ADMINISTRADOR),  # Exige administrador también para leer.
    ),  # La autorización ocurre antes de ejecutar el endpoint.
) -> list[SistemaProductivo]:
    """Lista el catálogo completo o un estado explícito."""
    # Delega la consulta al servicio.
    return listar_sistemas_productivos(db, activo)


# Detalle de un sistema productivo; solo el administrador.
@router.get("/{sistema_productivo_id}", response_model=SistemaProductivoOut)
# Recibe el id y la sesión de la petición.
def obtener(
    sistema_productivo_id: int,  # Id interno solicitado.
    db: Session = Depends(get_db),  # Sesión de la petición.
    usuario_administrador: Usuario = Depends(
        require_rol(RolUsuario.ADMINISTRADOR),  # Restringe la lectura al administrador.
    ),  # La autorización ocurre antes de ejecutar el endpoint.
) -> SistemaProductivo:
    """Obtiene un sistema productivo de cualquier estado."""
    # Busca el sistema por id.
    sistema = obtener_sistema_productivo(db, sistema_productivo_id)
    # Traduce la ausencia a 404.
    if sistema is None:
        # Mensaje sin información interna de la base.
        raise HTTPException(
            status_code=404,  # Recurso inexistente.
            detail="Sistema productivo no encontrado",  # Mensaje de negocio.
        )  # Finaliza la respuesta de no encontrado.
    # FastAPI serializa el modelo con SistemaProductivoOut.
    return sistema


# Alta de un sistema productivo; responde 201.
@router.post(
    "",  # Comparte la ruta de colección con el listado.
    response_model=SistemaProductivoOut,  # Respuesta pública.
    status_code=status.HTTP_201_CREATED,  # Recurso creado.
)  # Finaliza la configuración HTTP del alta.
# El responsable sale de la autorización, no del cuerpo de la petición.
def crear(
    datos: SistemaProductivoCreate,  # Nombre validado y normalizado.
    db: Session = Depends(get_db),  # Sesión de la petición.
    usuario_administrador: Usuario = Depends(
        require_rol(RolUsuario.ADMINISTRADOR),  # Autoriza y entrega el actor de la auditoría.
    ),  # La autorización ocurre antes de ejecutar el endpoint.
) -> SistemaProductivo:
    """Crea el sistema productivo con auditoría del actor autenticado."""
    # Limita la traducción de errores al conflicto conocido.
    try:
        # El servicio confirma el sistema y su auditoría.
        return crear_sistema_productivo(db, datos, usuario_administrador)
    # Solo el nombre duplicado se traduce a 409.
    except SistemaProductivoDuplicadoError as error:
        # Mensaje fijo, sin detalles del controlador SQL.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,  # Conflicto de unicidad.
            detail="Ya existe un sistema productivo con ese nombre",  # Mensaje de negocio.
        ) from error  # Conserva la causa para diagnóstico.


# Edición: renombrar, desactivar o activar (no hay DELETE).
@router.put("/{sistema_productivo_id}", response_model=SistemaProductivoOut)
# Recibe el id, los cambios parciales y la sesión.
def actualizar(
    sistema_productivo_id: int,  # Id interno que se edita.
    datos: SistemaProductivoUpdate,  # Cambios validados; activo=False desactiva.
    db: Session = Depends(get_db),  # Sesión de la petición.
    usuario_administrador: Usuario = Depends(
        require_rol(RolUsuario.ADMINISTRADOR),  # Autoriza y entrega el actor de la auditoría.
    ),  # La autorización ocurre antes de ejecutar el endpoint.
) -> SistemaProductivo:
    """Actualiza nombre o estado manteniendo la identidad del catálogo."""
    # Busca antes de editar.
    sistema = obtener_sistema_productivo(db, sistema_productivo_id)
    # Responde 404 sin intentar modificar ni auditar.
    if sistema is None:
        # Mismo mensaje que el detalle.
        raise HTTPException(
            status_code=404,  # Recurso inexistente.
            detail="Sistema productivo no encontrado",  # Mensaje de negocio.
        )  # Finaliza la respuesta de no encontrado.
    # Traduce solo los errores de negocio conocidos.
    try:
        # El servicio aplica los cambios efectivos, audita y confirma.
        return actualizar_sistema_productivo(
            db,  # Sesión de la petición.
            sistema,  # Registro encontrado.
            datos,  # Cambios validados.
            usuario_administrador,  # Responsable de la auditoría.
        )  # Finaliza la llamada al servicio.
    # El registro desapareció durante la edición.
    except SistemaProductivoNoEncontradoError as error:
        # Responde 404 conservando la causa.
        raise HTTPException(
            status_code=404,  # Recurso inexistente.
            detail="Sistema productivo no encontrado",  # Mensaje de negocio.
        ) from error  # Encadena la causa.
    # El nuevo nombre pertenece a otro sistema productivo.
    except SistemaProductivoDuplicadoError as error:
        # Responde 409 sin detalles internos.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,  # Conflicto de unicidad.
            detail="Ya existe un sistema productivo con ese nombre",  # Mensaje de negocio.
        ) from error  # Conserva la causa para diagnóstico.
