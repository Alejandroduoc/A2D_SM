"""HU12-HU14: prueba reproducible del registro de tarjas de recepción.

Ejecutar desde sistema/: docker compose exec -T backend python -m tests.probar_tarjas
Todas las filas temporales quedan dentro de una transacción externa revertida.
"""

# Ejecuta la aplicación ASGI desde funciones normales.
import asyncio
# Calcula las huellas de las tablas.
import hashlib
# Serializa cuerpos, respuestas y huellas.
import json
# Registrar el fallo de un escenario no detiene el informe final.
import sys
# Imprime el detalle de un error inesperado.
import traceback
# Genera nombres y ids que no chocan con datos existentes.
import uuid
# Declara los contextos de aislamiento.
from contextlib import contextmanager
# Compara fechas y calcula la fecha de mañana.
from datetime import datetime, timedelta, timezone
# Pesos exactos, sin float.
from decimal import Decimal
# Simula el fallo de la auditoría.
from unittest.mock import patch
# Separa la ruta y la consulta de cada petición.
from urllib.parse import urlsplit

# Consultas de lectura y SQL directo para huellas y secuencia.
from sqlalchemy import func, select, text
# Sesión unida a la transacción externa de la prueba.
from sqlalchemy.orm import Session

# Conexión a la base y dependencia de sesión que se sobrescribe.
from app.core.database import engine, get_db
# Genera los tokens de los actores de prueba.
from app.core.security import create_access_token
# Aplicación real que reciben las peticiones.
from app.main import app
# Modelos que se crean o se comprueban.
from app.models.auditoria import AccionAuditoria, Auditoria
from app.models.calidad import Calidad
from app.models.especie import Especie
from app.models.movimiento_bandeja import MovimientoBandeja, TipoMovimientoBandeja
from app.models.productor import Productor
from app.models.sistema_productivo import SistemaProductivo
from app.models.tarja import EstadoTarja, Tarja
from app.models.tipo_bandeja import TipoBandeja
from app.models.usuario import RolUsuario, Usuario, UsuarioRol
from app.models.variedad import Variedad
# Schema de entrada y fecha de hoy en Chile.
from app.schemas.tarja import TarjaCreate, hoy_en_chile
# Misma instantánea que guarda la auditoría.
from app.services.auditoria import instantanea
# Funciones del service que se prueban directamente.
from app.services.tarja import anular_tarja, calcular_kilos_netos, registrar_impresion, registrar_tarja


# Tablas cuyas huellas no deben cambiar al terminar.
TABLAS = (
    "usuarios",
    "usuario_roles",
    "auditoria",
    "productores",
    "especies",
    "variedades",
    "calidades",
    "sistemas_productivos",
    "tipos_bandeja",
    "tarjas",
    "movimientos_bandeja",
    "procesos",
    "proceso_tarjas",
)
# Ruta base del módulo.
BASE = "/api/v1/tarjas"
# Contadores del resultado final.
comprobaciones = 0
fallas = 0


# Cuenta e imprime una comprobación.
def comprobar(nombre: str, condicion: bool) -> None:
    # Los contadores son globales del módulo.
    global comprobaciones, fallas
    # Suma la comprobación al total.
    comprobaciones += 1
    # Una condición falsa suma una falla.
    if not condicion:
        fallas += 1
    # Imprime al momento, para ver el avance.
    print(("OK    " if condicion else "FALLA ") + nombre, flush=True)


# Calcula cantidad de filas y hash de cada tabla.
def huellas(conexion) -> dict:
    # Resultado por tabla.
    salida = {}
    # Recorre las tablas protegidas.
    for tabla in TABLAS:
        # Lee todas las filas como diccionarios.
        filas = conexion.execute(text("SELECT * FROM " + tabla)).mappings().all()
        # Ordena las filas para que el hash no dependa del orden de lectura.
        serial = sorted(json.dumps(dict(fila), sort_keys=True, default=str) for fila in filas)
        # Guarda la cantidad y el hash.
        salida[tabla] = (
            len(filas),
            hashlib.sha256("\n".join(serial).encode("utf-8")).hexdigest(),
        )
    # Entrega la huella completa.
    return salida


# Ejecuta un escenario dentro de una transacción que siempre se revierte.
@contextmanager
def aislado():
    # Abre una conexión propia del escenario.
    with engine.connect() as conexion:
        # Transacción externa que contiene todo el escenario.
        externa = conexion.begin()
        # Los commit del service solo confirman un savepoint.
        db = Session(
            bind=conexion,
            autoflush=False,
            join_transaction_mode="create_savepoint",
        )
        # Garantiza la limpieza aunque el escenario falle.
        try:
            # Entrega sesión, conexión y transacción al escenario.
            yield db, conexion, externa
            # Un commit indebido habría cerrado la transacción externa.
            comprobar(
                "Aislamiento - transacción externa activa",
                externa.is_active and conexion.in_transaction(),
            )
        # Cierra la sesión en todos los casos.
        finally:
            # Libera la sesión antes de revertir.
            db.close()
            # Revierte solo si sigue abierta.
            if externa.is_active:
                externa.rollback()


# Crea un usuario con un rol y su token.
def crear_actor(db: Session, rol: RolUsuario) -> tuple[Usuario, str]:
    # El hash es ficticio: la prueba no usa el login.
    actor = Usuario(
        id=str(uuid.uuid4()),
        nombre_usuario="qa_tarjas_" + uuid.uuid4().hex[:20],
        nombre_completo="Actor QA Tarjas",
        password_hash="ficticio_no_sirve_para_login",
        activo=True,
        roles_asignados=[UsuarioRol(rol=rol)],
    )
    # Agrega el actor a la transacción.
    db.add(actor)
    # Lo inserta para que la API lo encuentre.
    db.flush()
    # Token con el rol en el JWT, aunque la autorización lea la base.
    token = create_access_token(actor.nombre_usuario, [rol.value])
    # Entrega el actor y su token.
    return actor, token


# Envía una petición a la aplicación, en memoria y sin servidor.
async def _solicitar(
    metodo: str,
    ruta: str,
    token: str | None = None,
    datos=None,
) -> tuple[int, object]:
    # Separa la ruta de la consulta.
    partes = urlsplit(ruta)
    # Cuerpo JSON, o vacío si no hay datos.
    cuerpo = json.dumps(datos).encode("utf-8") if datos is not None else b""
    # Cabeceras mínimas de una petición HTTP.
    cabeceras = [(b"host", b"qa-tarjas")]
    # Declara el JSON solo si hay cuerpo.
    if datos is not None:
        cabeceras += [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(cuerpo)).encode()),
        ]
    # Agrega el token si la petición lo lleva.
    if token:
        cabeceras.append((b"authorization", ("Bearer " + token).encode()))
    # Descripción de la petición según el protocolo ASGI.
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": metodo,
        "scheme": "http",
        "path": partes.path,
        "raw_path": partes.path.encode(),
        "query_string": partes.query.encode(),
        "root_path": "",
        "headers": cabeceras,
        "client": ("127.0.0.1", 1),
        "server": ("qa-tarjas", 80),
    }
    # Mensajes de respuesta que entrega la aplicación.
    mensajes = []
    # El cuerpo se entrega una sola vez.
    entregado = False

    # La aplicación lee el cuerpo con esta función.
    async def receive():
        # Modifica la variable de la función exterior.
        nonlocal entregado
        # Después del cuerpo, la petición terminó.
        if entregado:
            return {"type": "http.disconnect"}
        # Marca el cuerpo como entregado.
        entregado = True
        # Entrega el cuerpo completo.
        return {"type": "http.request", "body": cuerpo, "more_body": False}

    # La aplicación escribe la respuesta con esta función.
    async def send(mensaje):
        # Guarda cada mensaje recibido.
        mensajes.append(mensaje)

    # Ejecuta la aplicación con esta petición.
    await app(scope, receive, send)
    # El código HTTP viene en el primer mensaje.
    estado = next(m["status"] for m in mensajes if m["type"] == "http.response.start")
    # Une las partes del cuerpo de la respuesta.
    contenido = b"".join(
        m.get("body", b"") for m in mensajes if m["type"] == "http.response.body"
    ).decode("utf-8")
    # Devuelve JSON cuando la respuesta lo es.
    try:
        return estado, json.loads(contenido)
    # Una respuesta que no es JSON se devuelve como texto.
    except ValueError:
        return estado, contenido


# Versión normal (no asíncrona) de la petición.
def solicitar(metodo: str, ruta: str, token: str | None = None, datos=None):
    # Espera la respuesta antes de seguir.
    return asyncio.run(_solicitar(metodo, ruta, token, datos))


