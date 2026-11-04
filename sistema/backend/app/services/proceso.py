"""Reglas de negocio del procesamiento de tarjas (HU18)."""

# Revisa el formato de los folios que escribe el operador.
import re
# Pesos exactos, sin float, y redondeo bancario.
from decimal import ROUND_HALF_EVEN, Decimal

# Consultas de lectura y acceso directo a la secuencia de SQL Server.
from sqlalchemy import func, select, text
# Sesión compartida por el proceso, sus filas, las tarjas y la auditoría.
from sqlalchemy.orm import Session

# Acción que se registra en la auditoría.
from app.models.auditoria import AccionAuditoria
# Calidad y sistema productivo: se muestran al comparar la fruta del proceso.
from app.models.calidad import Calidad
# Embalaje del proceso.
from app.models.embalaje import Embalaje
# Cabecera, detalle y catálogos que se leen.
from app.models.especie import Especie
from app.models.proceso import Proceso, ProcesoTarja
from app.models.productor import Productor
from app.models.sistema_productivo import SistemaProductivo
from app.models.tarja import EstadoTarja, Tarja
from app.models.usuario import Usuario
from app.models.variedad import Variedad
# Entrada ya validada por Pydantic.
from app.schemas.proceso import ProcesoCreate, ProcesoEdicion, ProcesoTarjaCreate
# Captura estados y prepara eventos dentro de la misma transacción.
from app.services.auditoria import instantanea, registrar_auditoria
# Reglas de tarjas que se reutilizan.
from app.services.tarja import (
    CatalogoNoValidoError,  # El embalaje no existe o está inactivo.
    TarjaNoEncontradaError,  # La tarja no existe.
    consulta_con_nombres,  # Tarja con los nombres de sus catálogos.
    datos_de_fila,  # Convierte esa consulta en un diccionario.
    kilos_procesados_de_tarja,  # Suma de sus procesos no anulados.
)  # Finaliza las importaciones.


# Tope de filas de los listados: una consulta no devuelve toda la tabla.
MAXIMO_FILAS_LISTADO = 200
# Mayor valor de una columna DECIMAL(10,2): las cajas y los kilos usan ese tipo.
MAX_DECIMAL_COLUMNA = Decimal("99999999.99")
# Precisión de los kilos.
CENTESIMO = Decimal("0.01")
# Tope de folios de una consulta: SQL Server limita los parámetros de una sentencia.
MAXIMO_FOLIOS_CONSULTA = 200
# Folio con o sin la letra P; un INT tiene hasta diez dígitos.
_PATRON_FOLIO = re.compile(r"P?(\d{1,10})")


# El router traduce este error a HTTP 422.
class FoliosNoValidosError(Exception):
    """Un folio no tiene el formato P más número, o se pidieron demasiados."""


# El router traduce este error a HTTP 404.
class ProcesoNoEncontradoError(Exception):
    """El proceso pedido no existe."""


# El router traduce este error a HTTP 409.
class ProcesoNoEditableError(Exception):
    """Un proceso anulado no se edita."""


# El router traduce este error a HTTP 409.
class TarjaNoProcesableError(Exception):
    """La tarja está anulada o terminada, o no admite la operación pedida."""


# El router traduce este error a HTTP 409.
class SaldoInsuficienteError(Exception):
    """Los kilos del proceso superan los que le quedan a la tarja (HU18 criterio 4)."""


# El router traduce este error a HTTP 400.
class MezclaNoPermitidaError(Exception):
    """Las tarjas difieren en sistema productivo, especie o calidad."""


# El router traduce este error a HTTP 400.
class KilosProcesoNoValidosError(Exception):
    """Faltan los kilos a granel, sobran en un embalaje fijo o se excede la capacidad."""


# Relee una tarja y la bloquea hasta el commit.
def _bloquear_tarja(db: Session, tarja_id: int) -> Tarja | None:
    # Todo el que consuma kilos de la tarja espera aquí: dos procesos no pueden gastar el mismo saldo.
    return db.execute(
        select(Tarja)  # Relee la tarja completa.
        .where(Tarja.id == tarja_id)  # Solo la fila pedida.
        .with_hint(Tarja, "WITH (UPDLOCK, HOLDLOCK)", dialect_name="mssql")  # Bloqueo de actualización.
        .execution_options(populate_existing=True)  # Reemplaza los valores antiguos en memoria.
    ).scalars().first()  # Devuelve la tarja o None.


# Calcula el estado de la tarja con su merma y sus procesos no anulados.
def recalcular_estado(db: Session, tarja: Tarja) -> None:
    """Rebajada, con marca o sin saldo queda PROCESADA; sin procesos, RECEPCIONADA; si no, PARCIAL.

    La marca y la rebaja son decisiones del operador; el saldo 0 se deduce de los kilos.
    Por eso no se guarda nada cuando el saldo llega a 0: si después se anula otro proceso
    (HU25), los kilos vuelven y la tarja se abre sola, sin una merma que nadie decidió.
    """
    # Lee las filas vigentes de la tarja.
    filas = db.execute(
        select(ProcesoTarja.kilos_procesados, ProcesoTarja.tarja_terminada)  # Kilos y marca.
        .join(Proceso, ProcesoTarja.proceso_id == Proceso.id)  # Une con la cabecera.
        .where(
            ProcesoTarja.tarja_id == tarja.id,  # Solo esta tarja.
            Proceso.anulado == False,  # noqa: E712  Un proceso anulado deja de contar.
        )  # Finaliza los filtros.
    ).all()  # Devuelve todas las filas.
    # El saldo rebajado como merma cierra la tarja, tenga o no procesos.
    if tarja.merma_rebajada:
        tarja.estado = EstadoTarja.PROCESADA
        return
    # Sin procesos vigentes.
    if not filas:
        tarja.estado = EstadoTarja.RECEPCIONADA
        return
    # Suma lo que ya salió de la tarja.
    procesados = sum((fila.kilos_procesados for fila in filas), Decimal("0"))
    # Terminada por decisión del operador o porque ya no le quedan kilos.
    if any(fila.tarja_terminada for fila in filas) or procesados >= Decimal(tarja.kilos_netos):
        tarja.estado = EstadoTarja.PROCESADA
        return
    # Le quedan kilos y sigue disponible.
    tarja.estado = EstadoTarja.PARCIAL


