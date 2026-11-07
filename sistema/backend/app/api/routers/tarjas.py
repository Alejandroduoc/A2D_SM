"""Rutas de registro y consulta de tarjas de recepción."""

# Filtros por fecha de recepción.
from datetime import date

# Agrupa rutas, inyecta dependencias, valida la URL y responde errores HTTP.
from fastapi import APIRouter, Depends, HTTPException, Query, status
# Anota la sesión que FastAPI entrega a cada solicitud.
from sqlalchemy.orm import Session

# Autorización contra la base: usuario actual y lista exacta de roles.
from app.api.deps import IdRuta, get_current_user, require_roles
# Proporciona una sesión por petición.
from app.core.database import get_db
# Mayor id posible; un número mayor responde 422 en vez de un error interno.
from app.core.validators import MAX_INT_SQL_SERVER
# Modelo que devuelve el servicio antes de serializarlo.
from app.models.tarja import EstadoTarja, Tarja
# Roles permitidos y usuario autenticado.
from app.models.usuario import RolUsuario, Usuario
# Contratos de entrada y salida de la API.
from app.schemas.tarja import PendientesProductorOut, SaldoBandejaOut, TarjaCreate, TarjaDetalleOut, TarjaOut, TarjaResumenOut, TarjaUpdate
# Delega las reglas de negocio al servicio.
from app.services.tarja import (
    anular_tarja,  # Anulación sin borrar (HU24).
    CatalogoNoValidoError,  # Productor o catálogo inexistente o inactivo.
    editar_tarja,  # Corrección trazable antes del procesamiento (HU20).
    KilosNetosNoValidosError,  # Kilos netos cero o negativos.
    listar_tarjas,  # Listado con filtros (HU17).
    obtener_tarja,  # Detalle de una tarja.
    pendientes_productor,  # Acumulados del productor.
    registrar_impresion,  # Impresión o reimpresión (HU16).
    registrar_tarja,  # Alta en una sola transacción.
    saldo_bandejas_productor,  # Saldo de bandejas (HU15).
    TarjaAnuladaError,  # Una tarja anulada no se imprime.
    TarjaNoAnulableError,  # Ya anulada o con kilos en procesos.
    TarjaNoEncontradaError,  # La tarja no existe.
    TarjaNoEditableError,  # Tarja anulada o con kilos ya procesados.
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


# Corrige una tarja recepcionada y conserva la auditoría de antes y después (HU20).
@router.put("/{tarja_id}", response_model=TarjaDetalleOut)
def editar(
    tarja_id: IdRuta,  # Identidad validada en la ruta.
    datos: TarjaUpdate,  # Campos corregibles y motivo obligatorio.
    db: Session = Depends(get_db),  # Sesión de la petición.
    usuario: Usuario = Depends(get_current_user),  # Responsable autenticado de la corrección.
) -> dict:
    # El servicio mantiene una sola transacción entre tarja, saldo y auditoría.
    try:
        # Devuelve el detalle actualizado.
        return editar_tarja(db, tarja_id, datos, usuario)
    # La identidad no existe.
    except TarjaNoEncontradaError as error:
        # Responde como recurso no encontrado.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    # La tarja ya no cumple las condiciones de corrección.
    except TarjaNoEditableError as error:
        # Responde conflicto para que el cliente recargue su estado.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    # Los catálogos o los kilos son inválidos para la regla de negocio.
    except (CatalogoNoValidoError, KilosNetosNoValidosError) as error:
        # Responde con la explicación utilizable por el operador.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error


# Lista las tarjas según los filtros recibidos (HU17 criterio 1).
@router.get("", response_model=list[TarjaResumenOut])
def listar(
    numero_tarja: int | None = Query(default=None, gt=0, le=MAX_INT_SQL_SERVER),  # Número exacto.
    productor_id: int | None = Query(default=None, gt=0, le=MAX_INT_SQL_SERVER),  # Productor elegido.
    desde: date | None = Query(default=None),  # Primer día de recepción, incluido.
    hasta: date | None = Query(default=None),  # Último día de recepción, incluido.
    estado: EstadoTarja | None = Query(default=None),  # Un estado que no existe responde 422.
    db: Session = Depends(get_db),  # Sesión de la petición.
) -> list[dict]:
    # Un rango invertido no tiene resultados posibles: se avisa en vez de mostrar una lista vacía.
    if desde is not None and hasta is not None and desde > hasta:
        # Responde con el mensaje para el operador.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,  # Parámetros inválidos.
            detail="La fecha inicial no puede ser posterior a la final",  # Mensaje para el operador.
        )  # Finaliza el error.
    # Delega la consulta de solo lectura al servicio.
    return listar_tarjas(db, numero_tarja, productor_id, desde, hasta, estado)