# Hace que la API use la sesión del escenario.
@contextmanager
def api_con_sesion(db: Session):
    # Guarda las dependencias para restaurarlas.
    anteriores = dict(app.dependency_overrides)

    # Reemplazo de get_db que entrega la sesión aislada.
    def proveedor():
        # Comparte la transacción con la prueba.
        yield db

    # Activa el reemplazo.
    app.dependency_overrides[get_db] = proveedor
    # Restaura las dependencias aunque el escenario falle.
    try:
        # Ejecuta el bloque del escenario.
        yield
    finally:
        # Quita el reemplazo.
        app.dependency_overrides.clear()
        # Repone lo que había antes.
        app.dependency_overrides.update(anteriores)


# Cuenta tarjas, movimientos y eventos, para detectar escrituras.
def cantidades(db: Session) -> tuple[int, int, int]:
    # Las tres cantidades se comparan antes y después.
    return (
        db.scalar(select(func.count()).select_from(Tarja)),
        db.scalar(select(func.count()).select_from(MovimientoBandeja)),
        db.scalar(select(func.count()).select_from(Auditoria)),
    )


# Convierte una instantánea con fechas, decimales y enums como lo hace auditoría.
def instantanea_json(objeto) -> dict:
    return json.loads(json.dumps(instantanea(objeto), default=str))


# SQL Server DateTime pierde la zona y redondea milisegundos al persistir.
def instantanea_auditada_coincide(evento: Auditoria, objeto) -> bool:
    auditada = json.loads(evento.valores_despues)
    persistida = instantanea_json(objeto)
    fecha_auditada = datetime.fromisoformat(auditada.pop("fecha_hora"))
    fecha_persistida = datetime.fromisoformat(persistida.pop("fecha_hora"))
    if fecha_auditada.tzinfo is not None:
        fecha_auditada = fecha_auditada.astimezone(timezone.utc).replace(tzinfo=None)
    if fecha_persistida.tzinfo is not None:
        fecha_persistida = fecha_persistida.astimezone(timezone.utc).replace(tzinfo=None)
    return (
        evento.valores_antes is None
        and auditada == persistida
        and abs((fecha_auditada - fecha_persistida).total_seconds()) <= 0.01
    )


# Crea los datos de prueba, activos e inactivos.
def preparar(db: Session) -> dict:
    # Sufijo que evita chocar con nombres existentes.
    sufijo = uuid.uuid4().hex[:8]
    # Un actor por cada rol del sistema.
    actores = {rol: crear_actor(db, rol) for rol in RolUsuario}
    # Especie de las variedades de prueba.
    especie = Especie(nombre=f"QA Especie {sufijo}", activo=True)
    # La agrega a la transacción.
    db.add(especie)
    # La inserta para obtener su id.
    db.flush()
    # Variedad activa.
    variedad = Variedad(
        especie_id=especie.id,
        nombre=f"QA Variedad {sufijo}",
        activo=True,
    )
    # Variedad inactiva.
    variedad_inactiva = Variedad(
        especie_id=especie.id,
        nombre=f"QA Variedad inactiva {sufijo}",
        activo=False,
    )
    # Productor activo; la prueba no valida el RUT.
    productor = Productor(
        rut=uuid.uuid4().hex[:8] + "-K",
        razon_social=f"QA Productor {sufijo}",
        activo=True,
    )
    # Productor inactivo.
    productor_inactivo = Productor(
        rut=uuid.uuid4().hex[:8] + "-0",
        razon_social=f"QA Productor inactivo {sufijo}",
        activo=False,
    )
    # Sistema productivo activo.
    sistema = SistemaProductivo(nombre=f"QA Sistema {sufijo}", activo=True)
    # Sistema productivo inactivo.
    sistema_inactivo = SistemaProductivo(
        nombre=f"QA Sistema inactivo {sufijo}", activo=False
    )
    # Calidad activa.
    calidad = Calidad(nombre=f"QA Calidad {sufijo}", activo=True)
    # Calidad inactiva.
    calidad_inactiva = Calidad(nombre=f"QA Calidad inactiva {sufijo}", activo=False)
    # Bandeja activa con tara 1,20.
    bandeja = TipoBandeja(
        nombre=f"QA Bandeja {sufijo}", peso_tara_kg=Decimal("1.20"), activo=True
    )
    # Bandeja inactiva.
    bandeja_inactiva = TipoBandeja(
        nombre=f"QA Bandeja inactiva {sufijo}",
        peso_tara_kg=Decimal("1.30"),
        activo=False,
    )
    # Agrega todos los datos a la transacción.
    db.add_all(
        [
            variedad,
            variedad_inactiva,
            productor,
            productor_inactivo,
            sistema,
            sistema_inactivo,
            calidad,
            calidad_inactiva,
            bandeja,
            bandeja_inactiva,
        ]
    )
    # Solo confirma el savepoint.
    db.commit()
    # Entrega los datos a los escenarios.
    return {
        "actores": actores,
        "productor": productor,
        "productor_inactivo": productor_inactivo,
        "sistema": sistema,
        "sistema_inactivo": sistema_inactivo,
        "variedad": variedad,
        "variedad_inactiva": variedad_inactiva,
        "calidad": calidad,
        "calidad_inactiva": calidad_inactiva,
        "bandeja": bandeja,
        "bandeja_inactiva": bandeja_inactiva,
    }


# Cuerpo de una tarja válida: 1000 − 50 × 1,20 − 20 = 920 kg.
def cuerpo_valido(datos: dict) -> dict:
    # Cada caso cambia solo el campo que prueba.
    return {
        "productor_id": datos["productor"].id,
        "sistema_productivo_id": datos["sistema"].id,
        "variedad_id": datos["variedad"].id,
        "calidad_id": datos["calidad"].id,
        "tipo_bandeja_id": datos["bandeja"].id,
        "cantidad_bandejas": 50,
        "peso_pallet_kg": "20.00",
        "kilos_brutos": "1000.00",
        "porcentaje_calidad": 85,
        "fecha_recepcion": hoy_en_chile().isoformat(),
    }


# HU14 criterio 1: fórmula y redondeo bancario.
def probar_calculo() -> None:
    # Caso de la guía.
    comprobar(
        "Cálculo - caso 920 kg",
        calcular_kilos_netos(Decimal("1000"), 50, Decimal("1.20"), Decimal("20"))
        == 920,
    )
    # 916,5 baja al par.
    comprobar(
        "Cálculo - mitad par baja",
        calcular_kilos_netos(Decimal("916.5"), 1, Decimal("0"), Decimal("0"))
        == 916,
    )
    # 917,5 sube al par.
    comprobar(
        "Cálculo - mitad impar sube",
        calcular_kilos_netos(Decimal("917.5"), 1, Decimal("0"), Decimal("0"))
        == 918,
    )


# HU13 criterio 2: dos conexiones no reciben el mismo número.
def probar_secuencia_concurrente() -> None:
    # Dos conexiones distintas, como dos operadores.
    with engine.connect() as primera, engine.connect() as segunda:
        # Pedir un número no lee datos sin confirmar: no se bloquea.
        numero_1 = primera.scalar(text("SELECT NEXT VALUE FOR seq_numero_tarja"))
        # Número de la segunda conexión.
        numero_2 = segunda.scalar(text("SELECT NEXT VALUE FOR seq_numero_tarja"))
        # Nunca deben coincidir.
        comprobar(
            "HU13 - dos conexiones reciben números distintos",
            numero_1 != numero_2,
        )


