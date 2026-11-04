"""Ruta de solo lectura de la trazabilidad de una tarja (HU23)."""

# Agrupa rutas, inyecta dependencias y responde errores HTTP.
from fastapi import APIRouter, Depends, HTTPException, status
# Anota la sesión que FastAPI entrega a cada solicitud.
from sqlalchemy.orm import Session

# Id en rango y autorización contra la base por lista exacta de roles.
from app.api.deps import IdRuta, require_roles
# Proporciona una sesión por petición.
from app.core.database import get_db
# Roles permitidos.
from app.models.usuario import RolUsuario
# Contrato de salida.
from app.schemas.trazabilidad import TrazabilidadOut
# Consulta de solo lectura.
from app.services.trazabilidad import trazabilidad_tarja


# main.py agrega el prefijo general /api/v1.
router = APIRouter(
    prefix="/trazabilidad",  # Ruta base del módulo.
    tags=["Trazabilidad"],  # Sección que muestra /docs.
    dependencies=[
        Depends(
            require_roles(
                RolUsuario.GERENCIA,  # Responde reclamos y consultas de productores (HU23).
                RolUsuario.ADMINISTRADOR,  # Accede a todos los módulos.
            )  # Finaliza la lista de roles.
        )  # Finaliza la dependencia.
    ],  # La dependencia protege la ruta.
)  # Finaliza la declaración del router.


# Recorrido de una tarja por su número (HU23). Solo GET: la consulta no modifica datos (criterio 3).
@router.get("/tarjas/{numero_tarja}", response_model=TrazabilidadOut)
def obtener(
    numero_tarja: IdRuta,  # Número en rango; si no, 422.
    db: Session = Depends(get_db),  # Sesión de la petición.
) -> dict:
    # Delega la consulta al servicio.
    recorrido = trazabilidad_tarja(db, numero_tarja)
    # Una tarja inexistente responde 404.
    if recorrido is None:
        # Corta la petición con el mensaje para el usuario.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No existe la tarja N° {numero_tarja}")
    # Devuelve el recorrido.
    return recorrido
