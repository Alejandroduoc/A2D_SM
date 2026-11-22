"""Rutas de registro y consulta de procesos de tarjas (HU18)."""

# Agrupa rutas, inyecta dependencias, valida la URL y responde errores HTTP.
from fastapi import APIRouter, Depends, HTTPException, Query, status
# Anota la sesión que FastAPI entrega a cada solicitud.
from sqlalchemy.orm import Session

# Autorización contra la base: usuario actual, id de ruta y lista exacta de roles.
from app.api.deps import IdRuta, get_current_user, require_roles
# Proporciona una sesión por petición.
from app.core.database import get_db
# Mayor id posible; un número mayor responde 422 en vez de un error interno.
from app.core.validators import MAX_INT_SQL_SERVER
# Modelo que devuelve el servicio antes de serializarlo.
from app.models.embalaje import Embalaje
# Roles permitidos y usuario autenticado.
from app.models.usuario import RolUsuario, Usuario
# Contratos de entrada y salida de la API.
from app.schemas.proceso import (
    EmbalajeOpcionOut,  # Embalaje del formulario.
    ProcesoCreate,  # Alta de un proceso.
    ProcesoDetalleOut,  # Proceso con sus tarjas.
    ProcesoEdicion,  # Cómo debe quedar un proceso registrado.
    ProcesoResumenOut,  # Fila del listado.
    RendimientoOut,  # Rendimiento y merma por folios (HU19).
    TarjaDisponibleOut,  # Tarja que se puede procesar.
    TarjaTerminadaOut,  # Tarja cerrada con su merma.
)  # Finaliza las importaciones de schemas.
# Delega las reglas de negocio al servicio.
from app.services.proceso import (
    FoliosNoValidosError,  # Folio con formato inválido.
    KilosProcesoNoValidosError,  # Kilos faltantes, sobrantes o sobre la capacidad.
    MezclaNoPermitidaError,  # Tarjas con distinta fruta.
    ProcesoNoEditableError,  # Proceso anulado.
    ProcesoNoEncontradoError,  # El proceso no existe.
    SaldoInsuficienteError,  # Más kilos de los que le quedan a la tarja.
    TarjaNoProcesableError,  # Tarja anulada o terminada.
    anular_proceso,  # Anulación sin borrar (HU25).
    calcular_rendimiento,  # Rendimiento y merma por folios (HU19).
    editar_proceso,  # Corrige un proceso registrado.
    embalajes_activos,  # Lista del formulario.
    listar_procesos,  # Listado.
    listar_tarjas_disponibles,  # Tarjas con kilos por procesar.
    listar_tarjas_rebajadas,  # Tarjas con merma rebajada.
    obtener_proceso,  # Detalle.
    reabrir_tarja,  # Deshace una rebaja.
    registrar_proceso,  # Alta en una sola transacción.
    terminar_tarja,  # Rebaja el saldo como merma.
)  # Finaliza las importaciones del servicio.
# Errores de tarjas que también ocurren aquí.
from app.services.tarja import CatalogoNoValidoError, TarjaNoEncontradaError


# main.py agrega el prefijo general /api/v1.
router = APIRouter(
    prefix="/procesos",  # Ruta base del módulo.
    tags=["Procesos"],  # Sección que muestra /docs.
    # require_roles (lista exacta) y no require_rol: el jerárquico dejaría pasar a gerencia.
    dependencies=[
        Depends(
            require_roles(
                RolUsuario.OPERADOR_PROCESO,  # Registra los procesos.
                RolUsuario.ADMINISTRADOR,  # Puede ejecutar las operaciones de proceso.
            )  # Finaliza la lista de roles.
        )  # Finaliza la dependencia.
    ],  # La dependencia protege todas las rutas.
)  # Finaliza la declaración del router.


