"""HU12-HU14: prueba reproducible del registro de tarjas de recepción.

Ejecutar desde sistema/: docker compose exec -T backend python -m tests.probar_tarjas
Todas las filas temporales quedan dentro de una transacción externa revertida.
"""

import asyncio
import hashlib
import json
import sys
import traceback
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch
from urllib.parse import urlsplit

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.database import engine, get_db
from app.core.security import create_access_token
from app.main import app
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
from app.schemas.tarja import TarjaCreate, hoy_en_chile
from app.services.auditoria import instantanea
from app.services.tarja import calcular_kilos_netos, registrar_tarja


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
BASE = "/api/v1/tarjas"
comprobaciones = 0
fallas = 0


def comprobar(nombre: str, condicion: bool) -> None:
    global comprobaciones, fallas
    comprobaciones += 1
    if not condicion:
        fallas += 1
    print(("OK    " if condicion else "FALLA ") + nombre, flush=True)


def huellas(conexion) -> dict:
    salida = {}
    for tabla in TABLAS:
        filas = conexion.execute(text("SELECT * FROM " + tabla)).mappings().all()
        serial = sorted(json.dumps(dict(fila), sort_keys=True, default=str) for fila in filas)
        salida[tabla] = (
            len(filas),
            hashlib.sha256("\n".join(serial).encode("utf-8")).hexdigest(),
        )
    return salida


@contextmanager
def aislado():
    with engine.connect() as conexion:
        externa = conexion.begin()
        db = Session(
            bind=conexion,
            autoflush=False,
            join_transaction_mode="create_savepoint",
        )
        try:
            yield db, conexion, externa
            comprobar(
                "Aislamiento - transacción externa activa",
                externa.is_active and conexion.in_transaction(),
            )
        finally:
            db.close()
            if externa.is_active:
                externa.rollback()


def crear_actor(db: Session, rol: RolUsuario) -> tuple[Usuario, str]:
    actor = Usuario(
        id=str(uuid.uuid4()),
        nombre_usuario="qa_tarjas_" + uuid.uuid4().hex[:20],
        nombre_completo="Actor QA Tarjas",
        password_hash="ficticio_no_sirve_para_login",
        activo=True,
        roles_asignados=[UsuarioRol(rol=rol)],
    )
    db.add(actor)
    db.flush()
    token = create_access_token(actor.nombre_usuario, [rol.value])
    return actor, token


async def _solicitar(
    metodo: str,
    ruta: str,
    token: str | None = None,
    datos=None,
) -> tuple[int, object]:
    partes = urlsplit(ruta)
    cuerpo = json.dumps(datos).encode("utf-8") if datos is not None else b""
    cabeceras = [(b"host", b"qa-tarjas")]
    if datos is not None:
        cabeceras += [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(cuerpo)).encode()),
        ]
    if token:
        cabeceras.append((b"authorization", ("Bearer " + token).encode()))
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
    mensajes = []
    entregado = False

    async def receive():
        nonlocal entregado
        if entregado:
            return {"type": "http.disconnect"}
        entregado = True
        return {"type": "http.request", "body": cuerpo, "more_body": False}

    async def send(mensaje):
        mensajes.append(mensaje)

    await app(scope, receive, send)
    estado = next(m["status"] for m in mensajes if m["type"] == "http.response.start")
    contenido = b"".join(
        m.get("body", b"") for m in mensajes if m["type"] == "http.response.body"
    ).decode("utf-8")
    try:
        return estado, json.loads(contenido)
    except ValueError:
        return estado, contenido


def solicitar(metodo: str, ruta: str, token: str | None = None, datos=None):
    return asyncio.run(_solicitar(metodo, ruta, token, datos))


@contextmanager
def api_con_sesion(db: Session):
    anteriores = dict(app.dependency_overrides)

    def proveedor():
        yield db

    app.dependency_overrides[get_db] = proveedor
    try:
        yield
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(anteriores)


def cantidades(db: Session) -> tuple[int, int, int]:
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


def preparar(db: Session) -> dict:
    sufijo = uuid.uuid4().hex[:8]
    actores = {rol: crear_actor(db, rol) for rol in RolUsuario}
    especie = Especie(nombre=f"QA Especie {sufijo}", activo=True)
    db.add(especie)
    db.flush()
    variedad = Variedad(
        especie_id=especie.id,
        nombre=f"QA Variedad {sufijo}",
        activo=True,
    )
    variedad_inactiva = Variedad(
        especie_id=especie.id,
        nombre=f"QA Variedad inactiva {sufijo}",
        activo=False,
    )
    productor = Productor(
        rut=uuid.uuid4().hex[:8] + "-K",
        razon_social=f"QA Productor {sufijo}",
        activo=True,
    )
    productor_inactivo = Productor(
        rut=uuid.uuid4().hex[:8] + "-0",
        razon_social=f"QA Productor inactivo {sufijo}",
        activo=False,
    )
    sistema = SistemaProductivo(nombre=f"QA Sistema {sufijo}", activo=True)
    sistema_inactivo = SistemaProductivo(
        nombre=f"QA Sistema inactivo {sufijo}", activo=False
    )
    calidad = Calidad(nombre=f"QA Calidad {sufijo}", activo=True)
    calidad_inactiva = Calidad(nombre=f"QA Calidad inactiva {sufijo}", activo=False)
    bandeja = TipoBandeja(
        nombre=f"QA Bandeja {sufijo}", peso_tara_kg=Decimal("1.20"), activo=True
    )
    bandeja_inactiva = TipoBandeja(
        nombre=f"QA Bandeja inactiva {sufijo}",
        peso_tara_kg=Decimal("1.30"),
        activo=False,
    )
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
    db.commit()
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


