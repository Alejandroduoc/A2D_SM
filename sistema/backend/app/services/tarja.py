"""Reglas de negocio de las tarjas de recepción (HU12, HU13 y HU14)."""

# Filtros por fecha de recepción y momento de cada impresión.
from datetime import date, datetime, timezone
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
from app.models.especie import Especie
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


# Tope de filas del listado: una búsqueda sin filtros no devuelve toda la tabla.
MAXIMO_TARJAS_LISTADO = 200


# El router traduce este error a HTTP 400.
class CatalogoNoValidoError(Exception):
    """El productor o un catálogo elegido no existe o está inactivo."""


# El router traduce este error a HTTP 400.
class KilosNetosNoValidosError(Exception):
    """Los kilos netos calculados son cero o negativos (HU14 criterio 2)."""


# El router traduce este error a HTTP 404.
class TarjaNoEncontradaError(Exception):
    """La tarja pedida no existe."""


# El router traduce este error a HTTP 409.
class TarjaAnuladaError(Exception):
    """Una tarja anulada no se imprime: no debe identificar fruta en la planta."""


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


# Consulta común del listado y del detalle: la tarja con los nombres de sus catálogos.
def _consulta_con_nombres():
    # Las etiquetas coinciden con los campos de los schemas de salida.
    return (
        select(
            Tarja,  # Todas las columnas de la tarja.
            Productor.codigo.label("productor_codigo"),  # Código del productor.
            Productor.rut.label("productor_rut"),  # RUT del productor.
            Productor.razon_social.label("productor_razon_social"),  # Nombre del productor.
            SistemaProductivo.nombre.label("sistema_productivo"),  # Nombre del sistema productivo.
            Especie.nombre.label("especie"),  # Nombre de la especie.
            Variedad.nombre.label("variedad"),  # Nombre de la variedad.
            Calidad.nombre.label("calidad"),  # Nombre de la calidad.
            TipoBandeja.nombre.label("tipo_bandeja"),  # Nombre del tipo de bandeja.
            Usuario.nombre_completo.label("registrada_por"),  # Solo el nombre: nunca credenciales.
        )  # Finaliza las columnas.
        .join(Productor, Tarja.productor_id == Productor.id)  # Toda tarja tiene productor.
        .join(SistemaProductivo, Tarja.sistema_productivo_id == SistemaProductivo.id)  # Y sistema productivo.
        .join(Variedad, Tarja.variedad_id == Variedad.id)  # Y variedad.
        .join(Especie, Variedad.especie_id == Especie.id)  # La especie se obtiene de la variedad.
        .join(Calidad, Tarja.calidad_id == Calidad.id)  # Y calidad.
        .join(TipoBandeja, Tarja.tipo_bandeja_id == TipoBandeja.id)  # Y tipo de bandeja.
        .join(Usuario, Tarja.usuario_id == Usuario.id)  # Y usuario que la registró.
    )  # Un catálogo desactivado se sigue mostrando: los joins no filtran por activo.


# Convierte una fila de la consulta en los datos que esperan los schemas.
def _datos_de_fila(fila) -> dict:
    # Separa la tarja de los nombres.
    datos = dict(fila._mapping)
    tarja = datos.pop("Tarja")
    # Une las columnas de la tarja con los nombres; el estado viaja como texto.
    return {**instantanea(tarja), **datos, "estado": tarja.estado.value}


# Calcula los kilos procesados y pendientes de una tarja (HU17 criterio 2).
def kilos_de_tarja(tarja: Tarja) -> tuple[Decimal, Decimal]:
    # Hasta E4 no existen procesos: en HU18 se sumarán los procesos no anulados de la tarja.
    procesados = Decimal("0")
    # Una tarja anulada o terminada ya no tiene kilos por procesar.
    if tarja.estado in (EstadoTarja.ANULADA, EstadoTarja.PROCESADA):
        return procesados, Decimal("0")
    # Los demás estados conservan la diferencia.
    return procesados, Decimal(tarja.kilos_netos) - procesados


