"""
El router valida entradas, exige permisos y traduce resultados a HTTP.
El servicio controla las consultas, los cambios y su auditoría transaccional.
"""

# Agrupa rutas, inyecta dependencias y construye respuestas HTTP controladas.
from fastapi import APIRouter, Depends, HTTPException, status

# Anota la sesión que FastAPI proporciona a cada solicitud.
from sqlalchemy.orm import Session

# Reutiliza la autorización que consulta el usuario y sus roles en la base.
from app.api.deps import require_rol

# Proporciona la misma sesión a la autenticación y al mantenimiento de productores.
from app.core.database import get_db

# Anota los modelos que devuelve el servicio antes de la serialización de salida.
from app.models.productor import Productor

# Identifica el rol requerido y al usuario responsable de las operaciones.
from app.models.usuario import RolUsuario, Usuario

# Valida alta y edición y limita la respuesta a los seis campos públicos.
from app.schemas.productor import ProductorCreate, ProductorOut, ProductorUpdate

# Delega consultas y escrituras al servicio, incluida la auditoría de HU21.
from app.services.productor import (
    ProductorDuplicadoError,  # Identifica exclusivamente los conflictos de RUT.
    actualizar_productor,  # Edita, corrige RUT y cambia el estado con auditoría.
    crear_productor,  # Confirma el alta y su evento de auditoría juntos.
    listar_productores,  # Consulta el catálogo con filtro opcional de estado.
    obtener_productor,  # Busca por id y devuelve None cuando el registro no existe.
)  # Finaliza las importaciones del servicio de negocio.


# main.py agrega el prefijo general /api/v1 a estas rutas del módulo.
router = APIRouter(prefix="/productores", tags=["Productores"])


# Expone el catálogo con salida pública y mantiene el filtro de inactivos.
@router.get("", response_model=list[ProductorOut])
# La dependencia de administrador protege también las consultas del mantenimiento.
def listar(
    activo: bool | None = None,  # Sin filtro devuelve ambos estados; False pide inactivos.
    db: Session = Depends(get_db),  # Comparte la sesión de la solicitud.
    usuario_administrador: Usuario = Depends(
        require_rol(RolUsuario.ADMINISTRADOR),  # Exige administrador aunque no se use el actor en la consulta.
    ),  # La autorización ocurre antes de ejecutar el endpoint.
) -> list[Productor]:
    """Lista productores para un administrador, con filtro opcional de estado."""
    # Entrega siempre activo, incluido False, sin repetir consultas en el router.
    return listar_productores(db, activo=activo)


# Publica el detalle con las mismas restricciones de acceso del catálogo.
@router.get("/{productor_id}", response_model=ProductorOut)
# Recibe un id entero y deja que el servicio realice la búsqueda.
def obtener(
    productor_id: int,  # Identidad interna del productor solicitado.
    db: Session = Depends(get_db),  # Sesión proporcionada para esta solicitud.
    usuario_administrador: Usuario = Depends(
        require_rol(RolUsuario.ADMINISTRADOR),  # Restringe la lectura al administrador.
    ),  # Mantiene la protección aunque el actor no intervenga en la búsqueda.
) -> Productor:
    """Obtiene un productor o responde 404 si el id no existe."""
    # Delega la consulta por clave primaria al servicio.
    productor = obtener_productor(db, productor_id)
    # Traduce únicamente la ausencia del registro a una respuesta 404.
    if productor is None:
        # Mantiene un mensaje de negocio sin información interna de la base.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,  # Indica que el recurso solicitado no existe.
            detail="Productor no encontrado",  # Mensaje previsto para el cliente.
        )  # Finaliza la respuesta de recurso inexistente.
    # FastAPI serializa el modelo mediante ProductorOut.
    return productor


# El alta devuelve 201 y utiliza el schema de salida del catálogo.
@router.post(
    "",  # Comparte la ruta de colección con el listado.
    response_model=ProductorOut,  # Expone únicamente los campos públicos del productor.
    status_code=status.HTTP_201_CREATED,  # Informa que el recurso se creó correctamente.
)  # Finaliza la configuración HTTP del alta.
# La identidad del actor procede de la autorización, no del cuerpo recibido.
def crear(
    datos: ProductorCreate,  # Valida campos y normaliza el RUT antes de llamar al servicio.
    db: Session = Depends(get_db),  # Comparte la sesión con la autenticación y la escritura.
    usuario_administrador: Usuario = Depends(
        require_rol(RolUsuario.ADMINISTRADOR),  # Autoriza al administrador y obtiene el actor de auditoría.
    ),  # Entrega al endpoint el usuario autenticado autorizado.
) -> Productor:
    """Crea un productor y su auditoría; responde 409 si el RUT ya pertenece a otro."""
    # Limita la traducción de errores al conflicto de negocio conocido.
    try:
        # El servicio confirma el productor y la auditoría con este mismo actor.
        return crear_productor(db, datos, usuario_administrador)
    # No transforma otras restricciones o fallos internos en un RUT duplicado.
    except ProductorDuplicadoError as error:
        # Responde con un mensaje fijo sin SQL ni detalles del controlador.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,  # Informa el conflicto de unicidad.
            detail="Ya existe un productor con ese RUT",  # Mantiene el mensaje de negocio.
        ) from error  # Conserva la causa para diagnóstico interno.


# Usa PUT tanto para corregir datos como para activar o desactivar el productor.
@router.put("/{productor_id}", response_model=ProductorOut)
# El schema admite cambios parciales y el servicio calcula cuáles son efectivos.
def actualizar(
    productor_id: int,  # Conserva la identidad interna incluso al corregir el RUT.
    datos: ProductorUpdate,  # Valida los cambios; activo=False representa desactivación.
    db: Session = Depends(get_db),  # Comparte la sesión del cambio y su auditoría.
    usuario_administrador: Usuario = Depends(
        require_rol(RolUsuario.ADMINISTRADOR),  # Exige administrador también para corregir el RUT.
    ),  # Proporciona el responsable autenticado del evento UPDATE.
) -> Productor:
    """Edita sin borrar; responde 404 si falta el productor y 409 si el RUT está ocupado."""
    # Busca antes de editar para evitar pasar un registro inexistente al servicio.
    productor = obtener_productor(db, productor_id)
    # Resuelve la ausencia del productor sin intentar modificar ni auditar.
    if productor is None:
        # Devuelve el mismo mensaje que la consulta de detalle.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,  # El id no corresponde a un recurso existente.
            detail="Productor no encontrado",  # Describe el resultado de la búsqueda.
        )  # Finaliza la respuesta de recurso inexistente.
    # Traduce solo los conflictos que el servicio identifica como RUT duplicado.
    try:
        # Delega cambios, estados anterior y posterior, auditoría y commit al servicio.
        return actualizar_productor(db, productor, datos, usuario_administrador)
    # Incluye un conflicto al corregir el RUT hacia el de otro productor inactivo.
    except ProductorDuplicadoError as error:
        # Mantiene fuera de la respuesta cualquier información del controlador SQL.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,  # Indica el conflicto del RUT solicitado.
            detail="Ya existe un productor con ese RUT",  # Mensaje público del conflicto.
        ) from error  # Conserva la causa sin exponerla al cliente.