# Recorre la API completa dentro de una transacción aislada.
def probar_api() -> None:
    # Todo lo que se crea aquí se revierte.
    with aislado() as (db, conexion, externa):
        # Crea los datos de prueba.
        datos = preparar(db)
        # Actores por rol.
        actores = datos["actores"]
        # Operador de recepción, que registra las tarjas.
        recepcion, token_recepcion = actores[RolUsuario.OPERADOR_RECEPCION]
        # Administrador, también autorizado.
        _, token_admin = actores[RolUsuario.ADMINISTRADOR]
        # Gerencia, no autorizada.
        _, token_gerencia = actores[RolUsuario.GERENCIA]
        # Operador de proceso, no autorizado.
        proceso, token_proceso = actores[RolUsuario.OPERADOR_PROCESO]
        # Cuerpo base de los casos.
        cuerpo = cuerpo_valido(datos)

        # La API usa la sesión del escenario.
        with api_con_sesion(db):
            # Rutas que publica la aplicación.
            rutas = app.openapi()["paths"]
            # El módulo publica exactamente estas rutas.
            comprobar(
                "A3 - rutas publicadas",
                {ruta for ruta in rutas if ruta.startswith(BASE)}
                == {BASE, BASE + "/pendientes", BASE + "/saldo-bandejas", BASE + "/{tarja_id}", BASE + "/{tarja_id}/imprimir", BASE + "/{tarja_id}/anular"},
            )

            # Cantidades antes de los rechazos de permisos.
            antes = cantidades(db)
            # HU12 criterio 5: sin token.
            comprobar(
                "Permisos - sin token 401",
                solicitar("POST", BASE, datos=cuerpo)[0] == 401,
            )
            # Gerencia no registra tarjas.
            comprobar(
                "Permisos - gerencia 403",
                solicitar("POST", BASE, token_gerencia, cuerpo)[0] == 403,
            )
            # Operador de proceso no registra tarjas.
            comprobar(
                "Permisos - proceso 403",
                solicitar("POST", BASE, token_proceso, cuerpo)[0] == 403,
            )
            # Token que declara un rol que el usuario no tiene en la base.
            token_obsoleto = create_access_token(
                proceso.nombre_usuario,
                [RolUsuario.OPERADOR_RECEPCION.value],
            )
            # La autorización lee la base, no el JWT.
            comprobar(
                "Permisos - rol obsoleto del JWT 403",
                solicitar("POST", BASE, token_obsoleto, cuerpo)[0] == 403,
            )
            # Ningún rechazo dejó filas.
            comprobar("Permisos - sin escrituras", cantidades(db) == antes)

            # Alta válida.
            estado, salida = solicitar("POST", BASE, token_recepcion, cuerpo)
            # Responde 201.
            comprobar("Alta - HTTP 201", estado == 201)
            # HU13 y HU14: número, neto, tara copiada y estado inicial.
            comprobar(
                "Alta - número, neto, tara y estado",
                isinstance(salida.get("numero_tarja"), int)
                and salida.get("kilos_netos") == 920
                and Decimal(str(salida.get("tara_kg"))) == Decimal("1.20")
                and salida.get("estado") == EstadoTarja.RECEPCIONADA.value,
            )
            # Guarda el id para los casos siguientes.
            tarja_id = salida["id"]
            # Guarda el número para compararlo.
            numero_1 = salida["numero_tarja"]
            # Busca la entrada de bandejas de la tarja.
            movimiento = db.scalar(
                select(MovimientoBandeja).where(MovimientoBandeja.tarja_id == tarja_id)
            )
            # HU12 criterio 2: una entrada con la misma cantidad.
            comprobar(
                "Alta - entrada de 50 bandejas",
                movimiento is not None
                and movimiento.tipo == TipoMovimientoBandeja.ENTRADA
                and movimiento.cantidad == 50,
            )
            # Eventos de auditoría de la tarja.
            eventos_tarja = list(
                db.scalars(
                    select(Auditoria).where(
                        Auditoria.tabla == "tarjas",
                        Auditoria.registro_id == str(tarja_id),
                    )
                )
            )
            # Eventos de auditoría del movimiento.
            eventos_movimiento = list(
                db.scalars(
                    select(Auditoria).where(
                        Auditoria.tabla == "movimientos_bandeja",
                        Auditoria.registro_id == str(movimiento.id),
                    )
                )
            )
            # Un INSERT por tabla, con el usuario real.
            comprobar(
                "Alta - dos auditorías INSERT con actor real",
                len(eventos_tarja) == len(eventos_movimiento) == 1
                and eventos_tarja[0].accion == AccionAuditoria.INSERT
                and eventos_movimiento[0].accion == AccionAuditoria.INSERT
                and eventos_tarja[0].usuario_id == recepcion.id
                and eventos_movimiento[0].usuario_id == recepcion.id,
            )
            # La auditoría guarda la tarja completa.
            comprobar(
                "Alta - instantánea completa de la tarja",
                instantanea_auditada_coincide(
                    eventos_tarja[0], db.get(Tarja, tarja_id)
                ),
            )
            # La auditoría guarda el movimiento completo.
            comprobar(
                "Alta - instantánea completa del movimiento",
                instantanea_auditada_coincide(eventos_movimiento[0], movimiento),
            )

            # Segunda tarja, registrada por el administrador.
            estado, segunda = solicitar("POST", BASE, token_admin, cuerpo)
            # HU13 criterio 1: el número crece.
            comprobar(
                "HU13 - dos altas tienen números crecientes",
                estado == 201 and segunda["numero_tarja"] > numero_1,
            )

            # Detalle de una tarja existente.
            estado, detalle = solicitar("GET", f"{BASE}/{tarja_id}", token_recepcion)
            # Devuelve la tarja pedida.
            comprobar("Detalle - tarja existente 200", estado == 200 and detalle["id"] == tarja_id)
            # Una tarja inexistente responde 404.
            comprobar(
                "Detalle - inexistente 404",
                solicitar("GET", f"{BASE}/999999999", token_recepcion)[0] == 404,
            )
            # Un id mayor que un INT responde 422, no un error interno.
            comprobar(
                "Detalle - id mayor que un INT 422",
                solicitar("GET", f"{BASE}/{'9' * 19}", token_recepcion)[0] == 422,
            )
            comprobar(
                "Pendientes - id mayor que un INT 422",
                solicitar(
                    "GET", f"{BASE}/pendientes?productor_id={'9' * 19}", token_recepcion
                )[0]
                == 422,
            )
            comprobar(
                "Alta - id mayor que un INT 422",
                solicitar(
                    "POST", BASE, token_recepcion, dict(cuerpo, productor_id=10**19)
                )[0]
                == 422,
            )

            # Cambia los estados para probar los acumulados.
            primera = db.get(Tarja, tarja_id)
            # Segunda tarja, que quedará procesada.
            segunda_db = db.get(Tarja, segunda["id"])
            # PARCIAL cuenta como pendiente.
            primera.estado = EstadoTarja.PARCIAL
            # PROCESADA no cuenta.
            segunda_db.estado = EstadoTarja.PROCESADA
            # Solo confirma el savepoint.
            db.commit()
            # Decisión D: acumulados del productor.
            estado, pendientes = solicitar(
                "GET",
                f"{BASE}/pendientes?productor_id={datos['productor'].id}",
                token_recepcion,
            )
            # Cuenta una tarja con sus 920 kg.
            comprobar(
                "Pendientes - solo RECEPCIONADA y PARCIAL",
                estado == 200
                and pendientes["tarjas_sin_procesar"] == 1
                and Decimal(pendientes["kilos_sin_procesar"]) == 920,
            )
            # Un id cero responde 422.
            comprobar(
                "Pendientes - productor_id inválido 422",
                solicitar(
                    "GET", f"{BASE}/pendientes?productor_id=0", token_recepcion
                )[0]
                == 422,
            )

            # Catálogos inexistentes o inactivos no pueden dejar filas ni eventos.
            campos_invalidos = (
                ("productor_id", datos["productor_inactivo"].id),
                ("sistema_productivo_id", datos["sistema_inactivo"].id),
                ("variedad_id", datos["variedad_inactiva"].id),
                ("calidad_id", datos["calidad_inactiva"].id),
                ("tipo_bandeja_id", datos["bandeja_inactiva"].id),
                ("productor_id", 999999999),
            )
            # Cada dato inválido se prueba por separado.
            for campo, valor in campos_invalidos:
                # Cantidades antes del rechazo.
                antes = cantidades(db)
                # Envía el cuerpo con el dato inválido.
                estado, _ = solicitar(
                    "POST", BASE, token_recepcion, dict(cuerpo, **{campo: valor})
                )
                # Se rechaza por negocio.
                comprobar(f"Catálogo - {campo} rechazado 400", estado == 400)
                # No deja filas ni eventos.
                comprobar(f"Catálogo - {campo} sin escrituras", cantidades(db) == antes)

            # Neto cero o negativo se rechaza por negocio, no por el schema.
            # HU14 criterio 2: balanza que deja el neto en cero o negativo.
            for etiqueta, kilos in (("cero", "80.00"), ("negativo", "79.00")):
                # Cantidades antes del rechazo.
                antes = cantidades(db)
                # Envía el cuerpo con ese peso.
                estado, _ = solicitar(
                    "POST",
                    BASE,
                    token_recepcion,
                    dict(cuerpo, kilos_brutos=kilos),
                )
                # Se rechaza por negocio.
                comprobar(f"Neto {etiqueta} - HTTP 400", estado == 400)
                # No deja filas ni eventos.
                comprobar(
                    f"Neto {etiqueta} - sin escrituras",
                    cantidades(db) == antes,
                )

            # Fecha futura en Chile.
            manana = (hoy_en_chile() + timedelta(days=1)).isoformat()
            # Campos que el cliente no envía y valores inválidos.
            invalidos = (
                {"numero_tarja": 99},
                {"kilos_netos": 1},
                {"estado": "RECEPCIONADA"},
                {"porcentaje_calidad": 101},
                {"porcentaje_calidad": -1},
                {"cantidad_bandejas": 0},
                {"cantidad_bandejas": 2147483648},
                {"fecha_recepcion": manana},
                {"peso_pallet_kg": "-1"},
                {"peso_pallet_kg": "1000000.00"},
                {"kilos_brutos": "100000000.00"},
            )
            # Cada caso se prueba por separado.
            for indice, cambio in enumerate(invalidos, 1):
                # Cantidades antes del rechazo.
                antes = cantidades(db)
                # Envía el cuerpo con el cambio.
                estado, _ = solicitar(
                    "POST", BASE, token_recepcion, dict(cuerpo, **cambio)
                )
                # Lo rechaza el schema.
                comprobar(f"Schema V{indice} - HTTP 422", estado == 422)
                # No deja filas ni eventos.
                comprobar(f"Schema V{indice} - sin escrituras", cantidades(db) == antes)

            # La planta no fija máximos operativos: los antiguos 500, 100 y 5.000 se aceptan.
            estado, sin_tope = solicitar(
                "POST",  # Registra la tarja.
                BASE,  # Ruta del módulo.
                token_recepcion,  # Operador de recepción.
                dict(
                    cuerpo,  # Cuerpo válido.
                    cantidad_bandejas=501,  # Antes superaba el máximo de bandejas.
                    peso_pallet_kg="101.00",  # Antes superaba el máximo de pallet.
                    kilos_brutos="5001.00",  # Antes superaba el máximo de balanza.
                ),  # Finaliza el cuerpo.
            )  # Finaliza la petición.
            # Se acepta y conserva los valores.
            comprobar(
                "Sin tope operativo - HTTP 201",
                estado == 201
                and sin_tope["cantidad_bandejas"] == 501
                and Decimal(sin_tope["peso_pallet_kg"]) == Decimal("101.00")
                and Decimal(sin_tope["kilos_brutos"]) == Decimal("5001.00"),
            )

            # Omitir la fecha utiliza hoy en Chile.
            # Copia el cuerpo base.
            sin_fecha = dict(cuerpo)
            # Quita la fecha.
            sin_fecha.pop("fecha_recepcion")
            # Registra sin fecha de recepción.
            estado, salida_hoy = solicitar("POST", BASE, token_recepcion, sin_fecha)
            # Decisión C: queda la fecha de hoy.
            comprobar(
                "Fecha - omitida usa hoy en Chile",
                estado == 201
                and salida_hoy["fecha_recepcion"] == hoy_en_chile().isoformat(),
            )

            # Dos netos válidos cercanos a INT deben acumularse en BIGINT.
            # Primera tarja cercana al máximo de INT.
            db.get(Tarja, sin_tope["id"]).kilos_netos = 2000000000
            # Segunda tarja cercana al máximo de INT.
            db.get(Tarja, salida_hoy["id"]).kilos_netos = 2000000000
            # Solo confirma el savepoint.
            db.commit()
            # Pide los acumulados del productor.
            estado, acumulados_grandes = solicitar(
                "GET",  # Consulta de solo lectura.
                f"{BASE}/pendientes?productor_id={datos['productor'].id}",  # Productor de las dos tarjas.
                token_recepcion,  # Operador de recepción.
            )  # Finaliza la petición.
            # La suma supera INT sin error.
            comprobar(
                "Pendientes - suma BIGINT sin desborde",
                estado == 200 and Decimal(acumulados_grandes["kilos_sin_procesar"]) >= 4000000000,
            )

            # Un fallo al auditar debe revertir tarja y movimiento.
            # Cantidades antes del fallo.
            antes = cantidades(db)
            # Hace fallar la auditoría dentro del service.
            with patch(
                "app.services.tarja.registrar_auditoria",
                side_effect=RuntimeError("fallo simulado de auditoría"),
            ):
                # El service debe propagar el error.
                try:
                    registrar_tarja(db, TarjaCreate(**cuerpo), recepcion)
                # Es el error esperado.
                except RuntimeError:
                    pass
                # Si no hubo error, la prueba falla.
                else:
                    comprobar("Atomicidad - el fallo fue propagado", False)
            # HU12 criterio 2: no quedó nada a medias.
            comprobar("Atomicidad - sin tarja, movimiento ni auditoría", cantidades(db) == antes)
            # El rollback del service no cerró la transacción de la prueba.
            comprobar(
                "Atomicidad - transacción externa conservada",
                externa.is_active and conexion.in_transaction(),
            )