# Lista las tarjas que cumplen todos los filtros recibidos (HU17 criterio 1).
def listar_tarjas(
    db: Session,  # Sesión de la petición.
    numero_tarja: int | None = None,  # Número exacto.
    productor_id: int | None = None,  # Productor elegido.
    desde: date | None = None,  # Primer día de recepción, incluido.
    hasta: date | None = None,  # Último día de recepción, incluido.
    estado: EstadoTarja | None = None,  # Estado de la tarja.
) -> list[dict]:
    # Parte de la consulta con los nombres de los catálogos.
    consulta = _consulta_con_nombres()
    # Cada filtro se agrega solo si llegó.
    if numero_tarja is not None:
        consulta = consulta.where(Tarja.numero_tarja == numero_tarja)
    if productor_id is not None:
        consulta = consulta.where(Tarja.productor_id == productor_id)
    if desde is not None:
        consulta = consulta.where(Tarja.fecha_recepcion >= desde)
    if hasta is not None:
        consulta = consulta.where(Tarja.fecha_recepcion <= hasta)
    if estado is not None:
        consulta = consulta.where(Tarja.estado == estado)
    # Las más recientes primero, con un máximo de filas.
    consulta = consulta.order_by(Tarja.numero_tarja.desc()).limit(MAXIMO_TARJAS_LISTADO)
    # Devuelve cada fila lista para el schema.
    return [_datos_de_fila(fila) for fila in db.execute(consulta).all()]


# Obtiene el detalle completo de una tarja sin modificarla (HU17 criterio 2).
def obtener_tarja(db: Session, tarja_id: int) -> dict | None:
    # Busca la tarja con los nombres de sus catálogos.
    fila = db.execute(_consulta_con_nombres().where(Tarja.id == tarja_id)).first()
    # Devuelve None si no existe; el router resuelve el 404.
    if fila is None:
        return None
    # Calcula los kilos a partir de la tarja.
    procesados, pendientes = kilos_de_tarja(fila.Tarja)
    # Agrega los kilos a los demás datos.
    return {**_datos_de_fila(fila), "kilos_procesados": procesados, "kilos_pendientes": pendientes}


# Registra una impresión o reimpresión de la tarja (HU16 criterio 3).
def registrar_impresion(db: Session, tarja_id: int, usuario: Usuario) -> dict:
    # Protege toda la escritura hasta el único commit.
    try:
        # Bloquea la fila: dos impresiones a la vez no pueden perder una en el contador.
        tarja = db.execute(
            select(Tarja)  # Relee la tarja completa.
            .where(Tarja.id == tarja_id)  # Solo la fila pedida.
            .with_hint(Tarja, "WITH (UPDLOCK, HOLDLOCK)", dialect_name="mssql")  # Bloqueo de actualización.
            .execution_options(populate_existing=True)  # Reemplaza los valores antiguos en memoria.
        ).scalars().first()  # Devuelve la tarja o None.
        # Una tarja inexistente responde 404.
        if tarja is None:
            raise TarjaNoEncontradaError("Tarja no encontrada")
        # Una tarja anulada no se imprime.
        if tarja.estado == EstadoTarja.ANULADA:
            raise TarjaAnuladaError("No se puede imprimir una tarja anulada")
        # Captura el estado antes de modificarlo.
        antes = instantanea(tarja)
        # Suma la impresión.
        tarja.veces_impresa += 1
        # Guarda el momento en UTC.
        tarja.impresa_en = datetime.now(timezone.utc)
        # Comprueba las restricciones antes de auditar.
        db.flush()
        # Audita en la misma transacción; el motivo distingue la primera impresión de las copias.
        registrar_auditoria(
            db,  # Comparte la sesión que contiene el cambio.
            usuario.id,  # Responsable autenticado.
            "tarjas",  # Tabla afectada.
            tarja.id,  # Registro afectado.
            AccionAuditoria.UPDATE,  # La tarja cambia su contador.
            antes=antes,  # Estado anterior.
            despues=instantanea(tarja),  # Estado posterior.
            motivo="Reimpresión" if tarja.veces_impresa > 1 else "Impresión",  # Queda registrada (criterio 3).
        )  # Finaliza el evento.
        # Confirma el contador y su auditoría.
        db.commit()
    # Cualquier error revierte la operación completa.
    except Exception:
        # No queda un contador sin auditoría.
        db.rollback()
        # Deja que el router decida la respuesta.
        raise
    # Devuelve la tarja actualizada, con los nombres que necesita la hoja.
    return obtener_tarja(db, tarja_id)