# Consulta común de tarjas con la suma de sus kilos en procesos no anulados.
def _consulta_tarjas_con_kilos():
    # Suma por tarja de lo procesado en procesos no anulados.
    procesados = (
        select(
            ProcesoTarja.tarja_id,  # Tarja de la suma.
            func.sum(ProcesoTarja.kilos_procesados).label("kilos"),  # Suma de sus kilos.
        )  # Finaliza las columnas.
        .join(Proceso, ProcesoTarja.proceso_id == Proceso.id)  # Une con la cabecera.
        .where(Proceso.anulado == False)  # noqa: E712  Un proceso anulado deja de contar.
        .group_by(ProcesoTarja.tarja_id)  # Una fila por tarja.
        .subquery()  # Se une como una tabla más.
    )  # Finaliza la subconsulta.
    # Agrega los kilos a la consulta común de tarjas.
    return (
        consulta_con_nombres()  # Tarja con los nombres de sus catálogos.
        .add_columns(func.coalesce(procesados.c.kilos, 0).label("kilos_procesados"))  # Sin procesos, 0.
        .outerjoin(procesados, Tarja.id == procesados.c.tarja_id)  # Conserva las que no tienen procesos.
    )  # Finaliza la consulta.


# Convierte las filas de esa consulta en los datos que espera el schema.
def _tarjas_con_kilos(db: Session, consulta) -> list[dict]:
    # Prepara el resultado.
    salida = []
    # Convierte cada fila.
    for fila in db.execute(consulta).all():
        # Une los datos de la tarja con sus nombres y sus kilos.
        datos = datos_de_fila(fila)
        # Deja los kilos con dos decimales.
        kilos = Decimal(datos["kilos_procesados"]).quantize(CENTESIMO)
        # Agrega los kilos procesados y la diferencia con los netos.
        salida.append({**datos, "kilos_procesados": kilos, "kilos_pendientes": Decimal(datos["kilos_netos"]) - kilos})
    # Entrega la lista lista para el schema.
    return salida


# Lista las tarjas que todavía se pueden procesar, las más antiguas primero.
def listar_tarjas_disponibles(db: Session, numero_tarja: int | None = None) -> list[dict]:
    # Criterio 3: solo recepcionadas o parciales.
    consulta = _consulta_tarjas_con_kilos().where(Tarja.estado.in_((EstadoTarja.RECEPCIONADA, EstadoTarja.PARCIAL)))
    # El número se usa al escribirlo en el formulario, como en el Form30 del legado.
    if numero_tarja is not None:
        consulta = consulta.where(Tarja.numero_tarja == numero_tarja)
    # La fruta más antigua se procesa primero, con un máximo de filas.
    return _tarjas_con_kilos(db, consulta.order_by(Tarja.numero_tarja).limit(MAXIMO_FILAS_LISTADO))


# Lista las tarjas con merma rebajada, para poder reabrirlas; las más recientes primero.
def listar_tarjas_rebajadas(db: Session) -> list[dict]:
    # Solo las que tienen la decisión vigente.
    consulta = _consulta_tarjas_con_kilos().where(Tarja.merma_rebajada == True)  # noqa: E712
    # En estas tarjas, la diferencia con los netos es su merma.
    return _tarjas_con_kilos(db, consulta.order_by(Tarja.numero_tarja.desc()).limit(MAXIMO_FILAS_LISTADO))


# Deja los folios como se guardan, sin repetidos y en el orden escrito.
def _normalizar_folios(folios: list[str]) -> list[str]:
    # Prepara el resultado.
    salida = []
    # Revisa cada folio.
    for folio in folios:
        # Acepta p12, P12 o 12, como lo escriba el operador.
        coincide = _PATRON_FOLIO.fullmatch(folio.strip().upper())
        # Un texto que no es un folio se avisa, no se ignora.
        if coincide is None:
            raise FoliosNoValidosError(f"\"{folio.strip()[:20]}\" no es un folio válido")
        # Sin ceros a la izquierda, como lo guarda el sistema.
        normalizado = f"P{int(coincide.group(1))}"
        # Un folio repetido se considera una sola vez.
        if normalizado not in salida:
            salida.append(normalizado)
    # Un listado absurdo se rechaza antes de llegar a la base.
    if len(salida) > MAXIMO_FOLIOS_CONSULTA:
        raise FoliosNoValidosError(f"Se pueden consultar hasta {MAXIMO_FOLIOS_CONSULTA} folios a la vez")
    # Entrega los folios listos para buscar.
    return salida


# Calcula el porcentaje con dos decimales y el redondeo del Form42 del legado.
def _rendimiento(procesados: Decimal, entrada: Decimal) -> Decimal:
    # Multiplica primero para no perder precisión.
    return (procesados * 100 / entrada).quantize(CENTESIMO, rounding=ROUND_HALF_EVEN)


# Calcula rendimiento y merma de las tarjas asociadas a los folios (HU19); no escribe nada.
def calcular_rendimiento(db: Session, folios: list[str]) -> dict:
    """No se guarda: se calcula al consultar, para que siempre coincida con los procesos vigentes."""
    # Deja los folios como se guardan.
    buscados = _normalizar_folios(folios)
    # Busca los procesos de esos folios.
    procesos = db.execute(select(Proceso.id, Proceso.folio, Proceso.anulado).where(Proceso.folio.in_(buscados))).all()
    # Folios que existen.
    existentes = {proceso.folio for proceso in procesos}
    # Un proceso anulado no cuenta, pero se avisa para que el operador sepa por qué falta.
    anulados = {proceso.folio for proceso in procesos if proceso.anulado}
    # Procesos que sí cuentan.
    vigentes = [proceso.id for proceso in procesos if not proceso.anulado]
    # Tarjas de recepción asociadas (criterio 1).
    asociadas = select(ProcesoTarja.tarja_id).where(ProcesoTarja.proceso_id.in_(vigentes))
    # Kilos procesados en TODOS sus procesos no anulados: el legado tomaba solo el primero.
    filas = _tarjas_con_kilos(db, _consulta_tarjas_con_kilos().where(Tarja.id.in_(asociadas)).order_by(Tarja.numero_tarja))
    # Folios vigentes de cada tarja, para mostrarlos.
    folios_por_tarja = {}
    # Lee los folios en orden de registro.
    for tarja_id, folio in db.execute(
        select(ProcesoTarja.tarja_id, Proceso.folio)  # Tarja y folio.
        .join(Proceso, ProcesoTarja.proceso_id == Proceso.id)  # Une con la cabecera.
        .where(
            ProcesoTarja.tarja_id.in_([fila["id"] for fila in filas]),  # Solo las tarjas del resultado.
            Proceso.anulado == False,  # noqa: E712  Un proceso anulado deja de contar.
        )  # Finaliza los filtros.
        .order_by(Proceso.id)  # Orden de registro.
    ).all():
        # Agrupa por tarja.
        folios_por_tarja.setdefault(tarja_id, []).append(folio)
    # Prepara una fila por tarja.
    tarjas = []
    # Calcula cada tarja (criterio 2).
    for fila in filas:
        # Kilos de entrada: los netos de la recepción.
        entrada = Decimal(fila["kilos_netos"])
        # Kilos procesados vigentes.
        procesados = fila["kilos_procesados"]
        # Agrega la fila.
        tarjas.append({
            **fila,  # Datos y nombres de la tarja.
            "tarja_id": fila["id"],  # Identificador.
            "folios": folios_por_tarja.get(fila["id"], []),  # Sus procesos vigentes.
            "kilos_entrada": entrada.quantize(CENTESIMO),  # Con dos decimales.
            "merma": entrada - procesados,  # Lo que no salió en cajas.
            "rendimiento": _rendimiento(procesados, entrada),  # Porcentaje.
            "provisional": fila["estado"] != EstadoTarja.PROCESADA.value,  # Definitivo solo si terminó (criterio 4).
        })  # Finaliza la fila.
    # Suma de las tarjas (criterio 3).
    total_entrada = sum((tarja["kilos_entrada"] for tarja in tarjas), Decimal("0.00"))
    total_procesados = sum((tarja["kilos_procesados"] for tarja in tarjas), Decimal("0.00"))
    # Entrega el resultado.
    return {
        "tarjas": tarjas,  # Una fila por tarja.
        "total": {
            "kilos_entrada": total_entrada,  # Suma de la entrada.
            "kilos_procesados": total_procesados,  # Suma de lo procesado.
            "merma": total_entrada - total_procesados,  # Suma de las mermas.
            "rendimiento": _rendimiento(total_procesados, total_entrada) if tarjas else None,  # No divide por cero.
            "provisional": any(tarja["provisional"] for tarja in tarjas),  # Basta una abierta.
        },  # Finaliza el total.
        "folios_no_encontrados": [folio for folio in buscados if folio not in existentes],  # No existen.
        "folios_anulados": [folio for folio in buscados if folio in anulados],  # No cuentan.
    }  # Finaliza la respuesta.