# Registra un proceso con sus tarjas.
@router.post("", response_model=ProcesoDetalleOut, status_code=status.HTTP_201_CREATED)
def crear(
    datos: ProcesoCreate,  # Cuerpo ya validado; un dato inválido responde 422.
    db: Session = Depends(get_db),  # Sesión de la petición.
    usuario: Usuario = Depends(get_current_user),  # Responsable leído de la base, nunca del JSON.
) -> dict:
    # El servicio controla la transacción completa.
    try:
        # Devuelve el proceso ya confirmado.
        return registrar_proceso(db, datos, usuario)
    # Datos válidos en forma, rechazados por el negocio.
    except (CatalogoNoValidoError, KilosProcesoNoValidosError, MezclaNoPermitidaError) as error:
        # Responde 400 con el mensaje para el operador.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    # La tarja no existe.
    except TarjaNoEncontradaError as error:
        # Responde 404 con el mensaje del servicio.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    # El estado o el saldo de la tarja no lo permiten.
    except (SaldoInsuficienteError, TarjaNoProcesableError) as error:
        # Responde 409 con el mensaje del servicio.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


# Lista los procesos, los más recientes primero.
@router.get("", response_model=list[ProcesoResumenOut])
def listar(db: Session = Depends(get_db)) -> list[dict]:
    # Delega la consulta de solo lectura al servicio.
    return listar_procesos(db)


# Rendimiento y merma de las tarjas asociadas a los folios (HU19).
# Debe declararse antes de /{proceso_id} para no interpretar "rendimiento" como id.
@router.get("/rendimiento", response_model=RendimientoOut)
def rendimiento(
    folios: list[str] = Query(min_length=1),  # Uno o varios: ?folios=P1&folios=P2. Sin folios responde 422.
    db: Session = Depends(get_db),  # Sesión de la petición.
) -> dict:
    # El servicio solo lee: no se audita ni se guarda nada.
    try:
        # Devuelve las tarjas, su total y los folios que no entraron.
        return calcular_rendimiento(db, folios)
    # Un texto que no es un folio se avisa al operador.
    except FoliosNoValidosError as error:
        # Responde 422 con el mensaje del servicio.
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error


# Debe declararse antes de /{proceso_id} para no interpretar "embalajes" como id.
@router.get("/embalajes", response_model=list[EmbalajeOpcionOut])
def embalajes(db: Session = Depends(get_db)) -> list[Embalaje]:
    # Delega la consulta de solo lectura al servicio.
    return embalajes_activos(db)


# Debe declararse antes de /{proceso_id} para no interpretar "tarjas-disponibles" como id.
@router.get("/tarjas-disponibles", response_model=list[TarjaDisponibleOut])
def tarjas_disponibles(
    numero_tarja: int | None = Query(default=None, gt=0, le=MAX_INT_SQL_SERVER),  # Número exacto, opcional.
    db: Session = Depends(get_db),  # Sesión de la petición.
) -> list[dict]:
    # Delega la consulta de solo lectura al servicio.
    return listar_tarjas_disponibles(db, numero_tarja)


# Debe declararse antes de /{proceso_id} para no interpretar "tarjas-rebajadas" como id.
@router.get("/tarjas-rebajadas", response_model=list[TarjaDisponibleOut])
def tarjas_rebajadas(db: Session = Depends(get_db)) -> list[dict]:
    # Delega la consulta de solo lectura al servicio.
    return listar_tarjas_rebajadas(db)


# Rebaja como merma los kilos que le quedan a una tarja.
@router.post("/tarjas/{tarja_id}/terminar", response_model=TarjaTerminadaOut)
def terminar(
    tarja_id: IdRuta,  # Id en rango; si no, 422.
    db: Session = Depends(get_db),  # Sesión de la petición.
    usuario: Usuario = Depends(get_current_user),  # Responsable leído de la base.
) -> dict:
    # El servicio controla la transacción.
    try:
        # Devuelve la tarja cerrada con su merma.
        return terminar_tarja(db, tarja_id, usuario)
    # La tarja no existe.
    except TarjaNoEncontradaError as error:
        # Responde 404 con el mensaje del servicio.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    # El estado de la tarja no lo permite.
    except TarjaNoProcesableError as error:
        # Responde 409 con el mensaje del servicio.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


