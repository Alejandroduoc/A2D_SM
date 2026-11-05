"""Rutas de consulta de la bitácora de auditoría (HU22)."""

# Fechas de los filtros.
from datetime import date

# Agrupa rutas, valida parámetros y responde errores HTTP.
from fastapi import APIRouter, Depends, HTTPException, Query
# Sesión de base de datos.
from sqlalchemy.orm import Session

# Autoriza contra la base de datos por roles exactos.
from app.api.deps import require_roles
# Entrega una sesión por petición.
from app.core.database import get_db
# Mayor salto de filas admitido; más allá responde 422 en vez de un error interno.
from app.core.validators import MAX_INT_SQL_SERVER
# Acciones que se pueden filtrar.
from app.models.auditoria import AccionAuditoria
# Roles con acceso a la consulta.
from app.models.usuario import RolUsuario
# Contratos públicos y filtros internos.
from app.schemas.auditoria import BitacoraFiltros, BitacoraOut, UsuarioAuditoriaOut
# Consultas de solo lectura.
from app.services.auditoria_consulta import consultar_bitacora, tablas_de_bitacora, usuarios_de_bitacora


# Solo gerencia y administración pueden consultar la bitácora.
router = APIRouter(
    prefix="/auditoria",  # Ruta base del módulo.
    tags=["Auditoría"],  # Sección que muestra /docs.
    dependencies=[Depends(require_roles(RolUsuario.GERENCIA, RolUsuario.ADMINISTRADOR))],  # Protege todas las rutas.
)  # Finaliza la declaración del router.


# Solo GET: nadie puede editar ni borrar la auditoría desde el sistema (HU21 criterio 3).
@router.get("", response_model=BitacoraOut)
def listar(
    usuario_id: str | None = Query(default=None, max_length=36),  # Largo de usuarios.id.
    fecha_desde: date | None = None,  # Primer día, en hora de Chile.
    fecha_hasta: date | None = None,  # Último día, en hora de Chile.
    tabla: str | None = Query(default=None, max_length=50),  # Largo de auditoria.tabla.
    accion: AccionAuditoria | None = None,  # Solo las tres acciones guardadas.
    limite: int = Query(default=50, ge=1, le=100),  # Filas por página.
    offset: int = Query(default=0, ge=0, le=MAX_INT_SQL_SERVER),  # Filas que se saltan.
    db: Session = Depends(get_db),  # Sesión de la petición.
) -> dict:
    """Consulta eventos con filtros de usuario, fechas, tabla y acción."""

    # Rechaza un intervalo invertido antes de consultar la base.
    if fecha_desde and fecha_hasta and fecha_desde > fecha_hasta:
        raise HTTPException(status_code=422, detail="La fecha inicial no puede ser posterior a la fecha final")
    # El final del día se calcula con el día siguiente, y el último del calendario no lo tiene.
    if fecha_hasta == date.max:
        raise HTTPException(status_code=422, detail="La fecha final está fuera de rango")
    # Agrupa filtros para centralizar la conversión de fechas y la consulta.
    filtros = BitacoraFiltros(
        usuario_id=usuario_id,  # Responsable.
        fecha_desde=fecha_desde,  # Desde.
        fecha_hasta=fecha_hasta,  # Hasta.
        tabla=tabla,  # Tabla.
        accion=accion,  # Acción.
    )  # Finaliza los filtros.
    # Devuelve solo lectura; no hace commit ni crea auditoría.
    return consultar_bitacora(db, filtros, limite, offset)


@router.get("/usuarios", response_model=list[UsuarioAuditoriaOut])
def listar_usuarios(db: Session = Depends(get_db)) -> list[dict]:
    """Lista los actores que tienen eventos para llenar el filtro."""

    # El servicio devuelve solo id y nombre completo.
    return usuarios_de_bitacora(db)


@router.get("/tablas", response_model=list[str])
def listar_tablas(db: Session = Depends(get_db)) -> list[str]:
    """Lista las tablas que tienen eventos para llenar el filtro."""

    # La pantalla les pone el nombre legible.
    return tablas_de_bitacora(db)