# Lista los embalajes activos para el formulario.
def embalajes_activos(db: Session) -> list[Embalaje]:
    # Un embalaje desactivado no se ofrece, en orden alfabético.
    consulta = select(Embalaje).where(Embalaje.activo == True).order_by(Embalaje.nombre)  # noqa: E712
    # Devuelve los objetos Embalaje.
    return list(db.scalars(consulta).all())


# Calcula los kilos de una fila del proceso (HU18 criterio 2).
def _kilos_de_fila(embalaje: Embalaje, fila: ProcesoTarjaCreate, numero_tarja: int) -> Decimal:
    # A granel no hay peso fijo: los kilos se ingresan a mano.
    if embalaje.es_granel:
        # Sin kilos no se puede calcular nada.
        if fila.kilos_procesados is None:
            raise KilosProcesoNoValidosError(f"A granel se deben ingresar los kilos de la tarja N° {numero_tarja}")
        # Conserva lo ingresado.
        return fila.kilos_procesados
    # Con embalaje fijo no se aceptan kilos del cliente: se calculan siempre aquí.
    if fila.kilos_procesados is not None:
        raise KilosProcesoNoValidosError("Con un embalaje de peso fijo los kilos los calcula el sistema")
    # Cajas por kilos de cada caja, con el mismo redondeo de los kilos netos.
    return (fila.cantidad_cajas * embalaje.kg_por_caja).quantize(CENTESIMO, rounding=ROUND_HALF_EVEN)


# Revisa que los kilos de la fila quepan en lo que le queda a la tarja (HU18 criterio 4).
def _kilos_dentro_del_saldo(embalaje: Embalaje, kilos: Decimal, pendientes: Decimal, numero_tarja: int) -> Decimal:
    # Lo normal: caben.
    if kilos <= pendientes:
        return kilos
    # Las cajas tienen dos decimales: 1,20 kg con cajas de 11,35 kg son 0,11 cajas, que calculan 1,25 kg.
    # Una diferencia menor que un centésimo de caja es redondeo y se usa el saldo exacto para llegar a 0.
    if not embalaje.es_granel and kilos - pendientes < embalaje.kg_por_caja * CENTESIMO:
        return pendientes
    # Criterio 4: la suma nunca supera los kilos netos.
    raise SaldoInsuficienteError(f"La tarja N° {numero_tarja} tiene {pendientes} kg pendientes y el proceso pide {kilos} kg")


# Exige que todas las tarjas compartan sistema productivo, especie y calidad; la variedad puede variar.
def _exigir_misma_fruta(db: Session, tarjas: list[Tarja]) -> None:
    # La primera tarja es la referencia.
    primera = tarjas[0]
    # La especie se obtiene de la variedad.
    especie = db.get(Variedad, primera.variedad_id).especie_id
    # Compara cada una de las demás.
    for tarja in tarjas[1:]:
        # Mismo sistema productivo.
        if tarja.sistema_productivo_id != primera.sistema_productivo_id:
            raise MezclaNoPermitidaError(f"La tarja N° {tarja.numero_tarja} tiene otro sistema productivo: no se puede mezclar en el mismo proceso")
        # Misma especie.
        if db.get(Variedad, tarja.variedad_id).especie_id != especie:
            raise MezclaNoPermitidaError(f"La tarja N° {tarja.numero_tarja} es de otra especie: no se puede mezclar en el mismo proceso")
        # Misma calidad.
        if tarja.calidad_id != primera.calidad_id:
            raise MezclaNoPermitidaError(f"La tarja N° {tarja.numero_tarja} tiene otra calidad: no se puede mezclar en el mismo proceso")


# Bloquea las tarjas pedidas y revisa que se puedan procesar.
def _bloquear_y_revisar(db: Session, filas: list[ProcesoTarjaCreate]) -> list[tuple[ProcesoTarjaCreate, Tarja]]:
    # Bloquea en orden de id: dos procesos con las mismas tarjas no se traban entre sí.
    bloqueadas = {tarja_id: _bloquear_tarja(db, tarja_id) for tarja_id in sorted(fila.tarja_id for fila in filas)}
    # Reúne cada fila con su tarja, en el orden del operador.
    pares = []
    # Revisa cada tarja.
    for fila in filas:
        # Busca la tarja ya bloqueada.
        tarja = bloqueadas[fila.tarja_id]
        # Una tarja inexistente responde 404.
        if tarja is None:
            raise TarjaNoEncontradaError("Tarja no encontrada")
        # Criterio 3: solo recepcionadas o parciales.
        if tarja.estado == EstadoTarja.ANULADA:
            raise TarjaNoProcesableError(f"La tarja N° {tarja.numero_tarja} está anulada")
        # Una tarja terminada ya no está disponible (criterio 5).
        if tarja.estado == EstadoTarja.PROCESADA:
            raise TarjaNoProcesableError(f"La tarja N° {tarja.numero_tarja} ya está terminada")
        # Guarda el par para los pasos siguientes.
        pares.append((fila, tarja))
    # Entrega las filas con sus tarjas.
    return pares