# HU17: filtros, detalle y permisos de la consulta de tarjas.
def probar_consulta() -> None:
    # Todo lo que se crea aquí se revierte.
    with aislado() as (db, conexion, externa):
        # Crea los datos de prueba.
        datos = preparar(db)
        # Operador de recepción, que registra y consulta.
        recepcion, token = datos["actores"][RolUsuario.OPERADOR_RECEPCION]
        # Roles sin acceso a la consulta.
        _, token_gerencia = datos["actores"][RolUsuario.GERENCIA]
        _, token_proceso = datos["actores"][RolUsuario.OPERADOR_PROCESO]
        # Segundo productor, para probar ese filtro.
        otro = Productor(rut=uuid.uuid4().hex[:8] + "-1", razon_social="QA Otro productor", activo=True)
        db.add(otro)
        db.commit()
        # Fechas de recepción distintas.
        hoy = hoy_en_chile()
        ayer = hoy - timedelta(days=1)
        anteayer = hoy - timedelta(days=2)
        # Cuerpo base de las altas.
        cuerpo = cuerpo_valido(datos)

        # La API usa la sesión del escenario.
        with api_con_sesion(db):
            # Tres tarjas: dos del productor principal y una del otro.
            _, t1 = solicitar("POST", BASE, token, dict(cuerpo, fecha_recepcion=anteayer.isoformat()))
            _, t2 = solicitar("POST", BASE, token, dict(cuerpo, fecha_recepcion=ayer.isoformat()))
            _, t3 = solicitar("POST", BASE, token, dict(cuerpo, productor_id=otro.id))
            # Anula una tarja directamente, para probar el filtro de estado (HU24 aún no existe).
            db.get(Tarja, t2["id"]).estado = EstadoTarja.ANULADA
            db.commit()
            # Cantidades antes de las lecturas.
            antes = cantidades(db)

            # Ayuda: ejecuta un listado y devuelve los ids.
            def ids(consulta: str = "") -> list[int] | None:
                estado, lista = solicitar("GET", BASE + consulta, token)
                return [fila["id"] for fila in lista] if estado == 200 else None

            # Sin filtros, las más recientes primero.
            todas = ids()
            comprobar("HU17 - sin filtros incluye las tres", {t1["id"], t2["id"], t3["id"]} <= set(todas))
            comprobar("HU17 - más recientes primero", todas.index(t3["id"]) < todas.index(t2["id"]) < todas.index(t1["id"]))
            # Campos exactos de la fila del listado.
            _, lista = solicitar("GET", f"{BASE}?numero_tarja={t1['numero_tarja']}", token)
            comprobar(
                "HU17 - campos del listado",
                len(lista) == 1
                and set(lista[0]) == {"id", "numero_tarja", "fecha_recepcion", "productor_codigo", "productor_razon_social", "especie", "variedad", "cantidad_bandejas", "kilos_netos", "estado", "veces_impresa"},
            )
            # Cada filtro por separado.
            comprobar("HU17 - filtro número", ids(f"?numero_tarja={t2['numero_tarja']}") == [t2["id"]])
            comprobar("HU17 - filtro productor", ids(f"?productor_id={otro.id}") == [t3["id"]])
            comprobar("HU17 - filtro desde y hasta el mismo día", ids(f"?productor_id={datos['productor'].id}&desde={ayer}&hasta={ayer}") == [t2["id"]])
            comprobar("HU17 - filtro desde", ids(f"?productor_id={datos['productor'].id}&desde={ayer}") == [t2["id"]])
            comprobar("HU17 - filtro hasta", ids(f"?productor_id={datos['productor'].id}&hasta={anteayer}") == [t1["id"]])
            comprobar("HU17 - filtro estado", ids(f"?productor_id={datos['productor'].id}&estado=ANULADA") == [t2["id"]])
            # Los filtros se combinan.
            comprobar("HU17 - filtros combinados", ids(f"?productor_id={otro.id}&estado=ANULADA") == [])
            # Sin coincidencias responde una lista vacía.
            comprobar("HU17 - número sin coincidencias []", ids("?numero_tarja=2147483647") == [])
            # El tope limita las filas.
            with patch("app.services.tarja.MAXIMO_TARJAS_LISTADO", 1):
                comprobar("HU17 - tope de filas", ids() == [t3["id"]])
            # Filtros inválidos.
            for consulta in ("?numero_tarja=0", f"?numero_tarja={'9' * 19}", f"?productor_id={'9' * 19}", "?estado=OTRO", "?desde=ayer", f"?desde={hoy}&hasta={ayer}"):
                comprobar(f"HU17 - filtro inválido {consulta[:24]} 422", solicitar("GET", BASE + consulta, token)[0] == 422)

            # Detalle: datos completos y kilos (criterio 2).
            estado, detalle = solicitar("GET", f"{BASE}/{t1['id']}", token)
            comprobar(
                "HU17 - detalle con nombres",
                estado == 200
                and detalle["productor_razon_social"] == datos["productor"].razon_social
                and detalle["productor_codigo"] == datos["productor"].codigo
                and detalle["productor_rut"] == datos["productor"].rut
                and detalle["sistema_productivo"] == datos["sistema"].nombre
                and detalle["variedad"] == datos["variedad"].nombre
                and detalle["calidad"] == datos["calidad"].nombre
                and detalle["tipo_bandeja"] == datos["bandeja"].nombre
                and detalle["especie"].startswith("QA Especie")
                and detalle["registrada_por"] == recepcion.nombre_completo,
            )
            comprobar(
                "HU17 - detalle con pesos y promedio",
                detalle["kilos_netos"] == 920
                and Decimal(detalle["tara_kg"]) == Decimal("1.20")
                and Decimal(detalle["kg_promedio_bandeja"]) == Decimal("18.40")
                and detalle["porcentaje_calidad"] == 85
                and detalle["fecha_recepcion"] == anteayer.isoformat(),
            )
            comprobar(
                "HU17 - kilos procesados y pendientes",
                Decimal(detalle["kilos_procesados"]) == 0 and Decimal(detalle["kilos_pendientes"]) == 920,
            )
            comprobar("HU17 - detalle sin datos del usuario", "usuario_id" not in detalle and "password_hash" not in json.dumps(detalle))
            # Una tarja anulada no tiene kilos pendientes.
            _, anulada = solicitar("GET", f"{BASE}/{t2['id']}", token)
            comprobar("HU17 - anulada sin kilos pendientes", anulada["estado"] == "ANULADA" and Decimal(anulada["kilos_pendientes"]) == 0)
            # Un catálogo desactivado se sigue mostrando en las tarjas antiguas.
            db.get(Calidad, datos["calidad"].id).activo = False
            db.commit()
            _, con_inactiva = solicitar("GET", f"{BASE}/{t1['id']}", token)
            comprobar("HU17 - catálogo desactivado se sigue mostrando", con_inactiva["calidad"] == datos["calidad"].nombre)
            # Id fuera de rango.
            comprobar("HU17 - detalle id cero 422", solicitar("GET", f"{BASE}/0", token)[0] == 422)

            # Permisos del listado.
            comprobar("HU17 - sin token 401", solicitar("GET", BASE)[0] == 401)
            comprobar("HU17 - gerencia 403", solicitar("GET", BASE, token_gerencia)[0] == 403)
            comprobar("HU17 - proceso 403", solicitar("GET", BASE, token_proceso)[0] == 403)
            # Las consultas no escriben (la edición de la calidad no cuenta en estas tablas).
            comprobar("HU17 - consultas sin escrituras", cantidades(db) == antes)


