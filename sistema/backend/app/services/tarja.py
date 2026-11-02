"""Reglas de negocio de las tarjas de recepción (HU12, HU13 y HU14)."""

# Pesos exactos y redondeo bancario.
from decimal import ROUND_HALF_EVEN, Decimal

# Consultas agregadas y acceso directo a la secuencia de SQL Server.
from sqlalchemy import func, select, text
# Sesión compartida por la tarja, el movimiento y sus auditorías.
from sqlalchemy.orm import Session

# Acción que se registra en la auditoría.
from app.models.auditoria import AccionAuditoria
# Catálogos y entidades que deben existir y estar activos al registrar.
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
        # El mensaje nombra el dato para que el operador sepa cuál corregir.
        raise CatalogoNoValidoError(f"{nombre} no existe o está inactivo")
    # Entrega la entidad para que el llamador pueda leer sus datos.
    return entidad


# Registra tarja, entrada de bandejas y dos auditorías como una sola operación.
def registrar_tarja(db: Session, datos: TarjaCreate, usuario: Usuario) -> Tarja:
    # Protege toda la escritura hasta el único commit.
    try:
        # Valida nuevamente las referencias recibidas, incluida su vigencia.
        _obtener_activo(db, Productor, datos.productor_id, "El productor")
        _obtener_activo(db, SistemaProductivo, datos.sistema_productivo_id, "El sistema productivo")
        _obtener_activo(db, Variedad, datos.variedad_id, "La variedad")
        _obtener_activo(db, Calidad, datos.calidad_id, "La calidad")
        # La bandeja se conserva porque de ella sale la tara.
        bandeja = _obtener_activo(db, TipoBandeja, datos.tipo_bandeja_id, "El tipo de bandeja")

        # Copia la tara vigente para conservar el cálculo histórico de la tarja.
        tara = bandeja.peso_tara_kg
        # Calcula los kilos netos con los datos validados.
        kilos_netos = calcular_kilos_netos(
            datos.kilos_brutos,  # Peso de balanza.
            datos.cantidad_bandejas,  # Cantidad de bandejas.
            tara,  # Tara copiada del catálogo.
            datos.peso_pallet_kg,  # Peso del pallet.
        )  # Finaliza el cálculo.
        # HU14 criterio 2: el neto no puede ser negativo ni cero.
        if kilos_netos <= 0:
            # Avisa antes de consumir un número de la secuencia.
            raise KilosNetosNoValidosError(
                "Los kilos netos deben ser mayores que cero; revise la balanza, "
                "las bandejas y el pallet"
            )  # Finaliza el error.

        # La secuencia entrega números únicos aun entre transacciones concurrentes.
        numero_tarja = db.scalar(text("SELECT NEXT VALUE FOR seq_numero_tarja"))
        # Prepara la tarja con los datos del operador y los que pone el sistema.
        nueva = Tarja(
            numero_tarja=numero_tarja,  # Número asignado por la secuencia.
            productor_id=datos.productor_id,  # Productor elegido.
            usuario_id=usuario.id,  # Usuario autenticado, nunca del JSON.
            sistema_productivo_id=datos.sistema_productivo_id,  # Sistema productivo elegido.
            variedad_id=datos.variedad_id,  # Variedad elegida.
            calidad_id=datos.calidad_id,  # Calidad elegida.
            tipo_bandeja_id=datos.tipo_bandeja_id,  # Tipo de bandeja elegido.
            cantidad_bandejas=datos.cantidad_bandejas,  # Cantidad de bandejas.
            tara_kg=tara,  # Copia de la tara (HU14 criterio 4).
            peso_pallet_kg=datos.peso_pallet_kg,  # Peso del pallet.
            kilos_brutos=datos.kilos_brutos,  # Peso de balanza.
            kilos_netos=kilos_netos,  # Resultado del cálculo.
            porcentaje_calidad=datos.porcentaje_calidad,  # Calidad visual (decisión B).
            fecha_recepcion=datos.fecha_recepcion,  # Día de llegada (decisión C).
            estado=EstadoTarja.RECEPCIONADA,  # Toda tarja nueva parte recepcionada.
        )  # Finaliza la tarja.
        # Agrega la tarja a la transacción.
        db.add(nueva)
        # Materializa la identidad antes de vincular el movimiento.
        db.flush()

        # Prepara la entrada de bandejas que genera la tarja.
        movimiento = MovimientoBandeja(
            productor_id=datos.productor_id,  # Productor cuyo saldo aumenta.
            tipo_bandeja_id=datos.tipo_bandeja_id,  # Tipo de bandeja recibido.
            tarja_id=nueva.id,  # Tarja de origen.
            tipo=TipoMovimientoBandeja.ENTRADA,  # En el PMV solo hay entradas.
            cantidad=datos.cantidad_bandejas,  # Misma cantidad de la tarja.
        )  # Finaliza el movimiento.
        # Agrega el movimiento a la misma transacción.
        db.add(movimiento)
        # Materializa su identidad antes de auditarlo.
        db.flush()

        # Audita la tarja dentro de la transacción de las filas de negocio.
        registrar_auditoria(
            db,  # Comparte la sesión que contiene la tarja.
            usuario.id,  # Responsable autenticado.
            "tarjas",  # Tabla afectada.
            nueva.id,  # Registro afectado.
            AccionAuditoria.INSERT,  # Alta de la tarja.
            despues=instantanea(nueva),  # Estado completo registrado.
        )  # Finaliza el evento de la tarja.
        # Audita el movimiento en la misma transacción.
        registrar_auditoria(
            db,  # Comparte la sesión que contiene el movimiento.
            usuario.id,  # Responsable autenticado.
            "movimientos_bandeja",  # Tabla afectada.
            movimiento.id,  # Registro afectado.
            AccionAuditoria.INSERT,  # Alta del movimiento.
            despues=instantanea(movimiento),  # Estado completo registrado.
        )  # Finaliza el evento del movimiento.
        # Confirma tarja, movimiento y auditorías una sola vez.
        db.commit()
    # Cualquier validación o fallo de escritura termina aquí.
    except Exception:
        # Revierte la operación completa: no queda nada a medias (HU12 criterio 2).
        db.rollback()
        # Deja que el router decida la respuesta.
        raise

    # Recarga después del commit los valores confirmados.
    db.refresh(nueva)
    # Entrega la tarja al router.
    return nueva


# Resume las tarjas que todavía no terminan su procesamiento.
def pendientes_productor(db: Session, productor_id: int) -> tuple[int, int]:
    # Cuenta las tarjas y suma sus kilos netos; sin tarjas, la suma es 0 y no NULL.
    consulta = select(
        func.count(Tarja.id),  # Cantidad de tarjas.
        func.coalesce(func.sum(Tarja.kilos_netos), 0),  # Suma de kilos netos.
    ).where(
        Tarja.productor_id == productor_id,  # Solo el productor elegido.
        Tarja.estado.in_((EstadoTarja.RECEPCIONADA, EstadoTarja.PARCIAL)),  # Sin terminar ni anular.
    )  # Finaliza la consulta.
    # Una consulta agregada siempre devuelve una fila.
    cantidad, kilos = db.execute(consulta).one()
    # En E4, las tarjas PARCIAL descontarán los kilos ya procesados.
    return int(cantidad), int(kilos)


# Obtiene una tarja por su identidad interna sin modificarla.
def obtener_tarja(db: Session, tarja_id: int) -> Tarja | None:
    # Devuelve None si no existe; el router resuelve el 404.
    return db.get(Tarja, tarja_id)