# Calcula los kilos de cada fila y comprueba el saldo de su tarja.
def _calcular_filas(db: Session, embalaje: Embalaje, pares: list) -> list[tuple[ProcesoTarjaCreate, Tarja, Decimal]]:
    # Prepara el resultado.
    calculadas = []
    # Calcula y comprueba cada fila.
    for fila, tarja in pares:
        # Kilos de la fila según el embalaje.
        kilos = _kilos_de_fila(embalaje, fila, tarja.numero_tarja)
        # Lo que le queda a la tarja, leído con la tarja bloqueada.
        pendientes = Decimal(tarja.kilos_netos) - kilos_procesados_de_tarja(db, tarja.id)
        # Los kilos nunca superan el saldo.
        calculadas.append((fila, tarja, _kilos_dentro_del_saldo(embalaje, kilos, pendientes, tarja.numero_tarja)))
    # Entrega las filas calculadas.
    return calculadas


# No hay máximo operativo, pero las columnas tienen capacidad: mejor un 400 que un error interno.
def _exigir_capacidad(cajas: Decimal, kilos: Decimal) -> None:
    # Ambos totales son DECIMAL(10,2).
    if cajas > MAX_DECIMAL_COLUMNA or kilos > MAX_DECIMAL_COLUMNA:
        raise KilosProcesoNoValidosError("Los totales del proceso superan la capacidad del sistema: divídalo en dos procesos")


# Audita las tarjas que cambiaron de estado o perdieron su merma rebajada.
def _auditar_tarjas(db: Session, usuario: Usuario, estados_antes: list[tuple[Tarja, dict]], motivo: str | None = None) -> None:
    # Recorre cada tarja con su estado anterior.
    for tarja, antes in estados_antes:
        # Una tarja que sigue igual no tiene nada que auditar.
        if antes["estado"] != tarja.estado or antes["merma_rebajada"] != tarja.merma_rebajada:
            registrar_auditoria(
                db,  # Comparte la sesión.
                usuario.id,  # Responsable autenticado.
                "tarjas",  # Tabla afectada.
                tarja.id,  # Registro afectado.
                AccionAuditoria.UPDATE,  # Cambia su estado.
                antes=antes,  # Estado anterior.
                despues=instantanea(tarja),  # Estado posterior.
                motivo=motivo,  # Lo indica la operación.
            )  # Finaliza el evento.


# Registra el proceso, sus filas, el estado de las tarjas y la auditoría en una transacción.
def registrar_proceso(db: Session, datos: ProcesoCreate, usuario: Usuario) -> dict:
    # Protege toda la escritura hasta el único commit.
    try:
        # La API no confía en que el frontend ofrezca solo embalajes activos.
        embalaje = db.get(Embalaje, datos.embalaje_id)
        # Un embalaje inexistente o desactivado se rechaza.
        if embalaje is None or not embalaje.activo:
            raise CatalogoNoValidoError("El embalaje no existe o está inactivo")

        # Bloquea y revisa las tarjas.
        pares = _bloquear_y_revisar(db, datos.tarjas)
        # La fruta del proceso debe ser homogénea, como en socradex y en el Form30 del legado.
        _exigir_misma_fruta(db, [tarja for _, tarja in pares])
        # Calcula los kilos sin superar el saldo de ninguna.
        calculadas = _calcular_filas(db, embalaje, pares)
        # Totales de la cabecera.
        total_cajas = sum((fila.cantidad_cajas for fila, _, _ in calculadas), Decimal("0"))
        total_kilos = sum((kilos for _, _, kilos in calculadas), Decimal("0"))
        # Comprueba que quepan en sus columnas.
        _exigir_capacidad(total_cajas, total_kilos)

        # La secuencia va después de validar, para no gastar números en rechazos.
        numero = db.scalar(text("SELECT NEXT VALUE FOR seq_numero_proceso"))
        # Prepara la cabecera con lo que pone el sistema.
        proceso = Proceso(
            folio=f"P{numero}",  # Folio único aunque dos operadores guarden a la vez (criterio 1).
            usuario_id=usuario.id,  # Usuario autenticado, nunca del JSON.
            embalaje_id=embalaje.id,  # Embalaje elegido.
            fecha_elaboracion=datos.fecha_elaboracion,  # Día de elaboración.
            cantidad_cajas=total_cajas,  # Suma de las filas.
            kilos_salida=total_kilos,  # Suma de las filas.
        )  # Finaliza la cabecera.
        # Agrega la cabecera a la transacción.
        db.add(proceso)
        # Materializa su identidad antes de crear las filas.
        db.flush()

        # Prepara las filas del detalle y lo que se audita de cada tarja.
        filas_nuevas = []
        estados_antes = []
        # Crea una fila por tarja.
        for fila, tarja, kilos in calculadas:
            # Captura la tarja antes de cambiar su estado.
            estados_antes.append((tarja, instantanea(tarja)))
            # Prepara la fila del detalle.
            nueva = ProcesoTarja(
                proceso_id=proceso.id,  # Cabecera recién creada.
                tarja_id=tarja.id,  # Tarja consumida.
                cantidad_cajas=fila.cantidad_cajas,  # Cajas de esta tarja.
                kilos_procesados=kilos,  # Calculados o a granel.
                tarja_terminada=fila.tarja_terminada,  # Decisión del operador.
            )  # Finaliza la fila.
            # Agrega la fila a la transacción.
            db.add(nueva)
            # Guarda la fila para auditarla.
            filas_nuevas.append(nueva)
        # Las filas deben estar en la base para recalcular el estado.
        db.flush()

        # Criterio 6: cada tarja cambia de estado en la misma transacción.
        for tarja, _ in estados_antes:
            recalcular_estado(db, tarja)
        # Comprueba las restricciones antes de auditar.
        db.flush()

        # Audita la cabecera.
        registrar_auditoria(
            db,  # Comparte la sesión.
            usuario.id,  # Responsable autenticado.
            "procesos",  # Tabla afectada.
            proceso.id,  # Registro afectado.
            AccionAuditoria.INSERT,  # Alta del proceso.
            despues=instantanea(proceso),  # Estado registrado.
        )  # Finaliza el evento.
        # Audita cada fila del detalle.
        for nueva in filas_nuevas:
            registrar_auditoria(
                db,  # Comparte la sesión.
                usuario.id,  # Responsable autenticado.
                "proceso_tarjas",  # Tabla afectada.
                f"{nueva.proceso_id}:{nueva.tarja_id}",  # La clave de esta tabla es compuesta.
                AccionAuditoria.INSERT,  # Alta de la fila.
                despues=instantanea(nueva),  # Estado registrado.
            )  # Finaliza el evento.
        # Audita solo las tarjas que cambiaron de estado.
        _auditar_tarjas(db, usuario, estados_antes)
        # Confirma todo una sola vez.
        db.commit()
    # Cualquier error revierte la operación completa.
    except Exception:
        # No queda un proceso a medias.
        db.rollback()
        # Deja que el router decida la respuesta.
        raise
    # Devuelve el proceso con sus nombres.
    return obtener_proceso(db, proceso.id)