# HU16: impresión, reimpresión, auditoría y permisos.
def probar_impresion() -> None:
    # Todo lo que se crea aquí se revierte.
    with aislado() as (db, conexion, externa):
        # Crea los datos de prueba.
        datos = preparar(db)
        # Operador de recepción, que registra e imprime.
        recepcion, token = datos["actores"][RolUsuario.OPERADOR_RECEPCION]
        # Administrador, también autorizado.
        admin, token_admin = datos["actores"][RolUsuario.ADMINISTRADOR]
        # Roles sin acceso.
        _, token_gerencia = datos["actores"][RolUsuario.GERENCIA]
        _, token_proceso = datos["actores"][RolUsuario.OPERADOR_PROCESO]

        # La API usa la sesión del escenario.
        with api_con_sesion(db):
            # Una tarja nueva nunca se imprimió.
            _, tarja = solicitar("POST", BASE, token, cuerpo_valido(datos))
            ruta = f"{BASE}/{tarja['id']}/imprimir"
            comprobar("HU16 - tarja nueva sin impresiones", tarja["veces_impresa"] == 0 and tarja["impresa_en"] is None)

            # Eventos de auditoría de la tarja, en orden.
            def eventos() -> list[Auditoria]:
                return list(db.scalars(select(Auditoria).where(Auditoria.tabla == "tarjas", Auditoria.registro_id == str(tarja["id"])).order_by(Auditoria.id)))

            # Permisos: nadie sin rol suma impresiones.
            comprobar("HU16 - sin token 401", solicitar("POST", ruta)[0] == 401)
            comprobar("HU16 - gerencia 403", solicitar("POST", ruta, token_gerencia)[0] == 403)
            comprobar("HU16 - proceso 403", solicitar("POST", ruta, token_proceso)[0] == 403)
            comprobar("HU16 - rechazos sin impresiones", db.get(Tarja, tarja["id"]).veces_impresa == 0 and len(eventos()) == 1)

            # Primera impresión.
            estado, primera = solicitar("POST", ruta, token)
            comprobar("HU16 - primera impresión 200", estado == 200 and primera["veces_impresa"] == 1 and primera["impresa_en"] is not None)
            # La respuesta trae lo que muestra la hoja (criterio 1).
            comprobar(
                "HU16 - datos de la hoja",
                primera["numero_tarja"] == tarja["numero_tarja"]
                and primera["productor_razon_social"] == datos["productor"].razon_social
                and primera["sistema_productivo"] == datos["sistema"].nombre
                and primera["variedad"] == datos["variedad"].nombre
                and primera["especie"].startswith("QA Especie")
                and primera["calidad"] == datos["calidad"].nombre
                and primera["tipo_bandeja"] == datos["bandeja"].nombre
                and primera["cantidad_bandejas"] == 50
                and Decimal(primera["kilos_brutos"]) == Decimal("1000")
                and primera["kilos_netos"] == 920
                and Decimal(primera["kg_promedio_bandeja"]) == Decimal("18.40")
                and primera["fecha_recepcion"] == hoy_en_chile().isoformat(),
            )
            # Queda auditada como impresión, con el actor real y el antes y el después.
            evento = eventos()[-1]
            comprobar(
                "HU16 - auditoría de la impresión",
                evento.accion == AccionAuditoria.UPDATE
                and evento.usuario_id == recepcion.id
                and evento.motivo == "Impresión"
                and json.loads(evento.valores_antes)["veces_impresa"] == 0
                and json.loads(evento.valores_despues)["veces_impresa"] == 1,
            )
            # Reimpresión (criterio 3), con otro usuario.
            estado, segunda = solicitar("POST", ruta, token_admin)
            evento = eventos()[-1]
            comprobar("HU16 - reimpresión suma", estado == 200 and segunda["veces_impresa"] == 2)
            comprobar("HU16 - reimpresión registrada", evento.motivo == "Reimpresión" and evento.usuario_id == admin.id)
            # Imprimir no cambia los datos de la tarja.
            comprobar(
                "HU16 - no cambia los datos",
                all(segunda[campo] == primera[campo] for campo in ("numero_tarja", "kilos_netos", "tara_kg", "estado", "kilos_pendientes", "fecha_hora")),
            )
            # Imprimir no mueve bandejas.
            comprobar("HU16 - no agrega movimientos", db.scalar(select(func.count()).select_from(MovimientoBandeja).where(MovimientoBandeja.tarja_id == tarja["id"])) == 1)
            # El listado informa las impresiones.
            _, lista = solicitar("GET", f"{BASE}?numero_tarja={tarja['numero_tarja']}", token)
            comprobar("HU16 - listado con veces impresa", lista[0]["veces_impresa"] == 2)
            # Solo se imprime una tarja guardada (criterio 2).
            comprobar("HU16 - tarja inexistente 404", solicitar("POST", f"{BASE}/2147483647/imprimir", token)[0] == 404)
            comprobar("HU16 - id cero 422", solicitar("POST", f"{BASE}/0/imprimir", token)[0] == 422)
            comprobar("HU16 - id mayor que un INT 422", solicitar("POST", f"{BASE}/{'9' * 19}/imprimir", token)[0] == 422)

            # Un fallo al auditar revierte el contador.
            antes = cantidades(db)
            with patch("app.services.tarja.registrar_auditoria", side_effect=RuntimeError("fallo simulado de auditoría")):
                try:
                    registrar_impresion(db, tarja["id"], recepcion)
                except RuntimeError:
                    pass
                else:
                    comprobar("HU16 - el fallo fue propagado", False)
            db.expire_all()
            comprobar("HU16 - fallo no cambia el contador", db.get(Tarja, tarja["id"]).veces_impresa == 2 and cantidades(db) == antes)

            # Una tarja anulada no se imprime.
            db.get(Tarja, tarja["id"]).estado = EstadoTarja.ANULADA
            db.commit()
            antes = cantidades(db)
            comprobar("HU16 - anulada 409", solicitar("POST", ruta, token)[0] == 409)
            db.expire_all()
            comprobar("HU16 - anulada sin cambios", db.get(Tarja, tarja["id"]).veces_impresa == 2 and cantidades(db) == antes)
            # La transacción de la prueba sigue viva.
            comprobar("HU16 - transacción externa conservada", externa.is_active and conexion.in_transaction())


