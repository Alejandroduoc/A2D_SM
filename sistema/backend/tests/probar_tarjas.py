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
from app.services.tarja import calcular_kilos_netos, registrar_tarja


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
            # El módulo publica exactamente tres rutas.
            comprobar(
                "A3 - tres rutas publicadas",
                {ruta for ruta in rutas if ruta.startswith(BASE)}
                == {BASE, BASE + "/pendientes", BASE + "/{tarja_id}"},
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
                and pendientes["kilos_sin_procesar"] == 920,
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
            # Campos que el cliente no envía y valores fuera de rango.
            invalidos = (
                {"numero_tarja": 99},
                {"kilos_netos": 1},
                {"estado": "RECEPCIONADA"},
                {"porcentaje_calidad": 101},
                {"porcentaje_calidad": -1},
                {"cantidad_bandejas": 0},
                {"fecha_recepcion": manana},
                {"peso_pallet_kg": "-1"},
                {"peso_pallet_kg": "101"},
                {"kilos_brutos": "5001"},
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