# Quita el cierre decidido de una tarja que recupera kilos, porque se decidió con otros kilos.
def _quitar_cierre_decidido(db: Session, tarja: Tarja, proceso_id: int) -> list[tuple[ProcesoTarja, dict, AccionAuditoria]]:
    # Quita la merma rebajada.
    tarja.merma_rebajada = False
    # Busca sus marcas vigentes, también en otros procesos.
    marcadas = db.scalars(
        select(ProcesoTarja)  # La fila del detalle.
        .join(Proceso, ProcesoTarja.proceso_id == Proceso.id)  # Une con la cabecera.
        .where(
            ProcesoTarja.tarja_id == tarja.id,  # Solo esta tarja.
            ProcesoTarja.tarja_terminada == True,  # noqa: E712  Solo las marcadas.
            Proceso.anulado == False,  # noqa: E712  Solo procesos vigentes.
        )  # Finaliza los filtros.
    ).all()  # Devuelve todas.
    # Eventos de las filas que cambian.
    eventos = []
    # Revisa cada marca.
    for marcada in marcadas:
        # La fila del proceso que se está corrigiendo ya trae lo que pidió el operador.
        if marcada.proceso_id == proceso_id:
            continue
        # Captura la fila antes de quitarle la marca.
        eventos.append((marcada, instantanea(marcada), AccionAuditoria.UPDATE))
        # Quita la marca.
        marcada.tarja_terminada = False
    # Entrega los eventos para auditarlos.
    return eventos