# HU15: saldo de bandejas por productor y tipo de bandeja.
def probar_saldo_bandejas() -> None:
    # Todo lo que se crea aquí se revierte.
    with aislado() as (db, conexion, externa):
        # Crea los datos de prueba.
        datos = preparar(db)
        # Operador de recepción, autorizado.
        _, token = datos["actores"][RolUsuario.OPERADOR_RECEPCION]
        # Roles sin acceso.
        _, token_gerencia = datos["actores"][RolUsuario.GERENCIA]
        _, token_proceso = datos["actores"][RolUsuario.OPERADOR_PROCESO]
        # Segundo tipo de bandeja y segundo productor.
        bandeja_2 = TipoBandeja(nombre="QA Bandeja saldo", peso_tara_kg=Decimal("1.00"), activo=True)
        otro = Productor(rut=uuid.uuid4().hex[:8] + "-2", razon_social="QA Otro saldo", activo=True)
        db.add_all([bandeja_2, otro])
        db.commit()
        # Cuerpo base y rutas.
        cuerpo = cuerpo_valido(datos)
        productor_id = datos["productor"].id
        ruta = f"{BASE}/saldo-bandejas?productor_id={productor_id}"
        tipo_1 = datos["bandeja"].id

        # La API usa la sesión del escenario.
        with api_con_sesion(db):
            # Sin movimientos: lista vacía.
            comprobar("HU15 - sin movimientos []", solicitar("GET", ruta, token) == (200, []))
            # Dos tarjas del mismo tipo, una de otro tipo y una de otro productor.
            solicitar("POST", BASE, token, cuerpo)
            _, segunda = solicitar("POST", BASE, token, dict(cuerpo, cantidad_bandejas=30))
            solicitar("POST", BASE, token, dict(cuerpo, tipo_bandeja_id=bandeja_2.id, cantidad_bandejas=10))
            solicitar("POST", BASE, token, dict(cuerpo, productor_id=otro.id, cantidad_bandejas=7))
            # Cantidades antes de las lecturas.
            antes = cantidades(db)

            # Ayuda: saldo del productor, por tipo.
            def saldos() -> dict:
                _, lista = solicitar("GET", ruta, token)
                return {fila["tipo_bandeja_id"]: fila for fila in lista}

            # Suma por tipo; no mezcla tipos ni productores (criterios 1 y 3).
            actual = saldos()
            comprobar("HU15 - una fila por tipo", set(actual) == {tipo_1, bandeja_2.id})
            comprobar("HU15 - suma las entradas del tipo", actual[tipo_1]["entradas"] == 80 and actual[tipo_1]["salidas"] == 0 and actual[tipo_1]["saldo"] == 80)
            comprobar("HU15 - no mezcla tipos", actual[bandeja_2.id]["saldo"] == 10)
            comprobar("HU15 - nombre del tipo", actual[tipo_1]["tipo_bandeja"] == datos["bandeja"].nombre)
            comprobar("HU15 - campos exactos", set(actual[tipo_1]) == {"tipo_bandeja_id", "tipo_bandeja", "entradas", "salidas", "saldo"})
            comprobar(
                "HU15 - no mezcla productores",
                [f["saldo"] for f in solicitar("GET", f"{BASE}/saldo-bandejas?productor_id={otro.id}", token)[1]] == [7],
            )
            # Consultar no escribe.
            comprobar("HU15 - consulta sin escrituras", cantidades(db) == antes)

            # Una entrada anulada deja de sumar, y la fila se conserva (criterio 1 y HU24).
            movimiento = db.scalar(select(MovimientoBandeja).where(MovimientoBandeja.tarja_id == segunda["id"]))
            movimiento.anulado = True
            db.commit()
            comprobar("HU15 - entrada anulada no suma", saldos()[tipo_1]["saldo"] == 50)
            comprobar("HU15 - la fila anulada se conserva", db.get(MovimientoBandeja, movimiento.id) is not None)

            # La regla para cuando exista la guía: una salida resta y el saldo puede ser negativo (criterio 5).
            db.add(MovimientoBandeja(productor_id=productor_id, tipo_bandeja_id=bandeja_2.id, tipo=TipoMovimientoBandeja.SALIDA, cantidad=25))
            db.commit()
            fila = saldos()[bandeja_2.id]
            comprobar("HU15 - salida resta y deja saldo negativo", fila["entradas"] == 10 and fila["salidas"] == 25 and fila["saldo"] == -15)

            # Dos acumulados de INT superan el máximo de INT sin desbordar el saldo.
            db.add_all(
                [
                    # Entrada cercana al máximo de INT.
                    MovimientoBandeja(productor_id=productor_id, tipo_bandeja_id=bandeja_2.id, tipo=TipoMovimientoBandeja.ENTRADA, cantidad=2000000000),
                    # Salida cercana al máximo de INT.
                    MovimientoBandeja(productor_id=productor_id, tipo_bandeja_id=bandeja_2.id, tipo=TipoMovimientoBandeja.SALIDA, cantidad=2000000000),
                ]
            )
            # Solo confirma el savepoint.
            db.commit()
            # Lee el saldo del tipo de bandeja.
            fila = saldos()[bandeja_2.id]
            # Las sumas no desbordan y el saldo sigue correcto.
            comprobar(
                "HU15 - sumas BIGINT sin desborde",
                fila["entradas"] == 2000000010 and fila["salidas"] == 2000000025 and fila["saldo"] == -15,
            )

            # Un tipo desactivado se sigue mostrando: el productor conserva esas bandejas.
            db.get(TipoBandeja, tipo_1).activo = False
            db.commit()
            comprobar("HU15 - tipo desactivado se sigue mostrando", tipo_1 in saldos())

            # Validación y permisos.
            comprobar("HU15 - sin productor_id 422", solicitar("GET", f"{BASE}/saldo-bandejas", token)[0] == 422)
            comprobar("HU15 - productor_id cero 422", solicitar("GET", f"{BASE}/saldo-bandejas?productor_id=0", token)[0] == 422)
            comprobar("HU15 - id mayor que un INT 422", solicitar("GET", f"{BASE}/saldo-bandejas?productor_id={'9' * 19}", token)[0] == 422)
            comprobar("HU15 - sin token 401", solicitar("GET", ruta)[0] == 401)
            comprobar("HU15 - gerencia 403", solicitar("GET", ruta, token_gerencia)[0] == 403)
            comprobar("HU15 - proceso 403", solicitar("GET", ruta, token_proceso)[0] == 403)
            # La ruta no se confunde con el detalle.
            comprobar("HU15 - ruta distinta del detalle", solicitar("GET", ruta, token)[0] == 200)


