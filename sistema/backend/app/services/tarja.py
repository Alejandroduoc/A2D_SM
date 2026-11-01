"""Reglas de negocio de las tarjas de recepción (HU12, HU13 y HU14)."""

# Pesos exactos y redondeo bancario.
from decimal import ROUND_HALF_EVEN, Decimal

# Consultas agregadas y acceso directo a la secuencia de SQL Server.
from sqlalchemy import func, select, text
# Sesión compartida por la tarja, el movimiento y sus auditorías.
from sqlalchemy.orm import Session

# Catálogos y entidades que deben existir y estar activos al registrar.
from app.models.auditoria import AccionAuditoria
from app.models.calidad import Calidad
from app.models.movimiento_bandeja import MovimientoBandeja, TipoMovimientoBandeja
from app.models.productor import Productor
from app.models.sistema_productivo import SistemaProductivo
from app.models.tarja import EstadoTarja, Tarja
from app.models.tipo_bandeja import TipoBandeja
from app.models.usuario import Usuario
from app.models.variedad import Variedad
# Entrada ya validada por Pydantic.
from app.schemas.tarja import TarjaCreate
# Captura estados y prepara eventos dentro de la misma transacción.
from app.services.auditoria import instantanea, registrar_auditoria


# El router traduce este error a HTTP 400.
class CatalogoNoValidoError(Exception):
    """El productor o un catálogo elegido no existe o está inactivo."""


# El router traduce este error a HTTP 400.
class KilosNetosNoValidosError(Exception):
    """Los kilos netos calculados son cero o negativos (HU14 criterio 2)."""


# Calcula los kilos netos de una tarja (HU14 criterio 1).
def calcular_kilos_netos(kilos_brutos: Decimal, cantidad: int, tara: Decimal, pallet: Decimal) -> int:
    """Neto = brutos − bandejas × tara − pallet, redondeado a entero.

    El redondeo es bancario (ROUND_HALF_EVEN), igual que CInt en Form4.vb del
    legado: 2,5 queda en 2 y 3,5 sube a 4. Es una función pura: no valida que
    el resultado sea positivo; eso lo decide registrar_tarja.
    """
    # Todo en Decimal para no perder precisión con float.
    neto = kilos_brutos - cantidad * tara - pallet
    # Redondea a entero con el criterio del legado y lo entrega como int.
    return int(neto.quantize(Decimal("1"), rounding=ROUND_HALF_EVEN))


# Exige que una entidad exista y permanezca habilitada para recepción.
def _obtener_activo(db: Session, modelo: type, identidad: int, nombre: str):
    # get usa la clave primaria y evita consultas adicionales si ya está cargada.
    entidad = db.get(modelo, identidad)
    # La API no confía en que el frontend ofrezca solamente opciones activas.
    if entidad is None or not entidad.activo:
        raise CatalogoNoValidoError(f"{nombre} no existe o está inactivo")
    return entidad


# Registra tarja, entrada de bandejas y dos auditorías como una sola operación.
def registrar_tarja(db: Session, datos: TarjaCreate, usuario: Usuario) -> Tarja:
    try:
        # Valida nuevamente las referencias recibidas, incluida su vigencia.
        productor = _obtener_activo(db, Productor, datos.productor_id, "El productor")
        sistema = _obtener_activo(
            db,
            SistemaProductivo,
            datos.sistema_productivo_id,
            "El sistema productivo",
        )
        variedad = _obtener_activo(db, Variedad, datos.variedad_id, "La variedad")
        calidad = _obtener_activo(db, Calidad, datos.calidad_id, "La calidad")
        bandeja = _obtener_activo(
            db,
            TipoBandeja,
            datos.tipo_bandeja_id,
            "El tipo de bandeja",
        )
        # Las variables explicitan que todas las referencias fueron validadas.
        _ = productor, sistema, variedad, calidad

        # Copia la tara vigente para conservar el cálculo histórico de la tarja.
        tara = bandeja.peso_tara_kg
        kilos_netos = calcular_kilos_netos(
            datos.kilos_brutos,
            datos.cantidad_bandejas,
            tara,
            datos.peso_pallet_kg,
        )
        if kilos_netos <= 0:
            raise KilosNetosNoValidosError(
                "Los kilos netos deben ser mayores que cero; revise la balanza, "
                "las bandejas y el pallet"
            )

        # La secuencia entrega números únicos aun entre transacciones concurrentes.
        numero_tarja = db.scalar(text("SELECT NEXT VALUE FOR seq_numero_tarja"))
        nueva = Tarja(
            numero_tarja=numero_tarja,
            productor_id=datos.productor_id,
            usuario_id=usuario.id,
            sistema_productivo_id=datos.sistema_productivo_id,
            variedad_id=datos.variedad_id,
            calidad_id=datos.calidad_id,
            tipo_bandeja_id=datos.tipo_bandeja_id,
            cantidad_bandejas=datos.cantidad_bandejas,
            tara_kg=tara,
            peso_pallet_kg=datos.peso_pallet_kg,
            kilos_brutos=datos.kilos_brutos,
            kilos_netos=kilos_netos,
            porcentaje_calidad=datos.porcentaje_calidad,
            fecha_recepcion=datos.fecha_recepcion,
            estado=EstadoTarja.RECEPCIONADA,
        )
        db.add(nueva)
        # Materializa la identidad antes de vincular el movimiento.
        db.flush()

        movimiento = MovimientoBandeja(
            productor_id=datos.productor_id,
            tipo_bandeja_id=datos.tipo_bandeja_id,
            tarja_id=nueva.id,
            tipo=TipoMovimientoBandeja.ENTRADA,
            cantidad=datos.cantidad_bandejas,
        )
        db.add(movimiento)
        db.flush()

        # Los dos eventos comparten la transacción de las filas de negocio.
        registrar_auditoria(
            db,
            usuario.id,
            "tarjas",
            nueva.id,
            AccionAuditoria.INSERT,
            despues=instantanea(nueva),
        )
        registrar_auditoria(
            db,
            usuario.id,
            "movimientos_bandeja",
            movimiento.id,
            AccionAuditoria.INSERT,
            despues=instantanea(movimiento),
        )
        # Confirma tarja, movimiento y auditorías una sola vez.
        db.commit()
    except Exception:
        # Cualquier validación o fallo de escritura revierte la operación completa.
        db.rollback()
        raise

    db.refresh(nueva)
    return nueva


# Resume las tarjas que todavía no terminan su procesamiento.
def pendientes_productor(db: Session, productor_id: int) -> tuple[int, int]:
    consulta = select(
        func.count(Tarja.id),
        func.coalesce(func.sum(Tarja.kilos_netos), 0),
    ).where(
        Tarja.productor_id == productor_id,
        Tarja.estado.in_((EstadoTarja.RECEPCIONADA, EstadoTarja.PARCIAL)),
    )
    cantidad, kilos = db.execute(consulta).one()
    # En E4, las tarjas PARCIAL descontarán los kilos ya procesados.
    return int(cantidad), int(kilos)


# Obtiene una tarja por su identidad interna sin modificarla.
def obtener_tarja(db: Session, tarja_id: int) -> Tarja | None:
    return db.get(Tarja, tarja_id)