# Corrige un proceso ya registrado: sube o baja sus cajas, agrega tarjas o las quita.
def editar_proceso(db: Session, proceso_id: int, datos: ProcesoEdicion, usuario: Usuario) -> dict:
    """Decisión del 2026-11-03: un pallet con error se edita y sus kilos se ajustan.

    El cuerpo indica cómo debe quedar el proceso. Los kilos que salen vuelven solos a su
    tarja de recepción, porque el saldo siempre es kilos netos menos kilos procesados.
    Si una tarja recupera kilos, su cierre decidido (marca o merma rebajada) deja de valer:
    se tomó con otros kilos, y queda pendiente hasta llegar a 0 o rebajarse de nuevo.
    El folio, el embalaje y la fecha no cambian.
    """
    # Protege toda la escritura hasta el único commit.
    try:
        # Bloquea primero la cabecera: dos ediciones a la vez no pueden perder un total.
        proceso = db.execute(
            select(Proceso)  # Relee la cabecera completa.
            .where(Proceso.id == proceso_id)  # Solo el proceso pedido.
            .with_hint(Proceso, "WITH (UPDLOCK, HOLDLOCK)", dialect_name="mssql")  # Bloqueo de actualización.
            .execution_options(populate_existing=True)  # Reemplaza los valores antiguos en memoria.
        ).scalars().first()  # Devuelve el proceso o None.
        # Un proceso inexistente responde 404.
        if proceso is None:
            raise ProcesoNoEncontradoError("Proceso no encontrado")
        # Los kilos de un proceso anulado ya volvieron a sus tarjas.
        if proceso.anulado:
            raise ProcesoNoEditableError(f"El proceso {proceso.folio} está anulado")
        # El embalaje queda fijo; puede estar desactivado y la corrección se sigue pudiendo hacer.
        embalaje = db.get(Embalaje, proceso.embalaje_id)
        # Lee las filas que ya tiene el proceso.
        existentes = {fila.tarja_id: fila for fila in db.scalars(select(ProcesoTarja).where(ProcesoTarja.proceso_id == proceso.id))}
        # Tarjas pedidas.
        pedidas = {fila.tarja_id: fila for fila in datos.tarjas}
        # Bloquea en orden de id todas las tarjas involucradas, también las que se quitan.
        bloqueadas = {tarja_id: _bloquear_tarja(db, tarja_id) for tarja_id in sorted(set(existentes) | set(pedidas))}

        # Prepara el resultado de cada fila pedida.
        calculadas = []
        # Revisa cada fila en el orden del operador.
        for fila in datos.tarjas:
            # Busca la tarja ya bloqueada.
            tarja = bloqueadas[fila.tarja_id]
            # Una tarja inexistente responde 404.
            if tarja is None:
                raise TarjaNoEncontradaError("Tarja no encontrada")
            # Una tarja anulada no se procesa.
            if tarja.estado == EstadoTarja.ANULADA:
                raise TarjaNoProcesableError(f"La tarja N° {tarja.numero_tarja} está anulada")
            # Fila que ya tiene en este proceso, si la hay.
            actual = existentes.get(tarja.id)
            # Una tarja terminada no entra de nuevo; la que ya está en el proceso sí se puede ajustar.
            if actual is None and tarja.estado == EstadoTarja.PROCESADA:
                raise TarjaNoProcesableError(f"La tarja N° {tarja.numero_tarja} ya está terminada")
            # Kilos pedidos; con las mismas cajas se conservan, aunque el catálogo haya cambiado el peso.
            if actual is not None and not embalaje.es_granel and fila.kilos_procesados is None and fila.cantidad_cajas == actual.cantidad_cajas:
                kilos = actual.kilos_procesados
            # En los demás casos se calculan como al registrar.
            else:
                kilos = _kilos_de_fila(embalaje, fila, tarja.numero_tarja)
                # Lo máximo que esta fila puede tener: lo pendiente más lo que ya tiene.
                disponibles = Decimal(tarja.kilos_netos) - kilos_procesados_de_tarja(db, tarja.id) + (actual.kilos_procesados if actual else Decimal("0"))
                # Los kilos nunca superan el saldo.
                kilos = _kilos_dentro_del_saldo(embalaje, kilos, disponibles, tarja.numero_tarja)
            # Guarda la fila calculada.
            calculadas.append((fila, tarja, kilos))
        # La fruta debe seguir siendo homogénea: el legado olvidó esta regla al editar.
        _exigir_misma_fruta(db, [tarja for _, tarja, _ in calculadas])
        # Nuevos totales de la cabecera.
        total_cajas = sum((fila.cantidad_cajas for fila, _, _ in calculadas), Decimal("0"))
        total_kilos = sum((kilos for _, _, kilos in calculadas), Decimal("0"))
        # Comprueba que quepan en sus columnas.
        _exigir_capacidad(total_cajas, total_kilos)

        # Captura la cabecera y las tarjas antes de modificarlas.
        proceso_antes = instantanea(proceso)
        estados_antes = [(tarja, instantanea(tarja)) for tarja in bloqueadas.values()]
        # Eventos de las filas: (fila, estado anterior o None, acción).
        eventos = []
        # Tarjas que recuperan kilos.
        devueltas = set()
        # Aplica cada fila pedida.
        for fila, tarja, kilos in calculadas:
            # Busca si la tarja ya está en el proceso.
            actual = existentes.get(tarja.id)
            # Es una tarja nueva en este proceso.
            if actual is None:
                # Prepara la fila del detalle.
                actual = ProcesoTarja(
                    proceso_id=proceso.id,  # Este proceso.
                    tarja_id=tarja.id,  # Tarja que entrega la fruta.
                    cantidad_cajas=fila.cantidad_cajas,  # Cajas de la tarja.
                    kilos_procesados=kilos,  # Kilos de la tarja.
                    tarja_terminada=fila.tarja_terminada,  # Decisión del operador.
                )  # Finaliza la fila.
                # La agrega a la transacción.
                db.add(actual)
                # No tiene estado anterior.
                eventos.append((actual, None, AccionAuditoria.INSERT))
                # Sigue con la siguiente.
                continue
            # Sin cambios no se escribe ni se audita.
            if (actual.cantidad_cajas, actual.kilos_procesados, actual.tarja_terminada) == (fila.cantidad_cajas, kilos, fila.tarja_terminada):
                continue
            # Captura la fila antes de modificarla.
            eventos.append((actual, instantanea(actual), AccionAuditoria.UPDATE))
            # Bajar los kilos los devuelve a la tarja.
            if kilos < actual.kilos_procesados:
                devueltas.add(tarja.id)
            # Aplica las cajas.
            actual.cantidad_cajas = fila.cantidad_cajas
            # Aplica los kilos.
            actual.kilos_procesados = kilos
            # Aplica la marca.
            actual.tarja_terminada = fila.tarja_terminada
        # Quita las tarjas que ya no están en el proceso; la auditoría conserva la fila.
        for tarja_id, actual in existentes.items():
            # Sigue en el proceso.
            if tarja_id in pedidas:
                continue
            # Todos sus kilos vuelven a la tarja.
            devueltas.add(tarja_id)
            # Guarda el evento antes de borrarla.
            eventos.append((actual, instantanea(actual), AccionAuditoria.DELETE))
            # Una fila de detalle se puede quitar: la cabecera y su folio se conservan.
            db.delete(actual)
        # Sin ningún cambio, no hay nada que confirmar.
        if not eventos:
            db.rollback()
            return obtener_proceso(db, proceso_id)
        # Actualiza los totales.
        proceso.cantidad_cajas = total_cajas
        proceso.kilos_salida = total_kilos
        # Las filas deben estar en la base antes de seguir.
        db.flush()

        # Una tarja que recupera kilos deja de estar cerrada por decisión: se tomó con otros kilos.
        for tarja_id in sorted(devueltas):
            # Quita su merma rebajada y las marcas de otros procesos, y suma esos eventos.
            eventos.extend(_quitar_cierre_decidido(db, bloqueadas[tarja_id], proceso.id))
        # Lleva los cambios a la base antes de recalcular.
        db.flush()
        # Cada tarja queda con el estado que indican sus procesos, en la misma transacción.
        for tarja, _ in estados_antes:
            recalcular_estado(db, tarja)
        # Comprueba las restricciones antes de auditar.
        db.flush()

        # El motivo distingue la corrección en la bitácora.
        motivo = f"Edición del proceso {proceso.folio}"
        # Audita la cabecera con el antes y el después.
        registrar_auditoria(
            db,  # Comparte la sesión.
            usuario.id,  # Responsable autenticado.
            "procesos",  # Tabla afectada.
            proceso.id,  # Registro afectado.
            AccionAuditoria.UPDATE,  # Cambian sus totales.
            antes=proceso_antes,  # Estado anterior.
            despues=instantanea(proceso),  # Estado posterior.
            motivo=motivo,  # Corrección del pallet.
        )  # Finaliza el evento.
        # Audita cada fila del detalle.
        for fila_evento, antes, accion in eventos:
            registrar_auditoria(
                db,  # Comparte la sesión.
                usuario.id,  # Responsable autenticado.
                "proceso_tarjas",  # Tabla afectada.
                f"{fila_evento.proceso_id}:{fila_evento.tarja_id}",  # La clave de esta tabla es compuesta.
                accion,  # Fila nueva, cambiada o quitada.
                antes=antes,  # Estado anterior, si lo había.
                despues=None if accion == AccionAuditoria.DELETE else instantanea(fila_evento),  # Estado posterior.
                motivo=motivo,  # Corrección del pallet.
            )  # Finaliza el evento.
        # Audita las tarjas que cambiaron de estado o perdieron su merma.
        _auditar_tarjas(db, usuario, estados_antes, motivo)
        # Confirma todo una sola vez.
        db.commit()
    # Cualquier error revierte la operación completa.
    except Exception:
        # No queda un proceso a medias.
        db.rollback()
        # Deja que el router decida la respuesta.
        raise
    # Devuelve el proceso actualizado.
    return obtener_proceso(db, proceso_id)