# Debe declararse antes de /{tarja_id} para no interpretar "pendientes" como id.
@router.get("/pendientes", response_model=PendientesProductorOut)
def pendientes(
    productor_id: int = Query(gt=0, le=MAX_INT_SQL_SERVER),  # Obligatorio y en rango; si no, 422.
    db: Session = Depends(get_db),  # Sesión de la petición.
) -> PendientesProductorOut:
    # Obtiene la cantidad de tarjas y los kilos que les faltan por procesar.
    cantidad, kilos = pendientes_productor(db, productor_id)
    # Arma la respuesta con los acumulados del productor (decisión D).
    return PendientesProductorOut(
        productor_id=productor_id,  # Productor consultado.
        tarjas_sin_procesar=cantidad,  # Tarjas RECEPCIONADA o PARCIAL.
        kilos_sin_procesar=kilos,  # Kilos netos menos lo procesado.
    )  # Finaliza la respuesta.


# Saldo de bandejas de un productor, por tipo de bandeja (HU15 criterio 3).
# Debe declararse antes de /{tarja_id} para no interpretar "saldo-bandejas" como id.
@router.get("/saldo-bandejas", response_model=list[SaldoBandejaOut])
def saldo_bandejas(
    productor_id: int = Query(gt=0, le=MAX_INT_SQL_SERVER),  # Obligatorio y en rango; si no, 422.
    db: Session = Depends(get_db),  # Sesión de la petición.
) -> list[dict]:
    # Delega el cálculo de solo lectura al servicio.
    return saldo_bandejas_productor(db, productor_id)


# Obtiene el detalle completo de una tarja (HU17 criterio 2).
@router.get("/{tarja_id}", response_model=TarjaDetalleOut)
def obtener(
    tarja_id: IdRuta,  # Id en rango; si no, 422.
    db: Session = Depends(get_db),  # Sesión de la petición.
) -> dict:
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


# Registra una impresión o reimpresión de la tarja (HU16 criterio 3).
@router.post("/{tarja_id}/imprimir", response_model=TarjaDetalleOut)
def imprimir(
    tarja_id: IdRuta,  # Id en rango; si no, 422.
    db: Session = Depends(get_db),  # Sesión de la petición.
    usuario: Usuario = Depends(get_current_user),  # Responsable leído de la base.
) -> dict:
    # El servicio controla la transacción.
    try:
        # Devuelve la tarja con el contador actualizado.
        return registrar_impresion(db, tarja_id, usuario)
    # La tarja no existe.
    except TarjaNoEncontradaError as error:
        # Responde 404 con el mensaje del servicio.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    # La tarja está anulada.
    except TarjaAnuladaError as error:
        # Responde 409: la petición es válida, pero el estado de la tarja no lo permite.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


# Anula una tarja de recepción, solo el administrador (HU24 criterio 1).
@router.post(
    "/{tarja_id}/anular",  # POST y no DELETE: la tarja no se borra.
    response_model=TarjaDetalleOut,  # Devuelve la tarja anulada.
    dependencies=[Depends(require_roles(RolUsuario.ADMINISTRADOR))],  # Más estricto que el resto del router.
)  # Finaliza la declaración de la ruta.
def anular(
    tarja_id: IdRuta,  # Id en rango; si no, 422.
    db: Session = Depends(get_db),  # Sesión de la petición.
    usuario: Usuario = Depends(get_current_user),  # Responsable leído de la base.
) -> dict:
    # El servicio controla la transacción.
    try:
        # Devuelve la tarja ya anulada.
        return anular_tarja(db, tarja_id, usuario)
    # La tarja no existe.
    except TarjaNoEncontradaError as error:
        # Responde 404 con el mensaje del servicio.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    # Ya estaba anulada o tiene kilos en procesos.
    except TarjaNoAnulableError as error:
        # Responde 409: la petición es válida, pero el estado de la tarja no lo permite.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