# Deshace una rebaja hecha por error; decisión del 03/11: operador de proceso y administrador.
@router.post("/tarjas/{tarja_id}/reabrir", response_model=TarjaTerminadaOut)
def reabrir(
    tarja_id: IdRuta,  # Id en rango; si no, 422.
    db: Session = Depends(get_db),  # Sesión de la petición.
    usuario: Usuario = Depends(get_current_user),  # Responsable leído de la base.
) -> dict:
    # El servicio controla la transacción.
    try:
        # Devuelve la tarja reabierta.
        return reabrir_tarja(db, tarja_id, usuario)
    # La tarja no existe.
    except TarjaNoEncontradaError as error:
        # Responde 404 con el mensaje del servicio.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    # La tarja no tiene una merma rebajada.
    except TarjaNoProcesableError as error:
        # Responde 409 con el mensaje del servicio.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


# Anula un proceso, solo el administrador (HU25 criterio 1).
@router.post(
    "/{proceso_id}/anular",  # POST y no DELETE: el proceso no se borra.
    response_model=ProcesoDetalleOut,  # Devuelve el proceso anulado.
    dependencies=[Depends(require_roles(RolUsuario.ADMINISTRADOR))],  # Más estricto que el resto del router.
)  # Finaliza la declaración de la ruta.
def anular(
    proceso_id: IdRuta,  # Id en rango; si no, 422.
    db: Session = Depends(get_db),  # Sesión de la petición.
    usuario: Usuario = Depends(get_current_user),  # Responsable leído de la base.
) -> dict:
    # El servicio controla la transacción.
    try:
        # Devuelve el proceso ya anulado.
        return anular_proceso(db, proceso_id, usuario)
    # El proceso no existe.
    except ProcesoNoEncontradoError as error:
        # Responde 404 con el mensaje del servicio.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    # Ya estaba anulado.
    except ProcesoNoEditableError as error:
        # Responde 409: la petición es válida, pero el estado del proceso no lo permite.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


# Corrige un proceso ya registrado; los kilos que salen vuelven a sus tarjas de recepción.
@router.put("/{proceso_id}", response_model=ProcesoDetalleOut)
def editar(
    proceso_id: IdRuta,  # Id en rango; si no, 422.
    datos: ProcesoEdicion,  # Cuerpo ya validado; un dato inválido responde 422.
    db: Session = Depends(get_db),  # Sesión de la petición.
    usuario: Usuario = Depends(get_current_user),  # Responsable leído de la base.
) -> dict:
    # El servicio controla la transacción completa.
    try:
        # Devuelve el proceso actualizado.
        return editar_proceso(db, proceso_id, datos, usuario)
    # Datos válidos en forma, rechazados por el negocio.
    except (KilosProcesoNoValidosError, MezclaNoPermitidaError) as error:
        # Responde 400 con el mensaje para el operador.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    # El proceso o la tarja no existen.
    except (ProcesoNoEncontradoError, TarjaNoEncontradaError) as error:
        # Responde 404 con el mensaje del servicio.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    # El estado o el saldo no lo permiten.
    except (ProcesoNoEditableError, SaldoInsuficienteError, TarjaNoProcesableError) as error:
        # Responde 409 con el mensaje del servicio.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


# Obtiene un proceso con sus tarjas (HU18 criterio 7).
@router.get("/{proceso_id}", response_model=ProcesoDetalleOut)
def obtener(
    proceso_id: IdRuta,  # Id en rango; si no, 422.
    db: Session = Depends(get_db),  # Sesión de la petición.
) -> dict:
    # Busca el proceso por su identidad interna.
    proceso = obtener_proceso(db, proceso_id)
    # Un proceso inexistente responde 404.
    if proceso is None:
        # Corta la petición con el mensaje de recurso no encontrado.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proceso no encontrado")
    # Devuelve el proceso encontrado.
    return proceso