# Anula un proceso sin borrarlo; sus kilos vuelven a sus tarjas de recepción (HU25).
def anular_proceso(db: Session, proceso_id: int, usuario: Usuario) -> dict:
    """Cada tarja del proceso vuelve a quedar pendiente hasta procesarse de nuevo o rebajarse.

    Decisión del 2026-11-03: el sistema calcula los kilos de merma, pero la decisión es del
    operador. Por eso la tarja pierde su merma rebajada y sus marcas, también las de otros
    procesos: se decidieron con otros kilos y no pueden crecer sin que nadie lo decida.
    """
    # Protege toda la escritura hasta el único commit (criterio 4).
    try:
        # Bloquea primero la cabecera, en el mismo orden que la edición.
        proceso = db.execute(
            select(Proceso)  # Relee la cabecera completa.
            .where(Proceso.id == proceso_id)  # Solo el proceso pedido.
            .with_hint(Proceso, "WITH (UPDLOCK, HOLDLOCK)", dialect_name="mssql")  # Bloqueo de actualización.
            .execution_options(populate_existing=True)  # Reemplaza los valores antiguos en memoria.
        ).scalars().first()  # Devuelve el proceso o None.
        # Un proceso inexistente responde 404.
        if proceso is None:
            raise ProcesoNoEncontradoError("Proceso no encontrado")
        # Anularlo dos veces no tiene sentido y dejaría un evento falso.
        if proceso.anulado:
            raise ProcesoNoEditableError(f"El proceso {proceso.folio} ya está anulado")
        # Lee las tarjas del proceso.
        tarja_ids = sorted(db.scalars(select(ProcesoTarja.tarja_id).where(ProcesoTarja.proceso_id == proceso.id)).all())
        # Bloquea en orden de id: nadie consume esos kilos mientras vuelven.
        tarjas = [_bloquear_tarja(db, tarja_id) for tarja_id in tarja_ids]

        # Captura la cabecera y las tarjas antes de modificarlas.
        proceso_antes = instantanea(proceso)
        estados_antes = [(tarja, instantanea(tarja)) for tarja in tarjas]
        # Queda anulado y no se borra; su folio no se reutiliza (criterio 2).
        proceso.anulado = True
        # Debe estar en la base para que sus filas dejen de contar.
        db.flush()

        # Eventos de las marcas que se quitan en otros procesos.
        eventos = []
        # Todas sus tarjas recuperan kilos, porque cada fila tiene más de cero.
        for tarja in tarjas:
            eventos.extend(_quitar_cierre_decidido(db, tarja, proceso.id))
        # Lleva los cambios a la base antes de recalcular.
        db.flush()
        # Cada tarja queda con el estado que indican sus procesos vigentes (criterio 3).
        for tarja in tarjas:
            recalcular_estado(db, tarja)
        # Comprueba las restricciones antes de auditar.
        db.flush()

        # El motivo explica por qué cambian las tarjas; al administrador no se le exige uno (criterio 1).
        motivo = f"Anulación del proceso {proceso.folio}"
        # Audita la cabecera: quién y cuándo.
        registrar_auditoria(
            db,  # Comparte la sesión.
            usuario.id,  # Administrador autenticado.
            "procesos",  # Tabla afectada.
            proceso.id,  # Registro afectado.
            AccionAuditoria.UPDATE,  # No se borra: se marca anulado.
            antes=proceso_antes,  # Estado anterior.
            despues=instantanea(proceso),  # Estado posterior.
            motivo=motivo,  # Causa del cambio.
        )  # Finaliza el evento.
        # Audita las marcas quitadas en otros procesos.
        for fila_evento, antes, accion in eventos:
            registrar_auditoria(
                db,  # Comparte la sesión.
                usuario.id,  # Administrador autenticado.
                "proceso_tarjas",  # Tabla afectada.
                f"{fila_evento.proceso_id}:{fila_evento.tarja_id}",  # La clave de esta tabla es compuesta.
                accion,  # Cambia la marca.
                antes=antes,  # Estado anterior.
                despues=instantanea(fila_evento),  # Estado posterior.
                motivo=motivo,  # Causa del cambio.
            )  # Finaliza el evento.
        # Audita las tarjas que cambiaron de estado o perdieron su merma.
        _auditar_tarjas(db, usuario, estados_antes, motivo)
        # Confirma todo una sola vez (criterio 4).
        db.commit()
    # Cualquier error revierte la operación completa.
    except Exception:
        # No queda un proceso anulado con sus tarjas sin devolver.
        db.rollback()
        # Deja que el router decida la respuesta.
        raise
    # Devuelve el proceso anulado.
    return obtener_proceso(db, proceso_id)


# Consulta común del listado y del detalle: la cabecera con sus nombres.
def _consulta_procesos():
    # Las etiquetas coinciden con los campos de los schemas de salida.
    return (
        select(
            Proceso,  # Todas las columnas de la cabecera.
            Embalaje.nombre.label("embalaje"),  # Nombre del embalaje.
            Embalaje.kg_por_caja.label("embalaje_kg_por_caja"),  # Peso por caja; nulo a granel.
            Usuario.nombre_completo.label("registrado_por"),  # Solo el nombre: nunca credenciales.
        )  # Finaliza las columnas.
        .join(Embalaje, Proceso.embalaje_id == Embalaje.id)  # Todo proceso tiene embalaje.
        .join(Usuario, Proceso.usuario_id == Usuario.id)  # Y usuario que lo registró.
    )  # Un embalaje desactivado se sigue mostrando: el join no filtra por activo.


# Convierte una fila de la consulta en los datos que esperan los schemas.
def _datos_de_proceso(fila) -> dict:
    # Une las columnas de la cabecera con los nombres.
    return {
        **instantanea(fila.Proceso),  # Columnas de la cabecera.
        "embalaje": fila.embalaje,  # Nombre del embalaje.
        "embalaje_kg_por_caja": fila.embalaje_kg_por_caja,  # Peso por caja.
        "registrado_por": fila.registrado_por,  # Responsable.
    }  # Finaliza los datos.


# Lista los procesos, los más recientes primero.
def listar_procesos(db: Session) -> list[dict]:
    # Los más recientes primero, con un máximo de filas.
    consulta = _consulta_procesos().order_by(Proceso.id.desc()).limit(MAXIMO_FILAS_LISTADO)
    # Devuelve cada fila lista para el schema.
    return [_datos_de_proceso(fila) for fila in db.execute(consulta).all()]


# Obtiene un proceso con sus tarjas (HU18 criterio 7).
def obtener_proceso(db: Session, proceso_id: int) -> dict | None:
    # Busca la cabecera.
    fila = db.execute(_consulta_procesos().where(Proceso.id == proceso_id)).first()
    # Devuelve None si no existe; el router resuelve el 404.
    if fila is None:
        return None
    # Lee el detalle con la tarja y su productor.
    consulta = (
        select(
            ProcesoTarja,  # Cajas, kilos y marca.
            Tarja.numero_tarja,  # Número de la tarja.
            Tarja.kilos_netos,  # Kilos recibidos.
            Tarja.estado.label("estado_tarja"),  # Estado actual.
            Productor.codigo.label("productor_codigo"),  # Código del productor.
            Productor.razon_social.label("productor_razon_social"),  # Nombre del productor.
            SistemaProductivo.nombre.label("sistema_productivo"),  # Nombre del sistema productivo.
            Especie.nombre.label("especie"),  # Nombre de la especie.
            Variedad.nombre.label("variedad"),  # Nombre de la variedad.
            Calidad.nombre.label("calidad"),  # Nombre de la calidad.
        )  # Finaliza las columnas.
        .join(Tarja, ProcesoTarja.tarja_id == Tarja.id)  # Toda fila tiene tarja.
        .join(Productor, Tarja.productor_id == Productor.id)  # Y productor.
        .join(SistemaProductivo, Tarja.sistema_productivo_id == SistemaProductivo.id)  # Y sistema productivo.
        .join(Variedad, Tarja.variedad_id == Variedad.id)  # Y variedad.
        .join(Especie, Variedad.especie_id == Especie.id)  # La especie sale de la variedad.
        .join(Calidad, Tarja.calidad_id == Calidad.id)  # Y calidad.
        .where(ProcesoTarja.proceso_id == proceso_id)  # Solo este proceso.
        .order_by(Tarja.numero_tarja)  # Orden estable.
    )  # Finaliza la consulta.
    # Convierte cada fila.
    tarjas = [
        {
            **instantanea(detalle.ProcesoTarja),  # Columnas de la fila.
            "numero_tarja": detalle.numero_tarja,  # Número de la tarja.
            "estado_tarja": detalle.estado_tarja.value,  # El estado viaja como texto.
            "productor_codigo": detalle.productor_codigo,  # Código del productor.
            "productor_razon_social": detalle.productor_razon_social,  # Nombre del productor.
            "sistema_productivo": detalle.sistema_productivo,  # Sistema productivo.
            "especie": detalle.especie,  # Especie.
            "variedad": detalle.variedad,  # Variedad.
            "calidad": detalle.calidad,  # Calidad.
            # Lo que la fila tiene más lo que le queda a la tarja; cerrada por decisión también cuenta su merma.
            "kilos_disponibles": Decimal(detalle.kilos_netos) - kilos_procesados_de_tarja(db, detalle.ProcesoTarja.tarja_id) + (Decimal("0") if fila.Proceso.anulado else detalle.ProcesoTarja.kilos_procesados),
        }  # Finaliza la fila.
        for detalle in db.execute(consulta).all()
    ]
    # Une la cabecera con el detalle.
    return {**_datos_de_proceso(fila), "tarjas": tarjas}


