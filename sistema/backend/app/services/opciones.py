"""Consultas de solo lectura que llenan las listas de los formularios de recepción (HU11)."""

# Limpia puntos, guion y espacios del texto que escribe el operador.
import re

# Construye las consultas; func.replace quita el guion del RUT guardado; or_ une las condiciones.
from sqlalchemy import func, or_, select
# Sesión de base de datos que entrega el router.
from sqlalchemy.orm import Session

# Modelos de los catálogos y de productores que se leen; aquí no se modifica ninguno.
from app.models.calidad import Calidad
from app.models.especie import Especie
from app.models.productor import Productor
from app.models.sistema_productivo import SistemaProductivo
from app.models.variedad import Variedad

# Menos caracteres devolverían casi toda la tabla en cada tecla.
MINIMO_BUSQUEDA = 2
# Tope de resultados del buscador de productores.
MAXIMO_RESULTADOS = 20
# Texto que, sin puntos ni guion, son solo dígitos con una K opcional al final.
_PATRON_RUT = re.compile(r"\d+K?")


# Especies activas, ordenadas por nombre.
def especies_activas(db: Session) -> list[Especie]:
    # activo == True (no .is_(True)): SQL Server no acepta "IS 1".
    consulta = select(Especie).where(Especie.activo == True).order_by(Especie.nombre)  # noqa: E712
    # scalars().all() devuelve objetos Especie en vez de filas.
    return list(db.scalars(consulta).all())


# Variedades activas de una especie, solo si la especie también está activa.
def variedades_activas(db: Session, especie_id: int) -> list[Variedad]:
    # El join con Especie descarta las variedades de una especie desactivada.
    consulta = (
        select(Variedad)  # Devuelve variedades.
        .join(Especie, Variedad.especie_id == Especie.id)  # Une cada variedad con su especie.
        .where(
            Variedad.especie_id == especie_id,  # Solo la especie elegida en el formulario.
            Variedad.activo == True,  # noqa: E712  Variedad activa.
            Especie.activo == True,  # noqa: E712  Especie activa.
        )  # Una especie inexistente o inactiva deja la lista vacía.
        .order_by(Variedad.nombre)  # Orden alfabético para el selector.
    )  # Finaliza la consulta.
    # Devuelve los objetos Variedad encontrados.
    return list(db.scalars(consulta).all())


# Calidades activas, ordenadas por nombre.
def calidades_activas(db: Session) -> list[Calidad]:
    # Mismo filtro que especies: solo registros activos.
    consulta = select(Calidad).where(Calidad.activo == True).order_by(Calidad.nombre)  # noqa: E712
    # Devuelve los objetos Calidad encontrados.
    return list(db.scalars(consulta).all())


# Sistemas productivos activos, ordenados por nombre.
def sistemas_productivos_activos(db: Session) -> list[SistemaProductivo]:
    # Mismo filtro que especies: solo registros activos.
    consulta = (
        select(SistemaProductivo)  # Devuelve sistemas productivos.
        .where(SistemaProductivo.activo == True)  # noqa: E712  Solo activos.
        .order_by(SistemaProductivo.nombre)  # Orden alfabético para el selector.
    )  # Finaliza la consulta.
    # Devuelve los objetos SistemaProductivo encontrados.
    return list(db.scalars(consulta).all())


# Productores activos cuyo RUT empieza con el texto o cuya razón social lo contiene.
def buscar_productores(db: Session, texto: str) -> list[Productor]:
    # Quita espacios al inicio y al final.
    texto = texto.strip()
    # Con menos de 2 caracteres no se consulta la base.
    if len(texto) < MINIMO_BUSQUEDA:
        return []

    # La razón social se busca siempre; autoescape evita que % o _ del operador funcionen como comodines.
    condicion = Productor.razon_social.contains(texto, autoescape=True)

    # Deja el texto como el RUT guardado pero sin guion: "12.345.678-5" pasa a "123456785".
    rut_limpio = re.sub(r"[.\-\s]", "", texto).upper().lstrip("0")
    # Si parece un RUT (o el inicio de uno), también se busca por RUT.
    if rut_limpio and _PATRON_RUT.fullmatch(rut_limpio):
        # El RUT se guarda como "12345678-5"; sin su guion se compara por el inicio.
        rut_sin_guion = func.replace(Productor.rut, "-", "")
        # Encuentra el productor tanto por los primeros dígitos como por el RUT completo.
        condicion = or_(condicion, rut_sin_guion.startswith(rut_limpio))

    # Solo productores activos, por orden alfabético y con un máximo de resultados.
    consulta = (
        select(Productor)  # Devuelve productores.
        .where(Productor.activo == True, condicion)  # noqa: E712  Activos que coinciden.
        .order_by(Productor.razon_social)  # Orden alfabético para la lista.
        .limit(MAXIMO_RESULTADOS)  # SQL Server lo traduce a TOP 20.
    )  # Finaliza la consulta.
    # Devuelve los objetos Productor encontrados.
    return list(db.scalars(consulta).all())
