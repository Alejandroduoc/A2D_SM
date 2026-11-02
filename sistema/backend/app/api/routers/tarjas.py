"""Rutas de registro y consulta de tarjas de recepción."""

# Agrupa rutas, inyecta dependencias, valida la URL y responde errores HTTP.
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
# Anota la sesión que FastAPI entrega a cada solicitud.
from sqlalchemy.orm import Session

# Autorización contra la base: usuario actual y lista exacta de roles.
from app.api.deps import get_current_user, require_roles
# Proporciona una sesión por petición.
from app.core.database import get_db
# Mayor id posible; un número mayor responde 422 en vez de un error interno.
from app.core.validators import MAX_INT_SQL_SERVER
# Modelo que devuelve el servicio antes de serializarlo.
from app.models.tarja import Tarja
# Roles permitidos y usuario autenticado.
from app.models.usuario import RolUsuario, Usuario
# Contratos de entrada y salida de la API.
from app.schemas.tarja import PendientesProductorOut, TarjaCreate, TarjaOut
# Delega las reglas de negocio al servicio.
from app.services.tarja import (
    CatalogoNoValidoError,  # Productor o catálogo inexistente o inactivo.
    KilosNetosNoValidosError,  # Kilos netos cero o negativos.
    obtener_tarja,  # Detalle de una tarja.
    pendientes_productor,  # Acumulados del productor.
    registrar_tarja,  # Alta en una sola transacción.
)  # Finaliza las importaciones del servicio.


# main.py agrega el prefijo general /api/v1.
router = APIRouter(
    prefix="/tarjas",  # Ruta base del módulo.
    tags=["Tarjas"],  # Sección que muestra /docs.
    # Solo recepción y administración acceden; require_roles consulta los roles en la base.
    dependencies=[
        Depends(
            require_roles(
                RolUsuario.OPERADOR_RECEPCION,  # Registra las tarjas.
                RolUsuario.ADMINISTRADOR,  # Puede ejecutar las operaciones de recepción.
            )  # Finaliza la lista de roles.
        )  # Finaliza la dependencia.
    ],  # La dependencia protege las tres rutas.
)  # Finaliza la declaración del router.


# Registra una tarja, su entrada de bandejas y sus auditorías.
@router.post("", response_model=TarjaOut, status_code=status.HTTP_201_CREATED)
def crear(
    datos: TarjaCreate,  # Cuerpo ya validado; un dato inválido responde 422.
    db: Session = Depends(get_db),  # Sesión de la petición.
    usuario: Usuario = Depends(get_current_user),  # Responsable leído de la base, nunca del JSON.
) -> Tarja:
    # El servicio controla la transacción completa.
    try:
        # Devuelve la tarja ya confirmada.
        return registrar_tarja(db, datos, usuario)
    # Los errores de negocio no son fallas del servidor.
    except (CatalogoNoValidoError, KilosNetosNoValidosError) as error:
        # Traduce el error a 400 con el mensaje para el operador.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,  # Datos válidos en forma, rechazados por el negocio.
            detail=str(error),  # Mensaje definido por el servicio.
        ) from error  # Conserva la causa original.


# Debe declararse antes de /{tarja_id} para no interpretar "pendientes" como id.
@router.get("/pendientes", response_model=PendientesProductorOut)
def pendientes(
    productor_id: int = Query(gt=0, le=MAX_INT_SQL_SERVER),  # Obligatorio y en rango; si no, 422.
    db: Session = Depends(get_db),  # Sesión de la petición.
) -> PendientesProductorOut:
    # Obtiene la cantidad de tarjas y la suma de sus kilos netos.
    cantidad, kilos = pendientes_productor(db, productor_id)
    # Arma la respuesta con los acumulados del productor (decisión D).
    return PendientesProductorOut(
        productor_id=productor_id,  # Productor consultado.
        tarjas_sin_procesar=cantidad,  # Tarjas RECEPCIONADA o PARCIAL.
        kilos_sin_procesar=kilos,  # Suma de sus kilos netos.
    )  # Finaliza la respuesta.


# Obtiene el detalle persistido de una tarja.
@router.get("/{tarja_id}", response_model=TarjaOut)
def obtener(
    tarja_id: int = Path(gt=0, le=MAX_INT_SQL_SERVER),  # Id en rango; si no, 422.
    db: Session = Depends(get_db),  # Sesión de la petición.
) -> Tarja:
    # Busca la tarja por su identidad interna.
    tarja = obtener_tarja(db, tarja_id)
    # Una tarja inexistente responde 404.
    if tarja is None:
        # Corta la petición con el mensaje de recurso no encontrado.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,  # El recurso no existe.
            detail="Tarja no encontrada",  # Mensaje para el cliente.
        )  # Finaliza el error.
    # Devuelve la tarja encontrada.
    return tarja
