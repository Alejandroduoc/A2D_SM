"""Mantenimiento de variedades con autorización y traducción de errores HTTP."""

# Incluye Query para validar el filtro opcional de especie en la URL.
from fastapi import APIRouter, Depends, HTTPException, Query, status
# Anota la sesión que comparte autenticación con los servicios.
from sqlalchemy.orm import Session

# Exige permisos a partir de los roles vigentes en la base de datos.
from app.api.deps import require_rol
# Proporciona la misma dependencia de sesión usada por autenticación.
from app.core.database import get_db
# Recurso de salida y actor autenticado de las escrituras.
from app.models.variedad import Variedad
from app.models.usuario import RolUsuario, Usuario
# El schema de edición no permite reasignar la especie.
from app.schemas.variedad import VariedadCreate, VariedadOut, VariedadUpdate
# Las escrituras de hijas pueden rechazar referencias o estados del padre.
from app.services.especie import EspecieInactivaError, EspecieNoEncontradaError
# Delega reglas de nombres, bloqueos, cambios de estado y auditoría.
from app.services.variedad import (
    VariedadDuplicadaError,  # Nombre reservado dentro de la misma especie.
    VariedadNoEncontradaError,  # Ausencia detectada al recargar durante la escritura.
    actualizar_variedad,  # Conserva id y especie y audita diferencias efectivas.
    crear_variedad,  # Exige padre activo y confirma alta e historial juntos.
    listar_variedades,  # Admite filtros opcionales de estado y especie.
    obtener_variedad,  # Consulta el detalle incluyendo registros inactivos.
)


# El prefijo general se incorpora una sola vez desde main.py.
router = APIRouter(prefix="/variedades", tags=["Variedades"])


# Todo el mantenimiento, incluidas las consultas, requiere administrador.
@router.get("", response_model=list[VariedadOut])
def listar(
    activo: bool | None = None,  # No pierde False al filtrar registros inactivos.
    especie_id: int | None = Query(default=None, gt=0),  # Convierte el texto de URL a entero positivo.
    db: Session = Depends(get_db),  # Comparte la sesión de la solicitud.
    usuario_administrador: Usuario = Depends(
        require_rol(RolUsuario.ADMINISTRADOR),  # No confía en roles declarados solo en JWT.
    ),  # Las consultas operativas de otros roles corresponden a HU11.
) -> list[Variedad]:
    """Lista por estado y especie; sin coincidencias devuelve una lista vacía."""
    # No exige que exista el padre para devolver un resultado de listado válido.
    return listar_variedades(db, activo=activo, especie_id=especie_id)


# La respuesta expone exclusivamente id, especie_id, nombre y activo.
@router.get("/{variedad_id}", response_model=VariedadOut)
def obtener(
    variedad_id: int,  # Rechaza valores de ruta no enteros mediante FastAPI.
    db: Session = Depends(get_db),  # Usa la sesión compartida con autorización.
    usuario_administrador: Usuario = Depends(
        require_rol(RolUsuario.ADMINISTRADOR),  # Protege también los detalles inactivos.
    ),  # No amplía permisos a gerencia o a operadores.
) -> Variedad:
    """Obtiene la variedad o responde 404 con un mensaje público fijo."""
    # Delega la lectura por identidad al servicio.
    variedad = obtener_variedad(db, variedad_id)
    # Una identidad ausente debe distinguirse de un listado sin coincidencias.
    if variedad is None:
        # No incluye información SQL ni nombres de restricciones.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variedad no encontrada")
    # El schema de salida serializa únicamente las columnas públicas.
    return variedad


# La creación inicial es activa y conserva la especie elegida en el alta.
@router.post("", response_model=VariedadOut, status_code=status.HTTP_201_CREATED)
def crear(
    datos: VariedadCreate,  # Exige nombre y especie_id entero JSON positivo estricto.
    db: Session = Depends(get_db),  # El mismo contexto contiene bloqueo, cambio y evento.
    usuario_administrador: Usuario = Depends(
        require_rol(RolUsuario.ADMINISTRADOR),  # Proporciona el actor real a la auditoría.
    ),  # El cliente no elige usuario_id ni acción de historial.
) -> Variedad:
    """Delega el alta y traduce solo referencias, estados y duplicidad conocidos."""
    # Mantiene los controles transaccionales en el servicio de negocio.
    try:
        # El servicio bloquea el padre y confirma conjuntamente variedad y evento.
        return crear_variedad(db, datos, usuario_administrador)
    # La referencia estructuralmente válida podría no corresponder a una especie.
    except EspecieNoEncontradaError as error:
        # No convierte una ausencia en conflicto de nombre.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Especie no encontrada") from error
    # Una especie inactiva impide habilitar una nueva variedad.
    except EspecieInactivaError as error:
        # Conserva el mensaje de estado previsto en el contrato.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="La especie debe estar activa para habilitar una variedad") from error
    # Incluye nombres reservados por variedades inactivas de la misma especie.
    except VariedadDuplicadaError as error:
        # No expone el error del controlador SQL.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ya existe una variedad con ese nombre en la especie") from error


# Activa, desactiva o renombra sin cambiar la especie ni borrar registros.
@router.put("/{variedad_id}", response_model=VariedadOut)
def actualizar(
    variedad_id: int,  # Identidad estable que se conserva en la respuesta y auditoría.
    datos: VariedadUpdate,  # especie_id se rechaza como campo extra con 422.
    db: Session = Depends(get_db),  # Comparte la sesión con el actor autenticado.
    usuario_administrador: Usuario = Depends(
        require_rol(RolUsuario.ADMINISTRADOR),  # Revalida los permisos desde la base.
    ),  # Un usuario multirrol con administrador también está autorizado.
) -> Variedad:
    """Edita mediante el servicio y conserva la traducción precisa de sus errores."""
    # La consulta inicial evita pasar una variedad inexistente al servicio.
    variedad = obtener_variedad(db, variedad_id)
    # No intenta crear eventos ni escribir cuando el detalle está ausente.
    if variedad is None:
        # Utiliza el mismo mensaje de la consulta de detalle.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variedad no encontrada")
    # La recarga bajo bloqueo vuelve a validar identidad, especie y estado.
    try:
        # El servicio resuelve diferencias, reglas, rollback y confirmación.
        return actualizar_variedad(db, variedad, datos, usuario_administrador)
    # La variedad puede desaparecer después de la consulta previa.
    except VariedadNoEncontradaError as error:
        # No devuelve el texto interno sobre asociación o bloqueo.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variedad no encontrada") from error
    # También contempla una referencia al padre ausente durante la escritura.
    except EspecieNoEncontradaError as error:
        # Distingue ausencia del padre de ausencia de la hija.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Especie no encontrada") from error
    # Reactivar o dejar activa una hija exige una especie activa.
    except EspecieInactivaError as error:
        # La excepción ya provocó rollback en el servicio.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="La especie debe estar activa para habilitar una variedad") from error
    # El nombre sigue siendo único dentro de su propia especie.
    except VariedadDuplicadaError as error:
        # Los detalles ODBC y parámetros permanecen fuera de la respuesta.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ya existe una variedad con ese nombre en la especie") from error