def cuerpo_valido(datos: dict) -> dict:
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


def probar_calculo() -> None:
    comprobar(
        "Cálculo - caso 920 kg",
        calcular_kilos_netos(Decimal("1000"), 50, Decimal("1.20"), Decimal("20"))
        == 920,
    )
    comprobar(
        "Cálculo - mitad par baja",
        calcular_kilos_netos(Decimal("916.5"), 1, Decimal("0"), Decimal("0"))
        == 916,
    )
    comprobar(
        "Cálculo - mitad impar sube",
        calcular_kilos_netos(Decimal("917.5"), 1, Decimal("0"), Decimal("0"))
        == 918,
    )


def probar_secuencia_concurrente() -> None:
    with engine.connect() as primera, engine.connect() as segunda:
        numero_1 = primera.scalar(text("SELECT NEXT VALUE FOR seq_numero_tarja"))
        numero_2 = segunda.scalar(text("SELECT NEXT VALUE FOR seq_numero_tarja"))
        comprobar(
            "HU13 - dos conexiones reciben números distintos",
            numero_1 != numero_2,
        )


def probar_api() -> None:
    with aislado() as (db, conexion, externa):
        datos = preparar(db)
        actores = datos["actores"]
        recepcion, token_recepcion = actores[RolUsuario.OPERADOR_RECEPCION]
        _, token_admin = actores[RolUsuario.ADMINISTRADOR]
        _, token_gerencia = actores[RolUsuario.GERENCIA]
        proceso, token_proceso = actores[RolUsuario.OPERADOR_PROCESO]
        cuerpo = cuerpo_valido(datos)

        with api_con_sesion(db):
            rutas = app.openapi()["paths"]
            comprobar(
                "A3 - tres rutas publicadas",
                {ruta for ruta in rutas if ruta.startswith(BASE)}
                == {BASE, BASE + "/pendientes", BASE + "/{tarja_id}"},
            )

            antes = cantidades(db)
            comprobar(
                "Permisos - sin token 401",
                solicitar("POST", BASE, datos=cuerpo)[0] == 401,
            )
            comprobar(
                "Permisos - gerencia 403",
                solicitar("POST", BASE, token_gerencia, cuerpo)[0] == 403,
            )
            comprobar(
                "Permisos - proceso 403",
                solicitar("POST", BASE, token_proceso, cuerpo)[0] == 403,
            )
            token_obsoleto = create_access_token(
                proceso.nombre_usuario,
                [RolUsuario.OPERADOR_RECEPCION.value],
            )
            comprobar(
                "Permisos - rol obsoleto del JWT 403",
                solicitar("POST", BASE, token_obsoleto, cuerpo)[0] == 403,
            )
            comprobar("Permisos - sin escrituras", cantidades(db) == antes)

            estado, salida = solicitar("POST", BASE, token_recepcion, cuerpo)
            comprobar("Alta - HTTP 201", estado == 201)
            comprobar(
                "Alta - número, neto, tara y estado",
                isinstance(salida.get("numero_tarja"), int)
                and salida.get("kilos_netos") == 920
                and Decimal(str(salida.get("tara_kg"))) == Decimal("1.20")
                and salida.get("estado") == EstadoTarja.RECEPCIONADA.value,
            )
            tarja_id = salida["id"]
            numero_1 = salida["numero_tarja"]
            movimiento = db.scalar(
                select(MovimientoBandeja).where(MovimientoBandeja.tarja_id == tarja_id)
            )
            comprobar(
                "Alta - entrada de 50 bandejas",
                movimiento is not None
                and movimiento.tipo == TipoMovimientoBandeja.ENTRADA
                and movimiento.cantidad == 50,
            )
            eventos_tarja = list(
                db.scalars(
                    select(Auditoria).where(
                        Auditoria.tabla == "tarjas",
                        Auditoria.registro_id == str(tarja_id),
                    )
                )
            )
            eventos_movimiento = list(
                db.scalars(
                    select(Auditoria).where(
                        Auditoria.tabla == "movimientos_bandeja",
                        Auditoria.registro_id == str(movimiento.id),
                    )
                )
            )
            comprobar(
                "Alta - dos auditorías INSERT con actor real",
                len(eventos_tarja) == len(eventos_movimiento) == 1
                and eventos_tarja[0].accion == AccionAuditoria.INSERT
                and eventos_movimiento[0].accion == AccionAuditoria.INSERT
                and eventos_tarja[0].usuario_id == recepcion.id
                and eventos_movimiento[0].usuario_id == recepcion.id,
            )
            comprobar(
                "Alta - instantánea completa de la tarja",
                instantanea_auditada_coincide(
                    eventos_tarja[0], db.get(Tarja, tarja_id)
                ),
            )
            comprobar(
                "Alta - instantánea completa del movimiento",
                instantanea_auditada_coincide(eventos_movimiento[0], movimiento),
            )

            estado, segunda = solicitar("POST", BASE, token_admin, cuerpo)
            comprobar(
                "HU13 - dos altas tienen números crecientes",
                estado == 201 and segunda["numero_tarja"] > numero_1,
            )

            estado, detalle = solicitar("GET", f"{BASE}/{tarja_id}", token_recepcion)
            comprobar("Detalle - tarja existente 200", estado == 200 and detalle["id"] == tarja_id)
            comprobar(
                "Detalle - inexistente 404",
                solicitar("GET", f"{BASE}/999999999", token_recepcion)[0] == 404,
            )

            primera = db.get(Tarja, tarja_id)
            segunda_db = db.get(Tarja, segunda["id"])
            primera.estado = EstadoTarja.PARCIAL
            segunda_db.estado = EstadoTarja.PROCESADA
            db.commit()
            estado, pendientes = solicitar(
                "GET",
                f"{BASE}/pendientes?productor_id={datos['productor'].id}",
                token_recepcion,
            )
            comprobar(
                "Pendientes - solo RECEPCIONADA y PARCIAL",
                estado == 200
                and pendientes["tarjas_sin_procesar"] == 1
                and pendientes["kilos_sin_procesar"] == 920,
            )
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
            for campo, valor in campos_invalidos:
                antes = cantidades(db)
                estado, _ = solicitar(
                    "POST", BASE, token_recepcion, dict(cuerpo, **{campo: valor})
                )
                comprobar(f"Catálogo - {campo} rechazado 400", estado == 400)
                comprobar(f"Catálogo - {campo} sin escrituras", cantidades(db) == antes)

            # Neto cero o negativo se rechaza por negocio, no por el schema.
            for etiqueta, kilos in (("cero", "80.00"), ("negativo", "79.00")):
                antes = cantidades(db)
                estado, _ = solicitar(
                    "POST",
                    BASE,
                    token_recepcion,
                    dict(cuerpo, kilos_brutos=kilos),
                )
                comprobar(f"Neto {etiqueta} - HTTP 400", estado == 400)
                comprobar(
                    f"Neto {etiqueta} - sin escrituras",
                    cantidades(db) == antes,
                )

            manana = (hoy_en_chile() + timedelta(days=1)).isoformat()
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
            for indice, cambio in enumerate(invalidos, 1):
                antes = cantidades(db)
                estado, _ = solicitar(
                    "POST", BASE, token_recepcion, dict(cuerpo, **cambio)
                )
                comprobar(f"Schema V{indice} - HTTP 422", estado == 422)
                comprobar(f"Schema V{indice} - sin escrituras", cantidades(db) == antes)

            # Omitir la fecha utiliza hoy en Chile.
            sin_fecha = dict(cuerpo)
            sin_fecha.pop("fecha_recepcion")
            estado, salida_hoy = solicitar("POST", BASE, token_recepcion, sin_fecha)
            comprobar(
                "Fecha - omitida usa hoy en Chile",
                estado == 201
                and salida_hoy["fecha_recepcion"] == hoy_en_chile().isoformat(),
            )

            # Un fallo al auditar debe revertir tarja y movimiento.
            antes = cantidades(db)
            with patch(
                "app.services.tarja.registrar_auditoria",
                side_effect=RuntimeError("fallo simulado de auditoría"),
            ):
                try:
                    registrar_tarja(db, TarjaCreate(**cuerpo), recepcion)
                except RuntimeError:
                    pass
                else:
                    comprobar("Atomicidad - el fallo fue propagado", False)
            comprobar("Atomicidad - sin tarja, movimiento ni auditoría", cantidades(db) == antes)
            comprobar(
                "Atomicidad - transacción externa conservada",
                externa.is_active and conexion.in_transaction(),
            )


def main() -> None:
    global fallas
    overrides_anteriores = dict(app.dependency_overrides)
    with engine.connect() as conexion:
        inicio = huellas(conexion)
    try:
        probar_calculo()
        probar_secuencia_concurrente()
        probar_api()
    except Exception:
        fallas += 1
        print("FALLA probar_tarjas: error inesperado", flush=True)
        traceback.print_exc()
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(overrides_anteriores)
    with engine.connect() as conexion:
        comprobar("Final - tablas idénticas al inicio", huellas(conexion) == inicio)
    print(f"COMPROBACIONES: {comprobaciones} FALLAS: {fallas}", flush=True)
    if fallas:
        print(f"RESULTADO: {fallas} comprobación(es) fallaron", flush=True)
        raise SystemExit(1)
    print("RESULTADO: todas las pruebas pasaron", flush=True)


if __name__ == "__main__":
    main()