# HU24: anulación de una tarja, sus bandejas, su auditoría y sus permisos.
def probar_anulacion() -> None:
    # Todo lo que se crea aquí se revierte.
    with aislado() as (db, conexion, externa):
        # Crea los datos de prueba.
        datos = preparar(db)
        # Administrador, el único que anula.
        admin, token_admin = datos["actores"][RolUsuario.ADMINISTRADOR]
        # Operador de recepción, que registra y no anula.
        recepcion, token = datos["actores"][RolUsuario.OPERADOR_RECEPCION]
        # Otros roles sin acceso.
        _, token_gerencia = datos["actores"][RolUsuario.GERENCIA]
        _, token_proceso = datos["actores"][RolUsuario.OPERADOR_PROCESO]
        # Cuerpo base y productor.
        cuerpo = cuerpo_valido(datos)
        productor_id = datos["productor"].id
        tipo = datos["bandeja"].id

        # La API usa la sesión del escenario.
        with api_con_sesion(db):
            # Dos tarjas del mismo productor.
            _, tarja = solicitar("POST", BASE, token, cuerpo)
            _, otra = solicitar("POST", BASE, token, cuerpo)
            ruta = f"{BASE}/{tarja['id']}/anular"

            # Ayuda: saldo del productor en el tipo de bandeja.
            def saldo() -> int:
                _, lista = solicitar("GET", f"{BASE}/saldo-bandejas?productor_id={productor_id}", token)
                return next(f["saldo"] for f in lista if f["tipo_bandeja_id"] == tipo)

            # Ayuda: tarjas y kilos pendientes del productor.
            def pendientes() -> tuple[int, int]:
                _, datos_p = solicitar("GET", f"{BASE}/pendientes?productor_id={productor_id}", token)
                return datos_p["tarjas_sin_procesar"], Decimal(datos_p["kilos_sin_procesar"])

            # Estado inicial: dos tarjas suman.
            comprobar("HU24 - antes: saldo y pendientes", saldo() == 100 and pendientes() == (2, 1840))

            # Criterio 1: solo el administrador.
            antes = cantidades(db)
            comprobar("HU24 - sin token 401", solicitar("POST", ruta)[0] == 401)
            comprobar("HU24 - operador de recepción 403", solicitar("POST", ruta, token)[0] == 403)
            comprobar("HU24 - gerencia 403", solicitar("POST", ruta, token_gerencia)[0] == 403)
            comprobar("HU24 - proceso 403", solicitar("POST", ruta, token_proceso)[0] == 403)
            # El rol que cuenta es el de la base, no el del JWT.
            token_obsoleto = create_access_token(recepcion.nombre_usuario, [RolUsuario.ADMINISTRADOR.value])
            comprobar("HU24 - rol obsoleto del JWT 403", solicitar("POST", ruta, token_obsoleto)[0] == 403)
            comprobar("HU24 - rechazos sin escrituras", cantidades(db) == antes and db.get(Tarja, tarja["id"]).estado == EstadoTarja.RECEPCIONADA)

            # Un fallo al auditar revierte todo (criterio 6).
            with patch("app.services.tarja.registrar_auditoria", side_effect=RuntimeError("fallo simulado de auditoría")):
                try:
                    anular_tarja(db, tarja["id"], admin)
                except RuntimeError:
                    pass
                else:
                    comprobar("HU24 - el fallo fue propagado", False)
            db.expire_all()
            movimiento = db.scalar(select(MovimientoBandeja).where(MovimientoBandeja.tarja_id == tarja["id"]))
            comprobar(
                "HU24 - fallo no deja nada a medias",
                db.get(Tarja, tarja["id"]).estado == EstadoTarja.RECEPCIONADA and movimiento.anulado is False and cantidades(db) == antes,
            )

            # Una tarja ya impresa también se anula: su número no se reutiliza.
            solicitar("POST", f"{BASE}/{tarja['id']}/imprimir", token)
            eventos_antes = len(list(db.scalars(select(Auditoria).where(Auditoria.tabla == "tarjas", Auditoria.registro_id == str(tarja["id"])))))
            filas_antes = cantidades(db)
            # Anulación válida, sin cuerpo: no se exige motivo.
            estado, anulada = solicitar("POST", ruta, token_admin)
            comprobar("HU24 - anular 200", estado == 200 and anulada["estado"] == "ANULADA")
            # Criterio 3: queda anulada y no se borra.
            comprobar(
                "HU24 - no se borra nada",
                db.get(Tarja, tarja["id"]) is not None
                and cantidades(db)[0] == filas_antes[0]
                and cantidades(db)[1] == filas_antes[1],
            )
            comprobar("HU24 - conserva su número", anulada["numero_tarja"] == tarja["numero_tarja"])
            # Criterio 4: la entrada de bandejas deja de sumar y la fila se conserva.
            db.expire_all()
            movimiento = db.scalar(select(MovimientoBandeja).where(MovimientoBandeja.tarja_id == tarja["id"]))
            comprobar("HU24 - entrada anulada", movimiento.anulado is True)
            comprobar("HU24 - el saldo baja", saldo() == 50)
            comprobar("HU24 - los pendientes bajan", pendientes() == (1, 920))
            comprobar("HU24 - sin kilos pendientes", Decimal(anulada["kilos_pendientes"]) == 0)
            # Criterio 1: la auditoría registra quién, sin motivo.
            eventos_tarja = list(db.scalars(select(Auditoria).where(Auditoria.tabla == "tarjas", Auditoria.registro_id == str(tarja["id"])).order_by(Auditoria.id)))
            evento = eventos_tarja[-1]
            comprobar(
                "HU24 - auditoría de la tarja",
                len(eventos_tarja) == eventos_antes + 1
                and evento.accion == AccionAuditoria.UPDATE
                and evento.usuario_id == admin.id
                and evento.motivo is None
                and json.loads(evento.valores_antes)["estado"] == "RECEPCIONADA"
                and json.loads(evento.valores_despues)["estado"] == "ANULADA",
            )
            evento_mov = list(db.scalars(select(Auditoria).where(Auditoria.tabla == "movimientos_bandeja", Auditoria.registro_id == str(movimiento.id)).order_by(Auditoria.id)))[-1]
            comprobar(
                "HU24 - auditoría del movimiento",
                evento_mov.accion == AccionAuditoria.UPDATE
                and evento_mov.usuario_id == admin.id
                and json.loads(evento_mov.valores_antes)["anulado"] is False
                and json.loads(evento_mov.valores_despues)["anulado"] is True,
            )
            # La otra tarja no cambia.
            comprobar("HU24 - no toca otras tarjas", db.get(Tarja, otra["id"]).estado == EstadoTarja.RECEPCIONADA)

            # Criterio 5: no se reprocesa, pero sigue en las consultas por estado.
            _, lista = solicitar("GET", f"{BASE}?productor_id={productor_id}&estado=ANULADA", token)
            comprobar("HU24 - aparece filtrando por estado", [f["id"] for f in lista] == [tarja["id"]])
            comprobar("HU24 - el detalle sigue disponible", solicitar("GET", f"{BASE}/{tarja['id']}", token)[0] == 200)
            comprobar("HU24 - no se imprime", solicitar("POST", f"{BASE}/{tarja['id']}/imprimir", token)[0] == 409)
            # Anular dos veces no agrega eventos.
            filas_antes = cantidades(db)
            comprobar("HU24 - anular de nuevo 409", solicitar("POST", ruta, token_admin)[0] == 409)
            comprobar("HU24 - segundo intento sin escrituras", cantidades(db) == filas_antes)

            # Criterio 2: con kilos en procesos no se anula.
            for estado_tarja in (EstadoTarja.PARCIAL, EstadoTarja.PROCESADA):
                db.get(Tarja, otra["id"]).estado = estado_tarja
                db.commit()
                estado_http, salida = solicitar("POST", f"{BASE}/{otra['id']}/anular", token_admin)
                db.expire_all()
                comprobar(f"HU24 - {estado_tarja.value} 409", estado_http == 409 and "procesos" in salida["detail"])
                comprobar(f"HU24 - {estado_tarja.value} sin cambios", db.get(Tarja, otra["id"]).estado == estado_tarja)

            # Criterio 3 de HU24 y criterio 3 de HU13 (R13): el número no se reutiliza.
            _, nueva = solicitar("POST", BASE, token, cuerpo)
            comprobar("HU13 - número no reutilizado tras anular", nueva["numero_tarja"] > otra["numero_tarja"] and nueva["numero_tarja"] != tarja["numero_tarja"])

            # Tarja inexistente e id fuera de rango.
            comprobar("HU24 - inexistente 404", solicitar("POST", f"{BASE}/2147483647/anular", token_admin)[0] == 404)
            comprobar("HU24 - id cero 422", solicitar("POST", f"{BASE}/0/anular", token_admin)[0] == 422)
            # DELETE no existe: nada se borra.
            comprobar("HU24 - DELETE no publicado 405", solicitar("DELETE", f"{BASE}/{tarja['id']}", token_admin)[0] == 405)
            # La transacción de la prueba sigue viva.
            comprobar("HU24 - transacción externa conservada", externa.is_active and conexion.in_transaction())