# Rebaja como merma los kilos que le quedan a una tarja de recepción y la cierra.
def terminar_tarja(db: Session, tarja_id: int, usuario: Usuario) -> dict:
    """Decisión del 2026-11-03: la merma es de la tarja de recepción, no del proceso.

    Los kilos pendientes se rebajan sin registrar otro proceso, también en una tarja que
    nunca entró a uno. El proceso no se toca: solo contiene fruta seleccionada. La merma
    tampoco se guarda: sigue siendo kilos netos menos kilos procesados.
    """
    # Protege toda la escritura hasta el único commit.
    try:
        # Bloquea la tarja: nadie puede consumir kilos mientras se cierra.
        tarja = _bloquear_tarja(db, tarja_id)
        # Una tarja inexistente responde 404.
        if tarja is None:
            raise TarjaNoEncontradaError("Tarja no encontrada")
        # Solo una tarja con kilos pendientes tiene algo que rebajar.
        if tarja.estado not in (EstadoTarja.RECEPCIONADA, EstadoTarja.PARCIAL):
            raise TarjaNoProcesableError(f"La tarja N° {tarja.numero_tarja} no tiene kilos por rebajar: está {tarja.estado.value.lower()}")
        # Captura el estado antes de modificarlo.
        antes = instantanea(tarja)
        # Deja la decisión en la tarja.
        tarja.merma_rebajada = True
        # La tarja pasa a PROCESADA con la misma regla de siempre.
        recalcular_estado(db, tarja)
        # Comprueba las restricciones antes de auditar.
        db.flush()
        # Calcula lo que queda como merma.
        procesados = kilos_procesados_de_tarja(db, tarja.id)
        merma = Decimal(tarja.kilos_netos) - procesados
        # Audita el cierre con los kilos a la vista en la bitácora.
        registrar_auditoria(
            db,  # Comparte la sesión.
            usuario.id,  # Responsable autenticado.
            "tarjas",  # Tabla afectada.
            tarja.id,  # Registro afectado.
            AccionAuditoria.UPDATE,  # Cambia su estado.
            antes=antes,  # Estado anterior.
            despues=instantanea(tarja),  # Estado posterior.
            motivo=f"Saldo de {merma} kg rebajado como merma",  # Kilos rebajados.
        )  # Finaliza el evento.
        # Confirma el cierre y la auditoría juntos.
        db.commit()
    # Cualquier error revierte la operación completa.
    except Exception:
        # No queda un cierre sin auditoría.
        db.rollback()
        # Deja que el router decida la respuesta.
        raise
    # Devuelve cómo quedó la tarja.
    return {
        "tarja_id": tarja.id,  # Tarja cerrada.
        "numero_tarja": tarja.numero_tarja,  # Número.
        "kilos_netos": tarja.kilos_netos,  # Recibidos.
        "kilos_procesados": procesados,  # Salieron en procesos.
        "kilos_merma": merma,  # Diferencia.
        "estado": tarja.estado.value,  # Estado final.
    }  # Finaliza la respuesta.


# Deshace una rebaja hecha por error: la tarja vuelve a quedar pendiente.
def reabrir_tarja(db: Session, tarja_id: int, usuario: Usuario) -> dict:
    # Protege toda la escritura hasta el único commit.
    try:
        # Bloquea la tarja.
        tarja = _bloquear_tarja(db, tarja_id)
        # Una tarja inexistente responde 404.
        if tarja is None:
            raise TarjaNoEncontradaError("Tarja no encontrada")
        # Solo se deshace una rebaja: una tarja cerrada por sus procesos se corrige anulándolos.
        if not tarja.merma_rebajada:
            raise TarjaNoProcesableError(f"La tarja N° {tarja.numero_tarja} no tiene una merma rebajada")
        # Captura el estado antes de modificarlo.
        antes = instantanea(tarja)
        # Quita la decisión.
        tarja.merma_rebajada = False
        # Vuelve al estado que indican sus procesos.
        recalcular_estado(db, tarja)
        # Comprueba las restricciones antes de auditar.
        db.flush()
        # Calcula cómo quedan sus kilos.
        procesados = kilos_procesados_de_tarja(db, tarja.id)
        # Audita quién la reabrió y cuándo.
        registrar_auditoria(
            db,  # Comparte la sesión.
            usuario.id,  # Responsable autenticado.
            "tarjas",  # Tabla afectada.
            tarja.id,  # Registro afectado.
            AccionAuditoria.UPDATE,  # Cambia su estado.
            antes=antes,  # Estado anterior.
            despues=instantanea(tarja),  # Estado posterior.
            motivo="Merma rebajada deshecha",  # Distingue el evento.
        )  # Finaliza el evento.
        # Confirma todo junto.
        db.commit()
    # Cualquier error revierte la operación completa.
    except Exception:
        # No queda un cambio sin auditoría.
        db.rollback()
        # Deja que el router decida la respuesta.
        raise
    # Devuelve cómo quedó la tarja; ya no hay merma decidida.
    return {
        "tarja_id": tarja.id,  # Tarja reabierta.
        "numero_tarja": tarja.numero_tarja,  # Número.
        "kilos_netos": tarja.kilos_netos,  # Recibidos.
        "kilos_procesados": procesados,  # Salieron en procesos.
        "kilos_merma": Decimal("0.00"),  # Ya no se rebajó nada.
        "estado": tarja.estado.value,  # Estado resultante.
    }  # Finaliza la respuesta.
