"""Rutas de solo lectura que llenan las listas de los formularios de recepción (HU11)."""

# Agrupa rutas, inyecta dependencias y valida los parámetros de la URL.
from fastapi import APIRouter, Depends, Query
# Anota la sesión que FastAPI entrega a cada solicitud.
from sqlalchemy.orm import Session

# Autorización por lista exacta de roles; consulta el usuario y sus roles en la base.
from app.api.deps import require_roles
# Proporciona una sesión por petición.
from app.core.database import get_db
# Modelos que devuelve el servicio antes de serializarlos.
from app.models.calidad import Calidad
from app.models.especie import Especie
from app.models.productor import Productor
from app.models.sistema_productivo import SistemaProductivo
from app.models.tipo_bandeja import TipoBandeja
# Roles que pueden leer las opciones.
from app.models.usuario import RolUsuario
from app.models.variedad import Variedad
# Limitan la salida a id y nombre (más la tara en bandejas, o id, RUT y razón social en productores).
from app.schemas.opciones import OpcionBandejaOut, OpcionOut, ProductorOpcionOut
# Delega las consultas de solo lectura al servicio.
from app.services.opciones import (
    buscar_productores,  # Productores activos por RUT o razón social.
    calidades_activas,  # Calidades activas.
    especies_activas,  # Especies activas.
    sistemas_productivos_activos,  # Sistemas productivos activos.
    tipos_bandeja_activos,  # Tipos de bandeja activos con su tara.
    variedades_activas,  # Variedades activas de una especie activa.
)  # Finaliza las importaciones del servicio.


# main.py agrega el prefijo general /api/v1.
router = APIRouter(
    prefix="/opciones",  # Separa la lectura para formularios del mantenimiento.
    tags=["Opciones de formularios"],  # Sección que muestra /docs.
    # Solo recepción y administración leen opciones; gerencia y proceso no las usan.
    # require_roles (lista exacta) y no require_rol: el jerárquico dejaría pasar a gerencia.
    dependencies=[Depends(require_roles(RolUsuario.OPERADOR_RECEPCION, RolUsuario.ADMINISTRADOR))],
)  # La dependencia protege las seis rutas; ninguna queda abierta por olvido.


# Especies activas para el selector de especie.
@router.get("/especies", response_model=list[OpcionOut])
# Solo recibe la sesión de la petición.
def listar_especies(db: Session = Depends(get_db)) -> list[Especie]:
    """Lista las especies activas ordenadas por nombre."""
    # Delega la consulta al servicio; no se audita porque es una lectura.
    return especies_activas(db)


# Variedades activas de la especie elegida en el formulario.
@router.get("/variedades", response_model=list[OpcionOut])
# Recibe el id de la especie y la sesión de la petición.
def listar_variedades(
    especie_id: int = Query(gt=0),  # Obligatorio y mayor que 0; si falta o es 0, FastAPI responde 422.
    db: Session = Depends(get_db),  # Sesión de la petición.
) -> list[Variedad]:
    """Lista las variedades activas de una especie activa; [] si la especie no existe o está inactiva."""
    # Delega la consulta al servicio.
    return variedades_activas(db, especie_id)


# Calidades activas para el selector de calidad.
@router.get("/calidades", response_model=list[OpcionOut])
# Solo recibe la sesión de la petición.
def listar_calidades(db: Session = Depends(get_db)) -> list[Calidad]:
    """Lista las calidades activas ordenadas por nombre."""
    # Delega la consulta al servicio.
    return calidades_activas(db)


# Sistemas productivos activos para su selector.
@router.get("/sistemas-productivos", response_model=list[OpcionOut])
# Solo recibe la sesión de la petición.
def listar_sistemas_productivos(db: Session = Depends(get_db)) -> list[SistemaProductivo]:
    """Lista los sistemas productivos activos ordenados por nombre."""
    # Delega la consulta al servicio.
    return sistemas_productivos_activos(db)


# Tipos de bandeja activos con su tara, para el cálculo de kilos netos de la tarja (E3).
@router.get("/tipos-bandeja", response_model=list[OpcionBandejaOut])
# Solo recibe la sesión de la petición.
def listar_tipos_bandeja(db: Session = Depends(get_db)) -> list[TipoBandeja]:
    """Lista los tipos de bandeja activos ordenados por nombre, con su tara."""
    # Delega la consulta al servicio; una bandeja desactivada no aparece.
    return tipos_bandeja_activos(db)


# Buscador de productores activos por RUT o razón social.
@router.get("/productores", response_model=list[ProductorOpcionOut])
# Recibe el texto escrito por el operador y la sesión de la petición.
def listar_productores(
    buscar: str = Query(max_length=50),  # Obligatorio; si falta o supera 50 caracteres, FastAPI responde 422.
    db: Session = Depends(get_db),  # Sesión de la petición.
) -> list[Productor]:
    """Busca hasta 20 productores activos; [] si el texto tiene menos de 2 caracteres."""
    # Delega la búsqueda al servicio.
    return buscar_productores(db, buscar)
