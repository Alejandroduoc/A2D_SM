"""Entradas, permisos y respuestas del mantenimiento administrativo de especies."""

# Agrupa rutas, inyecta dependencias y construye errores HTTP controlados.
from fastapi import APIRouter, Depends, HTTPException, status
# Anota la sesión compartida por autorización y servicio.
from sqlalchemy.orm import Session

# Comprueba el rol actual del usuario consultando la base de datos.
from app.api.deps import require_rol
# Proporciona una sesión por solicitud, también utilizada por autenticación.
from app.core.database import get_db
# Modelos que representan el recurso y el actor autenticado.
from app.models.especie import Especie
from app.models.usuario import RolUsuario, Usuario
# Contratos estrictos de entrada y campos públicos de salida.
from app.schemas.especie import EspecieCreate, EspecieOut, EspecieUpdate
# El servicio concentra reglas, bloqueos, transacción y auditoría.
from app.services.especie import (
    EspecieConVariedadesActivasError,  # Impide desactivar un padre con hijas activas.
    EspecieDuplicadaError,  # Identifica el conflicto de nombre reservado.
    EspecieNoEncontradaError,  # Contempla desaparición después de la consulta inicial.
    actualizar_especie,  # Actualiza únicamente cambios efectivos con auditoría.
    crear_especie,  # Crea especie y evento en la misma transacción.
    listar_especies,  # Conserva ambos estados o filtra explícitamente.
    obtener_especie,  # Devuelve None cuando no existe el id solicitado.
)


# main.py agrega el prefijo general /api/v1.
router = APIRouter(prefix="/especies", tags=["Especies"])


# La consulta administrativa también exige permiso de administrador.
@router.get("", response_model=list[EspecieOut])
def listar(
    activo: bool | None = None,  # False pide inactivos; None incluye ambos estados.
    db: Session = Depends(get_db),  # Comparte la sesión de la solicitud.
    usuario_administrador: Usuario = Depends(
        require_rol(RolUsuario.ADMINISTRADOR),  # Revalida el permiso contra la base.
    ),  # Admite usuarios multirrol que incluyan administrador.
) -> list[Especie]:
    """Lista especies con filtro opcional, sin modificar ni auditar."""
    # Pasa también False sin perder el filtro de inactivos.
    return listar_especies(db, activo=activo)


# El schema de salida limita la respuesta a id, nombre y activo.
@router.get("/{especie_id}", response_model=EspecieOut)
def obtener(
    especie_id: int,  # FastAPI rechaza ids de ruta no enteros.
    db: Session = Depends(get_db),  # Mantiene la sesión común de la solicitud.
    usuario_administrador: Usuario = Depends(
        require_rol(RolUsuario.ADMINISTRADOR),  # Protege también detalles inactivos.
    ),  # La identidad nunca procede de parámetros del cliente.
) -> Especie:
    """Obtiene una especie o responde 404 cuando no existe."""
    # Delega la consulta sin replicar SQL en el router.
    especie = obtener_especie(db, especie_id)
    # La ausencia de un detalle es diferente de un listado vacío válido.
    if especie is None:
        # Devuelve el mensaje público previsto, sin detalles SQL.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Especie no encontrada")
    # Incluye registros inactivos cuando el administrador solicita su detalle.
    return especie


# El alta asigna identidad y estado en el servidor y responde 201.
@router.post("", response_model=EspecieOut, status_code=status.HTTP_201_CREATED)
def crear(
    datos: EspecieCreate,  # Valida nombre y rechaza campos ajenos al contrato.
    db: Session = Depends(get_db),  # El servicio recibe la sesión de autenticación.
    usuario_administrador: Usuario = Depends(
        require_rol(RolUsuario.ADMINISTRADOR),  # Entrega el actor real del historial.
    ),  # No recibe usuario_id desde el cuerpo de la petición.
) -> Especie:
    """Crea una especie auditada y traduce únicamente la duplicidad conocida."""
    # La transacción pertenece al servicio, no a esta capa HTTP.
    try:
        # Confirma catálogo y evento con el administrador autenticado.
        return crear_especie(db, datos, usuario_administrador)
    # No confunde restricciones ajenas o errores inesperados con nombres ocupados.
    except EspecieDuplicadaError as error:
        # Usa un mensaje fijo en lugar del texto de la excepción o del controlador.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ya existe una especie con ese nombre") from error


# PUT permite renombrar, activar y desactivar sin borrar registros.
@router.put("/{especie_id}", response_model=EspecieOut)
def actualizar(
    especie_id: int,  # Conserva la identidad interna del recurso.
    datos: EspecieUpdate,  # Admite vacío o None; False solicita desactivación.
    db: Session = Depends(get_db),  # Comparte sesión para reglas y auditoría.
    usuario_administrador: Usuario = Depends(
        require_rol(RolUsuario.ADMINISTRADOR),  # El permiso se decide desde la base.
    ),  # Identifica al responsable de cualquier modificación efectiva.
) -> Especie:
    """Actualiza mediante el servicio y traduce ausencias y conflictos concretos."""
    # La consulta previa permite responder 404 antes de delegar la escritura.
    especie = obtener_especie(db, especie_id)
    # El servicio no recibe un recurso inexistente.
    if especie is None:
        # Conserva el mensaje del detalle para la misma identidad ausente.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Especie no encontrada")
    # El servicio recarga bajo bloqueo y puede detectar una desaparición posterior.
    try:
        # No calcula diferencias, bloquea ni confirma desde el router.
        return actualizar_especie(db, especie, datos, usuario_administrador)
    # La comprobación inicial no garantiza que el registro siga existiendo.
    except EspecieNoEncontradaError as error:
        # Traduce exclusivamente la ausencia reconocida por el servicio.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Especie no encontrada") from error
    # Incluye conflictos con nombres reservados por especies inactivas.
    except EspecieDuplicadaError as error:
        # No expone códigos, consultas ni parámetros SQL.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ya existe una especie con ese nombre") from error
    # Rechaza la operación completa si el padre tiene variedades activas.
    except EspecieConVariedadesActivasError as error:
        # La validación y el rollback ya corresponden al servicio.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No se puede desactivar una especie con variedades activas") from error