# HU20: corrige una tarja solo antes del procesamiento y conserva toda su trazabilidad.
def probar_edicion() -> None:
    # Aísla actores, catálogos, tarja y auditorías de este escenario.
    with aislado() as (db, conexion, externa):
        # Prepara referencias activas y un actor de cada perfil.
        datos = preparar(db)
        # Recupera los tokens necesarios para comprobar los permisos exactos.
        recepcion, token_recepcion = datos["actores"][RolUsuario.OPERADOR_RECEPCION]
        _, token_admin = datos["actores"][RolUsuario.ADMINISTRADOR]
        _, token_gerencia = datos["actores"][RolUsuario.GERENCIA]
        _, token_proceso = datos["actores"][RolUsuario.OPERADOR_PROCESO]
        # Parte de una recepción válida.
        cuerpo = cuerpo_valido(datos)

        # Usa la sesión aislada también en las rutas HTTP reales.
        with api_con_sesion(db):
            # Crea la tarja que se corregirá.
            _, creada = solicitar("POST", BASE, token_recepcion, cuerpo)
            # Completa el mismo contrato de alta con el motivo obligatorio de HU20.
            correccion = {**cuerpo, "kilos_brutos": "1020.00", "motivo": "Corrección de lectura de balanza"}
            # Declara la ruta una vez para todos los casos.
            ruta = f"{BASE}/{creada['id']}"
            # Los perfiles no autorizados y un motivo vacío no dejan escrituras.
            antes = cantidades(db)
            comprobar("HU20 - sin token 401", solicitar("PUT", ruta, datos=correccion)[0] == 401)
            comprobar("HU20 - gerencia 403", solicitar("PUT", ruta, token_gerencia, correccion)[0] == 403)
            comprobar("HU20 - proceso 403", solicitar("PUT", ruta, token_proceso, correccion)[0] == 403)
            comprobar("HU20 - motivo vacío 422", solicitar("PUT", ruta, token_recepcion, {**correccion, "motivo": "   "})[0] == 422)
            comprobar("HU20 - rechazos sin escrituras", cantidades(db) == antes)

            # Cambia el catálogo para demostrar que la corrección no toma una tara nueva.
            datos["bandeja"].peso_tara_kg = Decimal("3.30")
            db.commit()
            # Corrige como operador de recepción.
            estado, corregida = solicitar("PUT", ruta, token_recepcion, correccion)
            # El neto usa la tara histórica 1,20: 1020 - 50 x 1,20 - 20 = 940.
            comprobar(
                "HU20 - corrige y recalcula con tara histórica",
                estado == 200 and corregida["kilos_netos"] == 940 and Decimal(corregida["tara_kg"]) == Decimal("1.20"),
            )
            # La entrada de bandejas mantiene el saldo alineado con la tarja editada.
            movimiento = db.scalar(select(MovimientoBandeja).where(MovimientoBandeja.tarja_id == creada["id"]))
            comprobar("HU20 - conserva movimiento de bandejas", movimiento.cantidad == 50 and movimiento.anulado is False)
            # Solo la tarja cambia al corregir kilos; no se inventa una auditoría de movimiento.
            eventos = list(db.scalars(select(Auditoria).where(Auditoria.usuario_id == recepcion.id).order_by(Auditoria.id)))
            comprobar(
                "HU20 - auditoría solo de tarja sin cambio de saldo",
                eventos[-1].tabla == "tarjas"
                and eventos[-1].motivo == correccion["motivo"]
                and json.loads(eventos[-1].valores_antes)["kilos_brutos"] == "1000.00"
                and json.loads(eventos[-1].valores_despues)["kilos_brutos"] == "1020.00",
            )
            # Crea una segunda bandeja activa para comprobar una sincronización real del saldo.
            bandeja_alterna = TipoBandeja(nombre=f"QA Bandeja alterna {uuid.uuid4().hex[:8]}", peso_tara_kg=Decimal("2.00"), activo=True)
            db.add(bandeja_alterna)
            db.commit()
            # El administrador tiene el mismo permiso y puede corregir tipo, cantidad y calidad.
            estado_admin, administrada = solicitar("PUT", ruta, token_admin, {**correccion, "tipo_bandeja_id": bandeja_alterna.id, "cantidad_bandejas": 40, "porcentaje_calidad": 86, "motivo": "Corrección de bandejas y calidad"})
            db.expire_all()
            movimiento = db.scalar(select(MovimientoBandeja).where(MovimientoBandeja.tarja_id == creada["id"]))
            evento_movimiento = db.scalar(select(Auditoria).where(Auditoria.tabla == "movimientos_bandeja", Auditoria.registro_id == str(movimiento.id)).order_by(Auditoria.id.desc()))
            comprobar(
                "HU20 - administrador sincroniza y audita movimiento",
                estado_admin == 200
                and administrada["porcentaje_calidad"] == 86
                and movimiento.tipo_bandeja_id == bandeja_alterna.id
                and movimiento.cantidad == 40
                and evento_movimiento.motivo == "Corrección de bandejas y calidad"
                and json.loads(evento_movimiento.valores_antes)["cantidad"] == 50
                and json.loads(evento_movimiento.valores_despues)["cantidad"] == 40,
            )
            # PARCIAL y PROCESADA representan kilos ya comprometidos y bloquean toda edición.
            for estado_tarja in (EstadoTarja.PARCIAL, EstadoTarja.PROCESADA):
                db.get(Tarja, creada["id"]).estado = estado_tarja
                db.commit()
                estado_http, salida = solicitar("PUT", ruta, token_recepcion, correccion)
                comprobar(f"HU20 - {estado_tarja.value} bloqueada", estado_http == 409 and "procesos" in salida["detail"])
            # Una tarja anulada tampoco admite correcciones.
            db.get(Tarja, creada["id"]).estado = EstadoTarja.ANULADA
            db.commit()
            comprobar("HU20 - anulada bloqueada", solicitar("PUT", ruta, token_recepcion, correccion)[0] == 409)
            # Las rutas posteriores siguen usando la transacción externa del escenario.
            comprobar("HU20 - transacción externa conservada", externa.is_active and conexion.in_transaction())


# Ejecuta todo y compara el estado final con el inicial.
def main() -> None:
    # Un error inesperado suma una falla.
    global fallas
    # Guarda las dependencias de la aplicación.
    overrides_anteriores = dict(app.dependency_overrides)
    # Huellas iniciales, leídas en una conexión propia.
    with engine.connect() as conexion:
        # Estado de las tablas antes de empezar.
        inicio = huellas(conexion)
    # Un error inesperado no impide el informe final.
    try:
        # Cálculo de kilos netos.
        probar_calculo()
        # Secuencia entre conexiones.
        probar_secuencia_concurrente()
        # API completa.
        probar_api()
        # Consulta de tarjas (HU17).
        probar_consulta()
        # Impresión de tarjas (HU16).
        probar_impresion()
        # Saldo de bandejas (HU15).
        probar_saldo_bandejas()
        # Anulación de tarjas (HU24).
        probar_anulacion()
        # Corrección trazable de tarjas (HU20).
        probar_edicion()
    # Registra el error sin detener el informe.
    except Exception:
        # Cuenta el error como falla.
        fallas += 1
        # Identifica el error en la salida.
        print("FALLA probar_tarjas: error inesperado", flush=True)
        # Imprime el detalle.
        traceback.print_exc()
    # Restaura la aplicación en todos los casos.
    finally:
        # Quita los reemplazos.
        app.dependency_overrides.clear()
        # Repone las dependencias originales.
        app.dependency_overrides.update(overrides_anteriores)
    # Huellas finales en una conexión nueva.
    with engine.connect() as conexion:
        # Nada debe haber quedado en la base.
        comprobar("Final - tablas idénticas al inicio", huellas(conexion) == inicio)
    # Línea de resultado que se copia al acta.
    print(f"COMPROBACIONES: {comprobaciones} FALLAS: {fallas}", flush=True)
    # Con fallas, termina con error.
    if fallas:
        # Informa cuántas fallaron.
        print(f"RESULTADO: {fallas} comprobación(es) fallaron", flush=True)
        # Código de salida distinto de cero.
        raise SystemExit(1)
    # Sin fallas.
    print("RESULTADO: todas las pruebas pasaron", flush=True)


# No ejecuta nada al importar el módulo.
if __name__ == "__main__":
    main()
