"""HU08 — Pruebas reproducibles de especies y variedades.

Desde sistema/: docker compose exec -T backend python -m tests.probar_catalogos
Modalidad API: ASGI con get_db QA; la autenticación y autorización son reales.
Crea y retira exclusivamente una base QA propia; desarrollo solo se lee.
El argumento --fallo-controlado comprueba el código de salida y la limpieza.
Importar este módulo no abre conexiones ni ejecuta los escenarios.
"""

# Herramientas estándar para ejecutar solicitudes, aislar escenarios y coordinar hilos.
import argparse
import asyncio
import hashlib
import json
import re
import sys
import threading
import time
import traceback
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch
from urllib.parse import urlsplit

# Inspección de contratos y consultas SQL; los motores QA se crean solo desde main.
from pydantic import ValidationError
from sqlalchemy import create_engine, select, text, update
from sqlalchemy.dialects import mssql
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.schema import CreateTable

# La aplicación se importa sin iniciar Uvicorn ni sustituir dependencias.
from app.main import app
from app.api.routers import especies as re_, variedades as rv
from app.core.database import Base, engine, get_db
from app.core.security import create_access_token, create_refresh_token
from app.core.validators import normalizar_nombre_catalogo
from app.models.auditoria import Auditoria, AccionAuditoria
from app.models.especie import Especie
from app.models.productor import Productor
from app.models.usuario import Usuario, UsuarioRol, RolUsuario
from app.models.variedad import Variedad
from app.schemas.especie import EspecieCreate, EspecieUpdate, EspecieOut
from app.schemas.variedad import VariedadCreate, VariedadUpdate, VariedadOut
from app.services import especie as e, variedad as v

# Solo estas tablas de desarrollo se leen para acreditar conservación de contenido.
TABLAS = ("usuarios", "usuario_roles", "productores", "auditoria", "especies", "variedades")
# El nombre no se recibe desde argumentos ni variables de entorno.
PATRON_QA = r"a2d_hu08_suite_[0-9a-f]{32}"
# Estado de una ejecución; ninguna de estas variables abre recursos al importar.
qa = None
fabrica_qa = None
conteos = {}
peticiones = {}
evidencia = []
auditoria_api = []
concurrencia = []
actores_api = {}
hilos_propios = []
fallas = 0


class ComprobacionFallida(AssertionError):
    """Identifica una comprobación ya contada como fallo."""


# Registra aserciones sin convertir un error inesperado en un resultado aprobado.
def comprobar(caso, condicion, detalle=""):
    global fallas
    conteos[caso] = conteos.get(caso, 0) + 1
    if not condicion:
        fallas += 1
        print("FALLA " + caso + " — " + detalle, flush=True)
        raise ComprobacionFallida(caso + ": " + detalle)


# Conserva la excepción de preparación, prueba o limpieza y su código de fallo.
def registrar_error(etapa, error):
    global fallas
    if not isinstance(error, ComprobacionFallida):
        fallas += 1
        print("FALLA " + etapa + " — " + type(error).__name__, flush=True)
        traceback.print_exception(type(error), error, error.__traceback__)


# Serializa filas completas sin imprimir datos privados ni hashes de contraseñas.
def huellas(conexion):
    # Las peticiones confirmadas se leen con una conexión nueva ya cerrada al salir.
    if isinstance(conexion, Engine):
        with conexion.connect() as lectura:
            return huellas(lectura)
    salida = {}
    for tabla in TABLAS:
        filas = conexion.execute(text("SELECT * FROM " + tabla)).mappings().all()
        serial = sorted(json.dumps(dict(fila), sort_keys=True, ensure_ascii=True, default=str) for fila in filas)
        salida[tabla] = {
            "filas": len(filas),
            "sha256": hashlib.sha256("\n".join(serial).encode("utf-8")).hexdigest(),
        }
    return salida


# Impide dirigir la preparación o limpieza a una base arbitraria o a desarrollo.
def validar_nombre_qa(nombre, desarrollo):
    if not isinstance(nombre, str) or not re.fullmatch(PATRON_QA, nombre):
        raise ValueError("Nombre QA fuera del patrón reservado")
    if nombre.casefold() == desarrollo.casefold():
        raise ValueError("QA no puede coincidir con desarrollo")


# Restaura exactamente las dependencias previas aunque se interrumpa la batería API.
@contextmanager
def sesiones_api():
    anteriores = dict(app.dependency_overrides)
    def proveedor():
        # Cada solicitud recibe una sesión distinta y la cierra para liberar bloqueos.
        with fabrica_qa() as db:
            yield db
    app.dependency_overrides[get_db] = proveedor
    try:
        yield
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(anteriores)


# Envía solicitudes a la aplicación completa sin red ni paquetes adicionales.
async def solicitar_asgi(metodo, ruta, token=None, datos=None, cabeceras=None, error_esperado=None):
    partes = urlsplit(ruta)
    cuerpo = json.dumps(datos, ensure_ascii=False).encode("utf-8") if datos is not None else b""
    headers = [(b"host", b"qa-hu08")]
    if datos is not None:
        headers.extend([(b"content-type", b"application/json"), (b"content-length", str(len(cuerpo)).encode("ascii"))])
    if token:
        headers.append((b"authorization", ("Bearer " + token).encode("ascii")))
    headers.extend((clave.lower().encode("ascii"), valor.encode("ascii")) for clave, valor in (cabeceras or {}).items())
    scope = {
        "type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1", "method": metodo, "scheme": "http",
        "path": partes.path, "raw_path": partes.path.encode("utf-8"),
        "query_string": partes.query.encode("utf-8"), "root_path": "",
        "headers": headers, "client": ("127.0.0.1", 12345), "server": ("qa-hu08", 80),
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
    propagado = None
    try:
        await app(scope, receive, send)
    except Exception as error:
        # Solo acepta la misma excepción inducida, nunca cualquier fallo del ejecutor.
        if error is not error_esperado:
            raise
        propagado = error
    inicio = next((m for m in mensajes if m["type"] == "http.response.start"), None)
    finalizado = any(m["type"] == "http.response.body" and not m.get("more_body", False) for m in mensajes)
    if inicio is None or not finalizado:
        raise AssertionError("ASGI no produjo una respuesta completa") from propagado
    if error_esperado is not None and (propagado is not error_esperado or inicio["status"] != 500):
        raise AssertionError("El fallo inducido no produjo el 500 esperado")
    contenido = b"".join(m.get("body", b"") for m in mensajes if m["type"] == "http.response.body").decode("utf-8")
    try:
        contenido = json.loads(contenido)
    except ValueError:
        pass
    return inicio["status"], contenido, {k.decode().lower(): valor.decode() for k, valor in inicio.get("headers", [])}


# Mantiene las peticiones secuenciales y deja identificada la modalidad conservada.
def request(metodo, ruta, token=None, datos=None, cabeceras=None, error_esperado=None):
    return asyncio.run(solicitar_asgi(metodo, ruta, token, datos, cabeceras, error_esperado))


# Verifica contratos y límites sin efectuar consultas ni preparar registros.
def probar_contratos():
    for clase, base in ((EspecieCreate, {}), (VariedadCreate, {"especie_id": 1})):
        comprobar("C01", clase(**base, nombre=" \tAra\u0301ndano   ROJO\n").nombre == "Arándano ROJO")
        comprobar("C01", clase(**base, nombre=" " + "e\u0301" * 50 + " ").nombre == "é" * 50)
        for valor in (None, "", " \t\n", 12, True, [], {}, "X" * 51):
            falla("C01", ValidationError, lambda valor=valor: clase(**base, nombre=valor))
    for clase in (EspecieUpdate, VariedadUpdate):
        comprobar("C02", clase().model_dump(exclude_unset=True, exclude_none=True) == {})
        comprobar("C02", clase(nombre=None, activo=None).model_dump(exclude_unset=True, exclude_none=True) == {})
        comprobar("C02", clase(activo=False).model_dump(exclude_unset=True, exclude_none=True) == {"activo": False})
    for clase, objeto, campos in (
        (EspecieOut, Especie(id=1, nombre="Cereza", activo=True), {"id", "nombre", "activo"}),
        (VariedadOut, Variedad(id=2, especie_id=1, nombre="Bing", activo=False), {"id", "especie_id", "nombre", "activo"}),
    ):
        comprobar("C03", set(clase.model_validate(objeto).model_dump()) == campos)
        valores = {campo: getattr(objeto, campo) for campo in campos}
        comprobar("C03", clase.model_validate(SimpleNamespace(**valores, secreto="no_publicar")).model_dump() == valores)
    for modelo in (Especie, Variedad):
        sql = str(CreateTable(modelo.__table__).compile(dialect=mssql.dialect()))
        comprobar("C04", "IDENTITY" in sql and "COLLATE SQL_Latin1_General_CP1_CI_AS" in sql)
    db = Mock(spec=Session)
    db.scalar.return_value = None
    e.obtener_especie_bloqueada(db, 1)
    consulta = db.scalar.call_args.args[0]
    comprobar("C04", "WITH (UPDLOCK, HOLDLOCK)" in str(consulta.compile(dialect=mssql.dialect())))
    comprobar("C04", consulta.get_execution_options().get("populate_existing") is True and not db.commit.called and not db.rollback.called)
    for nombre in ("a2d_sm", "master", "a2d_hu08_suite_" + "g" * 32, "a2d_hu08_suite_" + "0" * 31):
        falla("C05", ValueError, lambda nombre=nombre: validar_nombre_qa(nombre, "a2d_sm"))
    propio = "a2d_hu08_suite_" + "1" * 32
    falla("C05", ValueError, lambda: validar_nombre_qa(propio, propio.upper()))
    # Una base cuyo DB_ID cambió no pertenece ya a la ejecución que quiere limpiarla.
    motor = MagicMock()
    conexion = motor.connect.return_value.__enter__.return_value
    conexion.scalar.return_value = 99
    falla("C05", RuntimeError, lambda: retirar_qa(motor, propio, "a2d_sm", 98))
    comprobar("C05", not conexion.exec_driver_sql.called, "rechazo de limpieza sin ejecutar DDL")

def snapshot(db):
    return huellas(db.connection())
# Exige el tipo de error previsto sin aceptar otras excepciones como éxito.
def falla(caso, clase, llamada):
    try:
        llamada()
    except clase as error:
        comprobar(caso, True)
        return error
    raise AssertionError(caso + ": no se produjo " + clase.__name__)
def eventos(db, tabla, identidad):
    return list(db.scalars(select(Auditoria).where(Auditoria.tabla == tabla, Auditoria.registro_id == str(identidad)).order_by(Auditoria.id)))
def auditar(caso, db, actor, tabla, identidad, accion, antes=None):
    ev = eventos(db, tabla, identidad)[-1]
    comprobar(caso, ev.accion == accion and ev.usuario_id == actor.id and ev.registro_id == str(identidad))
    posterior = json.loads(ev.valores_despues)
    comprobar(caso, set(posterior) == ({"id","nombre","activo"} if tabla == "especies" else {"id","especie_id","nombre","activo"}))
    comprobar(caso, (json.loads(ev.valores_antes) if ev.valores_antes else None) == antes)
    fecha = ev.fecha_hora.replace(tzinfo=timezone.utc)
    comprobar(caso, abs((datetime.now(timezone.utc)-fecha).total_seconds()) < 30)
    evidencia.append({"caso":caso,"tabla":tabla,"id":identidad,"accion":accion.value,"actor":actor.id,"fecha_utc":fecha.isoformat()})
    return ev
@contextmanager
def aislado():
    with qa.connect() as conexion:
        externa = conexion.begin()
        db = Session(bind=conexion, autoflush=False, join_transaction_mode="create_savepoint")
        actor = Usuario(id=str(uuid.uuid4()), nombre_usuario="qa_"+uuid.uuid4().hex, nombre_completo="Actor QA HU08", password_hash="ficticio_no_login", activo=True, roles_asignados=[UsuarioRol(rol=RolUsuario.ADMINISTRADOR)])
        db.add(actor); db.flush(); db.commit()
        try:
            yield db, actor
            comprobar("Aislamiento", externa.is_active and conexion.in_transaction())
        finally:
            db.close()
            if externa.is_active:
                externa.rollback()
        comprobar("Aislamiento", all(t["filas"] == 0 for t in huellas(conexion).values()))

def probar_servicios():
    with aislado() as (db, actor):
        padre = e.crear_especie(db, EspecieCreate(nombre="  Cereza  "), actor); pid=padre.id
        comprobar("S01", padre.activo and pid > 0 and padre.nombre == "Cereza")
        comprobar("S01", len(eventos(db,"especies",pid)) == 1)
        auditar("S01",db,actor,"especies",pid,AccionAuditoria.INSERT)
        e.actualizar_especie(db,padre,EspecieUpdate(activo=False),actor)
        antes=snapshot(db)
        falla("S02", e.EspecieDuplicadaError, lambda:e.crear_especie(db,EspecieCreate(nombre="cereza"),actor))
        comprobar("S02",snapshot(db)==antes)
        e.actualizar_especie(db,padre,EspecieUpdate(activo=True),actor)
        tildada=e.crear_especie(db,EspecieCreate(nombre="Arándano"),actor)
        simple=e.crear_especie(db,EspecieCreate(nombre="Arandano"),actor)
        comprobar("S03",tildada.id!=simple.id and tildada.nombre=="Arándano" and simple.nombre=="Arandano")
        previo=e.instantanea(padre)
        e.actualizar_especie(db,padre,EspecieUpdate(nombre="CEREZA"),actor)
        auditar("S04",db,actor,"especies",pid,AccionAuditoria.UPDATE,previo)
        antes=snapshot(db)
        falla("S04",e.EspecieDuplicadaError,lambda:e.actualizar_especie(db,padre,EspecieUpdate(nombre="arandano"),actor))
        comprobar("S04",snapshot(db)==antes)
        hija=v.crear_variedad(db,VariedadCreate(especie_id=pid,nombre="Bing"),actor); vid=hija.id
        comprobar("S07",hija.activo and hija.especie_id==pid and vid>0)
        auditar("S07",db,actor,"variedades",vid,AccionAuditoria.INSERT)
        antes=snapshot(db)
        falla("S05",e.EspecieConVariedadesActivasError,lambda:e.actualizar_especie(db,padre,EspecieUpdate(nombre="No guardar",activo=False),actor))
        comprobar("S05",snapshot(db)==antes and e.obtener_especie(db,pid).nombre=="CEREZA")
        previo=v.instantanea(hija)
        v.actualizar_variedad(db,hija,VariedadUpdate(activo=False),actor)
        auditar("S11",db,actor,"variedades",vid,AccionAuditoria.UPDATE,previo)
        e.actualizar_especie(db,padre,EspecieUpdate(activo=False),actor)
        comprobar("S06",not padre.activo and not v.obtener_variedad(db,vid).activo)
        antes=snapshot(db)
        falla("S08",e.EspecieNoEncontradaError,lambda:v.crear_variedad(db,VariedadCreate(especie_id=2147483647,nombre="Ausente"),actor))
        comprobar("S08",snapshot(db)==antes)
        falla("S08",e.EspecieInactivaError,lambda:v.crear_variedad(db,VariedadCreate(especie_id=pid,nombre="Inactiva"),actor))
        comprobar("S08",snapshot(db)==antes)
        falla("S11",e.EspecieInactivaError,lambda:v.actualizar_variedad(db,hija,VariedadUpdate(activo=True),actor))
        comprobar("S11",snapshot(db)==antes)
        v.actualizar_variedad(db,hija,VariedadUpdate(nombre="BING"),actor)
        comprobar("S12",not hija.activo and hija.nombre=="BING" and not e.obtener_especie(db,pid).activo)
        e.actualizar_especie(db,padre,EspecieUpdate(activo=True),actor)
        comprobar("S06",padre.activo and not v.obtener_variedad(db,vid).activo)
        antes=snapshot(db)
        falla("S09",v.VariedadDuplicadaError,lambda:v.crear_variedad(db,VariedadCreate(especie_id=pid,nombre="bing"),actor))
        comprobar("S09",snapshot(db)==antes)
        otra=v.crear_variedad(db,VariedadCreate(especie_id=tildada.id,nombre="Bing"),actor)
        comprobar("S09",otra.id!=vid and otra.especie_id!=pid)
        segunda=v.crear_variedad(db,VariedadCreate(especie_id=pid,nombre="Lapins"),actor)
        previo=v.instantanea(hija)
        v.actualizar_variedad(db,hija,VariedadUpdate(nombre="Bing"),actor)
        comprobar("S10",hija.id==vid and hija.especie_id==pid)
        auditar("S10",db,actor,"variedades",vid,AccionAuditoria.UPDATE,previo)
        antes=snapshot(db)
        falla("S10",v.VariedadDuplicadaError,lambda:v.actualizar_variedad(db,hija,VariedadUpdate(nombre="lapins"),actor))
        comprobar("S10",snapshot(db)==antes)
        for modulo,objeto,clase,funcion in ((e,padre,EspecieUpdate,e.actualizar_especie),(v,hija,VariedadUpdate,v.actualizar_variedad)):
            antes=snapshot(db)
            with patch.object(db,"commit",wraps=db.commit) as commits:
                for datos in (clase(),clase(nombre=None,activo=None),clase(nombre=objeto.nombre,activo=objeto.activo)):
                    funcion(db,objeto,datos,actor)
                comprobar("S13",commits.call_count==0)
            comprobar("S13",snapshot(db)==antes)
        e.actualizar_especie(db,simple,EspecieUpdate(activo=False),actor)
        comprobar("S14",{x.id for x in e.listar_especies(db)}=={pid,tildada.id,simple.id})
        comprobar("S14",{x.id for x in e.listar_especies(db,False)}=={simple.id})
        comprobar("S14",{x.id for x in e.listar_especies(db,True)}=={pid,tildada.id})
        comprobar("S14",{x.id for x in v.listar_variedades(db)}=={vid,otra.id,segunda.id})
        comprobar("S14",{x.id for x in v.listar_variedades(db,False,pid)}=={vid})
        comprobar("S14",{x.id for x in v.listar_variedades(db,True,pid)}=={segunda.id})
        comprobar("S14",v.listar_variedades(db,especie_id=2147483647)==[])
        comprobar("S14",e.obtener_especie(db,2147483647) is None and v.obtener_variedad(db,2147483647) is None)
        comprobar("S14",not e.obtener_especie(db,simple.id).activo and not v.obtener_variedad(db,vid).activo)
        # Fuerza a la restricción SQL real a resolver una duplicidad omitida en la preconsulta.
        for modulo,funcion in ((e,lambda:e.crear_especie(db,EspecieCreate(nombre="cereza"),actor)),(v,lambda:v.crear_variedad(db,VariedadCreate(especie_id=pid,nombre="bing"),actor)),(e,lambda:e.actualizar_especie(db,simple,EspecieUpdate(nombre="CEREZA"),actor)),(v,lambda:v.actualizar_variedad(db,hija,VariedadUpdate(nombre="lapins"),actor))):
            antes=snapshot(db)
            with patch.object(modulo,"_nombre_ocupado",return_value=False):
                error=falla("S16",modulo.EspecieDuplicadaError if modulo is e else modulo.VariedadDuplicadaError,funcion)
            comprobar("S16",isinstance(error.__cause__,IntegrityError) and snapshot(db)==antes)
        # Fallos antes de auditoría y después de insertar realmente su evento.
        for modulo in (e,v):
            for actualizar in (False,True):
                for despues in (False,True):
                    antes=snapshot(db); original=modulo.registrar_auditoria
                    def romper(*args,**kwargs):
                        if despues:
                            original(*args,**kwargs); args[0].flush()
                        raise RuntimeError("Fallo QA posterior" if despues else "Fallo QA auditoria")
                    with patch.object(modulo,"registrar_auditoria",side_effect=romper):
                        if modulo is e:
                            llamada=(lambda:e.actualizar_especie(db,padre,EspecieUpdate(nombre="No persistir"),actor)) if actualizar else (lambda:e.crear_especie(db,EspecieCreate(nombre="No persistir"),actor))
                        else:
                            llamada=(lambda:v.actualizar_variedad(db,segunda,VariedadUpdate(nombre="No persistir"),actor)) if actualizar else (lambda:v.crear_variedad(db,VariedadCreate(especie_id=pid,nombre="No persistir"),actor))
                        falla("S17",RuntimeError,llamada)
                    comprobar("S17",snapshot(db)==antes)
        actor_ausente=Usuario(id=str(uuid.uuid4()))
        for llamada in (lambda:e.crear_especie(db,EspecieCreate(nombre="FK QA"),actor_ausente),lambda:v.crear_variedad(db,VariedadCreate(especie_id=pid,nombre="FK QA"),actor_ausente)):
            antes=snapshot(db); falla("S17",IntegrityError,llamada); comprobar("S17",snapshot(db)==antes)
        # Falta de registros identificada en escritura y rollback de la operación.
        falla("S18",e.EspecieNoEncontradaError,lambda:e.actualizar_especie(db,Especie(id=2147483647),EspecieUpdate(nombre="Ausente"),actor))
        falla("S18",v.VariedadNoEncontradaError,lambda:v.actualizar_variedad(db,Variedad(id=2147483647,especie_id=pid),VariedadUpdate(nombre="Ausente"),actor))
        # Cambios SQL en la misma conexión conservan deliberadamente instancias ORM antiguas.
        padre=e.obtener_especie(db,pid)
        db.connection().execute(update(Especie).where(Especie.id==pid).values(nombre="Estado SQL vigente"))
        e.actualizar_especie(db,padre,EspecieUpdate(nombre="Estado posterior"),actor)
        comprobar("S18",json.loads(eventos(db,"especies",pid)[-1].valores_antes)["nombre"]=="Estado SQL vigente")
        segunda=v.obtener_variedad(db,segunda.id)
        db.connection().execute(update(Variedad).where(Variedad.id==segunda.id).values(nombre="Variedad SQL vigente"))
        v.actualizar_variedad(db,segunda,VariedadUpdate(nombre="Variedad posterior"),actor)
        comprobar("S18",json.loads(eventos(db,"variedades",segunda.id)[-1].valores_antes)["nombre"]=="Variedad SQL vigente")
        padre=e.obtener_especie(db,pid)
        db.connection().execute(update(Especie).where(Especie.id==pid).values(activo=False))
        # Confirma solo el savepoint de preparación, conservando la instancia precargada.
        with patch.object(db,"expire_on_commit",False):
            db.commit()
        antes=snapshot(db)
        falla("S18",e.EspecieInactivaError,lambda:v.crear_variedad(db,VariedadCreate(especie_id=pid,nombre="No habilitar"),actor))
        comprobar("S18",snapshot(db)==antes)
    for modulo,nombre in ((e,"uq_especies_nombre"),(v,"uq_variedades_especie_nombre")):
        for codigo in (2601,2627):
            comprobar("S15",modulo._es_nombre_duplicado(IntegrityError(None,None,Exception("23000",f"constraint '{nombre}' ({codigo})"))))
        for mensaje in (f"23000 {nombre}", f"12627 '{nombre}'", f"26270 '{nombre}'", f"2601 'pre_{nombre}'", f"2627 '{nombre}_sufijo'", f"2627 'pre-{nombre}'", f"2627 '{nombre}-sufijo'", "547 'fk_auditoria_usuario'", "2627 'otra_restriccion'", f"515 '{nombre}'"):
            comprobar("S15",not modulo._es_nombre_duplicado(IntegrityError(None,None,Exception(mensaje))))

def probar_concurrencia():
    # Preparación confirmada únicamente en QA, visible desde ambas conexiones.
    with Session(qa,autoflush=False) as db:
        actor=Usuario(id=str(uuid.uuid4()),nombre_usuario="qa_concurrente",nombre_completo="Actor concurrente QA",password_hash="ficticio_no_login",activo=True,roles_asignados=[UsuarioRol(rol=RolUsuario.ADMINISTRADOR)])
        db.add(actor);db.commit();actor_id=actor.id
    def preparar(con_hija=False):
        with Session(qa,autoflush=False) as db:
            actor=db.get(Usuario,actor_id)
            padre=e.crear_especie(db,EspecieCreate(nombre="QA "+uuid.uuid4().hex),actor);pid=padre.id;vid=None
            if con_hija:
                hija=v.crear_variedad(db,VariedadCreate(especie_id=pid,nombre="Inicial"),actor);vid=hija.id
                v.actualizar_variedad(db,hija,VariedadUpdate(activo=False),actor)
            return pid,vid
    def carrera(caso,etiqueta,pid,vid,accion_a,accion_b):
        preparados=[threading.Event(),threading.Event()]
        iniciar=[threading.Event(),threading.Event()]
        retenido=threading.Event(); liberar=threading.Event(); intentando=threading.Event()
        pids={};salidas={};commits={}
        def trabajador(i,accion):
            try:
                with Session(qa,autoflush=False,expire_on_commit=False) as db:
                    db.execute(text("SET LOCK_TIMEOUT 8000"))
                    pids[i]=db.scalar(text("SELECT @@SPID"))
                    actor=db.get(Usuario,actor_id)
                    padre=db.get(Especie,pid)
                    hija=db.get(Variedad,vid) if vid else None
                    original=db.scalar; contar_commit=db.commit;commits[i]=0
                    def confirmar():
                        commits[i]+=1
                        return contar_commit()
                    db.commit=confirmar
                    primer_bloqueo=True
                    def coordinar(consulta,*args,**kwargs):
                        nonlocal primer_bloqueo
                        bloqueo=primer_bloqueo and any("UPDLOCK" in str(h) for h in getattr(consulta,"_hints",{}).values())
                        if bloqueo:
                            primer_bloqueo=False
                            if i==1:intentando.set()
                        resultado=original(consulta,*args,**kwargs)
                        if bloqueo and i==0:
                            retenido.set()
                            if not liberar.wait(8):raise RuntimeError("No se libero el bloqueo QA")
                        return resultado
                    db.scalar=coordinar
                    preparados[i].set()
                    if not iniciar[i].wait(8):raise RuntimeError("No se inicio trabajador")
                    try:
                        accion(db,padre,hija,actor)
                        salidas[i]="ok"
                    except (e.EspecieInactivaError,e.EspecieConVariedadesActivasError) as error:
                        salidas[i]=type(error).__name__
            except Exception as error:
                salidas[i]="ERROR:"+type(error).__name__
                preparados[i].set()
        hilos=[threading.Thread(target=trabajador,args=(0,accion_a),daemon=True),threading.Thread(target=trabajador,args=(1,accion_b),daemon=True)]
        hilos_propios.extend(hilos)
        for hilo in hilos:hilo.start()
        bloqueado=False
        try:
            comprobar(caso,all(ev.wait(8) for ev in preparados),"preparacion de conexiones")
            iniciar[0].set();comprobar(caso,retenido.wait(8),"primer bloqueo adquirido")
            iniciar[1].set();comprobar(caso,intentando.wait(8),"segunda operacion iniciada")
            limite=time.monotonic()+4
            while time.monotonic()<limite:
                with qa.connect() as lectura:
                    fila=lectura.execute(text("SELECT blocking_session_id, wait_type FROM sys.dm_exec_requests WHERE session_id=:spid"),{"spid":pids[1]}).mappings().first()
                if fila and fila["blocking_session_id"]==pids[0] and (fila["wait_type"] or "").startswith("LCK_M_"):
                    bloqueado=True;break
                time.sleep(.04)
            comprobar(caso,bloqueado,"espera real de bloqueo confirmada en DMV")
        finally:
            liberar.set();iniciar[0].set();iniciar[1].set()
            for hilo in hilos:hilo.join(12)
        comprobar(caso,not any(h.is_alive() for h in hilos),"trabajadores terminaron")
        comprobar(caso,set(salidas)=={0,1} and all(not salida.startswith("ERROR") for salida in salidas.values()),str(salidas))
        comprobar(caso,pids[0]!=pids[1],"conexiones SQL independientes")
        concurrencia.append({"caso":caso,"variante":etiqueta,"especie_id":pid,"variedad_id":vid,"sesiones_sql_distintas":pids[0]!=pids[1],"bloqueo_real_observado":bloqueado,"resultados":salidas,"commits":commits})
        return salidas,commits
    for reactivar in (False,True):
        for desactivar_primero in (True,False):
            pid,vid=preparar(reactivar)
            def desactivar(db,padre,hija,actor):
                e.actualizar_especie(db,padre,EspecieUpdate(activo=False),actor)
            def habilitar(db,padre,hija,actor):
                if reactivar:v.actualizar_variedad(db,hija,VariedadUpdate(activo=True),actor)
                else:v.crear_variedad(db,VariedadCreate(especie_id=pid,nombre="Concurrente"),actor)
            a,b=(desactivar,habilitar) if desactivar_primero else (habilitar,desactivar)
            salidas,_=carrera("S19",("reactivar" if reactivar else "crear")+(" despues de desactivar" if desactivar_primero else " antes de desactivar"),pid,vid,a,b)
            comprobar("S19",salidas==({0:"ok",1:"EspecieInactivaError"} if desactivar_primero else {0:"ok",1:"EspecieConVariedadesActivasError"}))
            with Session(qa) as db:
                padre=db.get(Especie,pid)
                activas=list(db.scalars(select(Variedad).where(Variedad.especie_id==pid,Variedad.activo==True)))
                comprobar("S19",not activas or padre.activo)
                comprobar("S19",padre.activo != desactivar_primero)
    for hija in (False,True):
        for misma in (False,True):
            pid,vid=preparar(hija)
            if hija:
                # El nombre puede cambiar aunque siga inactiva.
                tabla="variedades";identidad=vid
            else:tabla="especies";identidad=pid
            with Session(qa) as db:antes=len(eventos(db,tabla,identidad))
            nombre_a="Primera "+uuid.uuid4().hex[:10]
            nombre_b=nombre_a if misma else "Segunda "+uuid.uuid4().hex[:10]
            def editar(nombre):
                def accion(db,padre,variedad,actor):
                    if hija:v.actualizar_variedad(db,variedad,VariedadUpdate(nombre=nombre),actor)
                    else:e.actualizar_especie(db,padre,EspecieUpdate(nombre=nombre),actor)
                return accion
            salidas,commits=carrera("S20",tabla+(" mismo valor" if misma else " cambio posterior"),pid,vid,editar(nombre_a),editar(nombre_b))
            comprobar("S20",salidas=={0:"ok",1:"ok"})
            comprobar("S20",commits=={0:1,1:0 if misma else 1})
            with Session(qa) as db:
                posteriores=eventos(db,tabla,identidad)
                comprobar("S20",len(posteriores)==antes+(1 if misma else 2))
                if not misma:comprobar("S20",json.loads(posteriores[-1].valores_antes)["nombre"]==nombre_a)
                comprobar("S20",json.loads(posteriores[-1].valores_despues)["nombre"]==nombre_b)

# Ejerce los contratos HTTP mediante la aplicación ASGI y las dependencias reales.
def _casos_api():
    actores={}
    with Session(qa) as db:
        for nombre,roles,activo in [
            ("admin",[RolUsuario.ADMINISTRADOR],True),
            ("multi",[RolUsuario.ADMINISTRADOR,RolUsuario.OPERADOR_RECEPCION],True),
            ("recepcion",[RolUsuario.OPERADOR_RECEPCION],True),
            ("proceso",[RolUsuario.OPERADOR_PROCESO],True),
            ("gerencia",[RolUsuario.GERENCIA],True),
            ("inactivo",[RolUsuario.ADMINISTRADOR],False),
        ]:
            u=Usuario(nombre_usuario="qa_"+nombre,nombre_completo="Actor QA "+nombre,password_hash="ficticio_no_login",activo=activo,roles_asignados=[UsuarioRol(rol=r) for r in roles])
            db.add(u);db.flush();actores[nombre]={"id":u.id,"nombre_usuario":u.nombre_usuario}
        db.commit()
        actor=db.get(Usuario,actores["admin"]["id"])
        padre=e.crear_especie(db,EspecieCreate(nombre="Semilla"),actor);pid_semilla=padre.id
        hija=v.crear_variedad(db,VariedadCreate(especie_id=padre.id,nombre="Semilla"),actor);vid_semilla=hija.id
    def req(caso,metodo,ruta,esperado,token=None,datos=None,detail=None,cabeceras=None,error_esperado=None):
        # Comprueba individualmente cada rechazo, incluidos 401/403 de las baterías.
        antes = huellas(qa) if esperado >= 400 else None
        estado,contenido,headers=request(metodo,ruta,token,datos,cabeceras,error_esperado)
        peticiones[caso]=peticiones.get(caso,0)+1
        comprobar(caso,estado==esperado,metodo+" "+ruta+" esperaba "+str(esperado)+" obtuvo "+str(estado))
        if detail is not None:comprobar(caso,contenido=={"detail":detail},"mensaje publico")
        if antes is not None:
            comprobar(caso,huellas(qa)==antes,"rechazo sin cambios ni eventos")
        return contenido,headers
    tokens={}
    with Session(qa) as db:
        for nombre,actor in actores.items():
            usuario=db.get(Usuario,actor["id"])
            tokens[nombre]=create_access_token(usuario.nombre_usuario,[rol.value for rol in usuario.roles])
    admin=tokens["admin"]
    def auds(tabla,identidad):
        with Session(qa) as db:
            return [{"accion":x.accion.value,"actor":x.usuario_id,"id":x.registro_id,"antes":json.loads(x.valores_antes) if x.valores_antes else None,"despues":json.loads(x.valores_despues),"fecha":x.fecha_hora.replace(tzinfo=timezone.utc).isoformat()} for x in db.scalars(select(Auditoria).where(Auditoria.tabla==tabla,Auditoria.registro_id==str(identidad)).order_by(Auditoria.id))]
    def escribir(caso,metodo,ruta,datos,token=None,actor=None):
        tabla="especies" if ruta.startswith("/api/v1/especies") else "variedades"
        campos={"id","nombre","activo"}|({"especie_id"} if tabla=="variedades" else set())
        anterior=None;cantidad=0
        if metodo=="PUT":
            identidad=int(ruta.rsplit("/",1)[1])
            with Session(qa) as db:
                x=db.get(Especie if tabla=="especies" else Variedad,identidad)
                anterior={k:getattr(x,k) for k in campos}
            cantidad=len(auds(tabla,identidad))
        salida,_=req(caso,metodo,ruta,201 if metodo=="POST" else 200,token or admin,datos)
        comprobar(caso,set(salida)==campos and isinstance(salida["id"],int))
        if anterior:comprobar(caso,salida["id"]==anterior["id"])
        eventos=auds(tabla,salida["id"])
        comprobar(caso,len(eventos)==cantidad+1,"incremento de auditoria")
        ultimo=eventos[-1]
        comprobar(caso,ultimo["actor"]==(actor or actores["admin"]["id"]) and ultimo["accion"]==("INSERT" if metodo=="POST" else "UPDATE") and ultimo["id"]==str(salida["id"]))
        comprobar(caso,ultimo["antes"]==anterior and ultimo["despues"]==salida)
        comprobar(caso,abs((datetime.now(timezone.utc)-datetime.fromisoformat(ultimo["fecha"])).total_seconds())<30)
        auditoria_api.append({"caso":caso,"tabla":tabla,**ultimo})
        return salida
    def rechazar(caso,metodo,ruta,estado,datos=None,token=None,detail=None,error_esperado=None):
        # req ya compara las huellas completas para cada respuesta de rechazo.
        salida,_=req(caso,metodo,ruta,estado,token or admin,datos,detail,error_esperado=error_esperado)
        return salida
    def operaciones(etiqueta):
        return [
            ("GET","/api/v1/especies",None,200),
            ("GET",f"/api/v1/especies/{pid_semilla}",None,200),
            ("POST","/api/v1/especies",{"nombre":"Permiso "+etiqueta},201),
            ("PUT",f"/api/v1/especies/{pid_semilla}",{"nombre":"Semilla "+etiqueta},200),
            ("GET","/api/v1/variedades",None,200),
            ("GET",f"/api/v1/variedades/{vid_semilla}",None,200),
            ("POST","/api/v1/variedades",{"especie_id":pid_semilla,"nombre":"Permiso "+etiqueta},201),
            ("PUT",f"/api/v1/variedades/{vid_semilla}",{"nombre":"Semilla "+etiqueta},200),
        ]
    # Las pruebas de rechazo usan siempre entradas estructuralmente válidas.
    antes=huellas(qa)
    for token in (None,"token_invalido",create_access_token(actores["admin"]["nombre_usuario"],[],timedelta(seconds=-5)),create_refresh_token(actores["admin"]["nombre_usuario"]),create_access_token("qa_inexistente",["administrador"])):
        for metodo,ruta,datos,_ in operaciones("sin permiso"):req("H01",metodo,ruta,401,token,datos)
    comprobar("H01",huellas(qa)==antes)
    for rol in ("recepcion","proceso","gerencia"):
        for metodo,ruta,datos,_ in operaciones(rol):req("H02",metodo,ruta,403,tokens[rol],datos)
    comprobar("H02",huellas(qa)==antes)
    for metodo,ruta,datos,_ in operaciones("inactivo"):req("H03",metodo,ruta,401,tokens["inactivo"],datos)
    token_falso=create_access_token(actores["recepcion"]["nombre_usuario"],["administrador"])
    for metodo,ruta,datos,_ in operaciones("JWT antiguo"):req("H03",metodo,ruta,403,token_falso,datos)
    comprobar("H03",huellas(qa)==antes)
    for etiqueta,token,actor in (("multirrol",tokens["multi"],actores["multi"]["id"]),("admin con JWT operador",create_access_token(actores["admin"]["nombre_usuario"],["operador_proceso"]),actores["admin"]["id"])):
        for metodo,ruta,datos,estado in operaciones(etiqueta):
            if metodo in ("POST","PUT"):escribir("H03",metodo,ruta,datos,token,actor)
            else:req("H03",metodo,ruta,estado,token,datos)
    padre=escribir("H08","POST","/api/v1/especies",{"nombre":"  QA   Principal  "});pid=padre["id"]
    comprobar("H08",padre["nombre"]=="QA Principal" and padre["activo"])
    hija=escribir("H08","POST","/api/v1/variedades",{"especie_id":pid,"nombre":"  Bing  "});vid=hija["id"]
    otro=escribir("H08","POST","/api/v1/especies",{"nombre":"QA Otro"});oid=otro["id"]
    # Se verifica rechazo de duplicados y conservación de nombres inactivos.
    rechazar("H09","POST","/api/v1/especies",409,{"nombre":"qa principal"},detail="Ya existe una especie con ese nombre")
    rechazar("H09","POST","/api/v1/variedades",409,{"especie_id":pid,"nombre":"bing"},detail="Ya existe una variedad con ese nombre en la especie")
    compartir=escribir("H09","POST","/api/v1/variedades",{"especie_id":oid,"nombre":"Bing"})
    comprobar("H09",compartir["id"]!=vid and compartir["especie_id"]!=pid)
    rechazar("H10","POST","/api/v1/variedades",404,{"especie_id":2147483647,"nombre":"Ausente"},detail="Especie no encontrada")
    padre=escribir("H11","PUT",f"/api/v1/especies/{pid}",{"nombre":"QA PRINCIPAL"})
    hija=escribir("H11","PUT",f"/api/v1/variedades/{vid}",{"nombre":"BING"})
    rechazar("H11","PUT",f"/api/v1/especies/{pid}",409,{"nombre":"qa otro"},detail="Ya existe una especie con ese nombre")
    otra_hija=escribir("H11","POST","/api/v1/variedades",{"especie_id":pid,"nombre":"Lapins"})
    rechazar("H11","PUT",f"/api/v1/variedades/{vid}",409,{"nombre":"lapins"},detail="Ya existe una variedad con ese nombre en la especie")
    rechazar("H12","PUT",f"/api/v1/especies/{pid}",409,{"nombre":"No guardar","activo":False},detail="No se puede desactivar una especie con variedades activas")
    hija=escribir("H13","PUT",f"/api/v1/variedades/{vid}",{"activo":False})
    escribir("H13","PUT",f"/api/v1/variedades/{otra_hija['id']}",{"activo":False})
    padre=escribir("H13","PUT",f"/api/v1/especies/{pid}",{"activo":False})
    rechazar("H09","POST","/api/v1/especies",409,{"nombre":"qa principal"},detail="Ya existe una especie con ese nombre")
    rechazar("H10","POST","/api/v1/variedades",409,{"especie_id":pid,"nombre":"Inactiva"},detail="La especie debe estar activa para habilitar una variedad")
    rechazar("H14","PUT",f"/api/v1/variedades/{vid}",409,{"activo":True},detail="La especie debe estar activa para habilitar una variedad")
    hija=escribir("H14","PUT",f"/api/v1/variedades/{vid}",{"nombre":"Bing corregida"})
    comprobar("H14",not hija["activo"] and hija["especie_id"]==pid)
    # Ambos estados están presentes en los listados reales.
    for recurso,campos in (("especies",{"id","nombre","activo"}),("variedades",{"id","especie_id","nombre","activo"})):
        filas,_=req("H04","GET","/api/v1/"+recurso,200,admin)
        comprobar("H04",len(filas)>1 and all(set(f)==campos for f in filas))
        comprobar("H04",{f["activo"] for f in filas}=={True,False})
        for filtro,valor in (("true",True),("false",False)):
            filtradas,_=req("H04","GET","/api/v1/"+recurso+"?activo="+filtro,200,admin)
            comprobar("H04",{f["id"] for f in filtradas}=={f["id"] for f in filas if f["activo"]==valor})
    filas,_=req("H05","GET",f"/api/v1/variedades?especie_id={pid}&activo=false",200,admin)
    comprobar("H05",{f["id"] for f in filas}=={vid,otra_hija["id"]})
    vacias,_=req("H05","GET","/api/v1/variedades?especie_id=2147483647",200,admin)
    comprobar("H05",vacias==[])
    for valor in ("abc","0","-1","1.5"):rechazar("H06","GET","/api/v1/variedades?especie_id="+valor,422)
    for recurso,identidad in (("especies",pid),("variedades",vid)):
        detalle,_=req("H07","GET",f"/api/v1/{recurso}/{identidad}",200,admin)
        comprobar("H07",not detalle["activo"])
        req("H07","GET",f"/api/v1/{recurso}/2147483647",404,admin,detail="Especie no encontrada" if recurso=="especies" else "Variedad no encontrada")
        req("H07","GET",f"/api/v1/{recurso}/abc",422,admin)
    padre=escribir("H13","PUT",f"/api/v1/especies/{pid}",{"activo":True})
    comprobar("H13",not request("GET",f"/api/v1/variedades/{vid}",admin)[1]["activo"])
    hija=escribir("H13","PUT",f"/api/v1/variedades/{vid}",{"activo":True})
    # Dejar una variedad inactiva bajo padre activo permite probar su nombre reservado.
    rechazar("H09","POST","/api/v1/variedades",409,{"especie_id":pid,"nombre":"lapins"},detail="Ya existe una variedad con ese nombre en la especie")
    for recurso,salida in (("especies",padre),("variedades",hija)):
        for datos in ({},{"nombre":None,"activo":None},{"nombre":salida["nombre"],"activo":salida["activo"]}):
            antes=huellas(qa)
            actual,_=req("H15","PUT",f"/api/v1/{recurso}/{salida['id']}",200,admin,datos)
            comprobar("H15",actual==salida and huellas(qa)==antes)
    rechazar("H16","PUT",f"/api/v1/variedades/{vid}",422,{"especie_id":oid})
    for recurso,datos in (("especies",{"nombre":"QA Extra"}),("variedades",{"especie_id":pid,"nombre":"QA Extra"})):
        for campo,valor in (("id",99),("activo",False),("usuario_id",actores["multi"]["id"])):
            rechazar("H16","POST","/api/v1/"+recurso,422,{**datos,campo:valor})
    for recurso,datos,identidad in (("especies",{},pid),("variedades",{"especie_id":pid},vid)):
        for nombre in ("","   ",None,12,True,[],{},"X"*51):
            rechazar("H17","POST","/api/v1/"+recurso,422,{**datos,"nombre":nombre})
        for nombre in (" ","X"*51,12):
            rechazar("H17","PUT",f"/api/v1/{recurso}/{identidad}",422,{"nombre":nombre})
    for identidad in (None,0,-1,True,"1",1.0):
        rechazar("H17","POST","/api/v1/variedades",422,{"especie_id":identidad,"nombre":"QA Tipo"})
    for ruta in ("/api/v1/especies",f"/api/v1/especies/{pid}","/api/v1/variedades",f"/api/v1/variedades/{vid}"):
        rechazar("H18","DELETE",ruta,405)
    # Las traducciones tardías se inducen solo en la aplicación QA del controlador.
    casos=[
        (re_,"crear_especie",e.EspecieDuplicadaError,"POST","/api/v1/especies",{"nombre":"QA Traducir"},409,"Ya existe una especie con ese nombre"),
        (re_,"actualizar_especie",e.EspecieDuplicadaError,"PUT",f"/api/v1/especies/{pid}",{"nombre":"QA Traducir"},409,"Ya existe una especie con ese nombre"),
        (re_,"actualizar_especie",e.EspecieNoEncontradaError,"PUT",f"/api/v1/especies/{pid}",{},404,"Especie no encontrada"),
        (re_,"actualizar_especie",e.EspecieConVariedadesActivasError,"PUT",f"/api/v1/especies/{pid}",{"activo":False},409,"No se puede desactivar una especie con variedades activas"),
    ]
    for funcion,metodo,ruta,datos in (("crear_variedad","POST","/api/v1/variedades",{"especie_id":pid,"nombre":"QA Traducir"}),("actualizar_variedad","PUT",f"/api/v1/variedades/{vid}",{"nombre":"QA Traducir"})):
        for clase,estado,mensaje in ((e.EspecieNoEncontradaError,404,"Especie no encontrada"),(e.EspecieInactivaError,409,"La especie debe estar activa para habilitar una variedad"),(v.VariedadDuplicadaError,409,"Ya existe una variedad con ese nombre en la especie")):
            casos.append((rv,funcion,clase,metodo,ruta,datos,estado,mensaje))
    casos.append((rv,"actualizar_variedad",v.VariedadNoEncontradaError,"PUT",f"/api/v1/variedades/{vid}",{},404,"Variedad no encontrada"))
    for modulo,funcion,clase,metodo,ruta,datos,estado,mensaje in casos:
        with patch.object(modulo,funcion,side_effect=clase("ODBC_SENTINELA_NO_PUBLICAR")):
            rechazar("H19",metodo,ruta,estado,datos,detail=mensaje)
    fallo=RuntimeError("ODBC_SENTINELA_NO_PUBLICAR")
    with patch.object(re_,"crear_especie",side_effect=fallo):
        respuesta=rechazar("H19","POST","/api/v1/especies",500,{"nombre":"QA Inesperado"},error_esperado=fallo)
        comprobar("H19","ODBC_SENTINELA" not in str(respuesta))
    # Rutas previas, documentación OpenAPI y CORS mediante ASGI, sin transporte de red.
    salud,_=req("H20","GET","/health",200);comprobar("H20",salud=={"status":"ok"})
    me,_=req("H20","GET","/api/v1/auth/me",200,admin);comprobar("H20",me["id"]==actores["admin"]["id"] and "password_hash" not in me)
    req("H20","GET","/api/v1/productores",200,admin)
    openapi,_=req("H20","GET","/openapi.json",200)
    for ruta in ("/api/v1/auth/login","/api/v1/auth/me","/api/v1/auth/usuarios","/api/v1/productores","/api/v1/productores/{productor_id}","/health"):
        comprobar("H20",ruta in openapi["paths"],"ruta anterior conservada")
    rutas_hu08={p:sorted(m for m in operaciones if m in {"get","post","put","delete"}) for p,operaciones in openapi["paths"].items() if p.startswith(("/api/v1/especies","/api/v1/variedades"))}
    comprobar("H20",rutas_hu08=={"/api/v1/especies":["get","post"],"/api/v1/especies/{especie_id}":["get","put"],"/api/v1/variedades":["get","post"],"/api/v1/variedades/{variedad_id}":["get","put"]})
    comprobar("H20",openapi["paths"]["/api/v1/especies"]["get"]["tags"]==["Especies"] and openapi["paths"]["/api/v1/variedades"]["get"]["tags"]==["Variedades"])
    _,headers=req("H20","OPTIONS","/api/v1/especies",200,cabeceras={"Origin":"http://localhost:5173","Access-Control-Request-Method":"GET","Access-Control-Request-Headers":"Authorization"})
    comprobar("H20",headers.get("access-control-allow-origin")== "http://localhost:5173" or headers.get("Access-Control-Allow-Origin")=="http://localhost:5173")
    comprobar("H20",get_db in app.dependency_overrides)
    actores_api.update(actores)


# Activa únicamente la dependencia de sesión QA alrededor de las peticiones.
def probar_api():
    with sesiones_api():
        _casos_api()


# Relee todos los eventos confirmados y su continuidad, no solo objetos en memoria.
def probar_historial():
    with Session(qa) as db:
        for modelo in (Especie, Variedad):
            for objeto in db.scalars(select(modelo).order_by(modelo.id)):
                historial = eventos(db, modelo.__tablename__, objeto.id)
                comprobar("A01", bool(historial), "cada registro preparado mediante servicio tiene historial")
                anterior = None
                for indice, evento in enumerate(historial):
                    comprobar("A01", evento.accion == (AccionAuditoria.INSERT if indice == 0 else AccionAuditoria.UPDATE))
                    comprobar("A01", (json.loads(evento.valores_antes) if evento.valores_antes else None) == anterior)
                    posterior = json.loads(evento.valores_despues)
                    comprobar("A01", set(posterior) == set(objeto.__table__.columns.keys()))
                    comprobar("A01", posterior["id"] == objeto.id and evento.registro_id == str(objeto.id))
                    comprobar("A01", db.get(Usuario, evento.usuario_id) is not None)
                    comprobar("A01", abs((datetime.now(timezone.utc) - evento.fecha_hora.replace(tzinfo=timezone.utc)).total_seconds()) < 300)
                    anterior = posterior
                comprobar("A01", anterior == e.instantanea(objeto), "historial termina en el estado SQL vigente")


# Elimina solo una base que esta llamada a main creó y cuyo identificador se conserva.
def retirar_qa(master, nombre, desarrollo, identificador):
    validar_nombre_qa(nombre, desarrollo)
    with master.connect() as conexion:
        actual = conexion.scalar(text("SELECT DB_ID(:nombre)"), {"nombre": nombre})
        if actual is None:
            raise RuntimeError("La base QA desapareció antes de la limpieza")
        if identificador is not None and actual != identificador:
            raise RuntimeError("La identidad de la base QA cambió; no se elimina")
        conexion.exec_driver_sql("ALTER DATABASE [" + nombre + "] SET SINGLE_USER WITH ROLLBACK IMMEDIATE")
        conexion.exec_driver_sql("DROP DATABASE [" + nombre + "]")
        if conexion.scalar(text("SELECT DB_ID(:nombre)"), {"nombre": nombre}) is not None:
            raise RuntimeError("La base QA sigue presente después de la limpieza")


# Ejecutar main es la única entrada que conecta, prepara QA o cambia dependencias.
def main() -> int:
    global qa, fabrica_qa, fallas
    parser = argparse.ArgumentParser(description="Pruebas HU08 en SQL Server QA temporal.")
    parser.add_argument("--fallo-controlado", action="store_true", help="Induce un fallo tras preparar QA y verifica su limpieza.")
    argumentos = parser.parse_args()
    if any(hilo.is_alive() for hilo in hilos_propios):
        print("FALLA: quedan trabajadores de una ejecución anterior; no se inicia otra", flush=True)
        return 1
    for coleccion in (conteos, peticiones, actores_api):
        coleccion.clear()
    for coleccion in (evidencia, auditoria_api, concurrencia, hilos_propios):
        coleccion.clear()
    fallas = 0
    qa = None
    fabrica_qa = None
    anteriores = dict(app.dependency_overrides)
    inicial = None
    master = None
    creada = False
    identificador = None
    retirada = False
    nombre = "a2d_hu08_suite_" + uuid.uuid4().hex
    desarrollo = engine.url.database
    grupos = {nombre: "No ejecutado" for nombre in ("contratos", "servicios", "concurrencia", "API ASGI", "historial")}
    try:
        if not desarrollo:
            raise RuntimeError("La conexión no identifica una base de desarrollo")
        validar_nombre_qa(nombre, desarrollo)
        with engine.connect() as conexion:
            inicial = huellas(conexion)
            revision = conexion.scalar(text("SELECT version_num FROM alembic_version"))
        print("DESARROLLO_INICIAL: " + json.dumps(inicial, sort_keys=True), flush=True)
        print("REVISION_REFERENCIA: " + str(revision), flush=True)
        master = create_engine(engine.url.set(database="master"), isolation_level="AUTOCOMMIT", connect_args={"timeout": 10})
        with master.connect() as conexion:
            if conexion.scalar(text("SELECT DB_ID(:nombre)"), {"nombre": nombre}) is not None:
                raise RuntimeError("El nombre QA ya existe; no se reutiliza")
            conexion.exec_driver_sql("CREATE DATABASE [" + nombre + "] COLLATE SQL_Latin1_General_CP1_CI_AS")
            creada = True
            identificador = conexion.scalar(text("SELECT DB_ID(:nombre)"), {"nombre": nombre})
        print("QA_CREADA: " + nombre, flush=True)
        qa = create_engine(engine.url.set(database=nombre), pool_size=8, pool_timeout=10, connect_args={"timeout": 10})
        fabrica_qa = sessionmaker(bind=qa, autoflush=False)
        with qa.connect() as conexion:
            if conexion.scalar(text("SELECT DB_NAME()")) != nombre:
                raise RuntimeError("El motor QA no está conectado a su base propia")
        Base.metadata.create_all(qa)
        if argumentos.fallo_controlado:
            raise RuntimeError("Fallo controlado después de preparar QA")
        for etiqueta, escenario in (
            ("contratos", probar_contratos),
            ("servicios", probar_servicios),
            ("concurrencia", probar_concurrencia),
            ("API ASGI", probar_api),
            ("historial", probar_historial),
        ):
            print("INICIO: " + etiqueta, flush=True)
            try:
                escenario()
                grupos[etiqueta] = "Correcto"
                print("OK GRUPO: " + etiqueta, flush=True)
            except BaseException as error:
                grupos[etiqueta] = "Fallido"
                registrar_error(etiqueta, error)
                if any(hilo.is_alive() for hilo in hilos_propios):
                    raise RuntimeError("Trabajadores QA pendientes; se interrumpe la batería") from error
    except BaseException as error:
        registrar_error("Preparación o ejecución", error)
    finally:
        # Incluso un fallo de preparación o una aserción restaura el estado de la app.
        restauradas = app.dependency_overrides == anteriores
        app.dependency_overrides.clear()
        app.dependency_overrides.update(anteriores)
        try:
            comprobar("Limpieza", restauradas and app.dependency_overrides == anteriores, "dependencias restauradas por sus contextos")
        except ComprobacionFallida:
            pass
        # Siempre libera y espera trabajadores propios antes de retirar su base.
        for hilo in hilos_propios:
            if hilo.is_alive():
                hilo.join(20)
        pendientes = any(hilo.is_alive() for hilo in hilos_propios)
        try:
            if pendientes:
                raise RuntimeError("No se elimina QA mientras existan trabajadores activos")
            if qa is not None:
                qa.dispose()
            if creada:
                retirar_qa(master, nombre, desarrollo, identificador)
                retirada = True
                print("QA_ELIMINADA: " + nombre, flush=True)
        except BaseException as error:
            registrar_error("Limpieza QA", error)
            print("QA_PENDIENTE: " + nombre, flush=True)
        finally:
            if master is not None:
                # Un fallo al cerrar este motor también debe invalidar el resultado.
                try:
                    master.dispose()
                except BaseException as error:
                    registrar_error("Cierre del motor master propio", error)
            fabrica_qa = None
            if not pendientes:
                qa = None
        try:
            if inicial is not None:
                with engine.connect() as conexion:
                    final = huellas(conexion)
                print("DESARROLLO_FINAL: " + json.dumps(final, sort_keys=True), flush=True)
                comprobar("Conservación", final == inicial, "conteos y huellas completos de desarrollo")
                print("DESARROLLO_CONSERVADO: " + json.dumps(final == inicial), flush=True)
            if creada:
                comprobar("Limpieza", retirada, "QA creada por esta ejecución fue eliminada")
        except BaseException as error:
            registrar_error("Conservación final", error)
    print("GRUPOS: " + json.dumps(grupos, ensure_ascii=False), flush=True)
    print("CASOS: " + json.dumps(conteos, sort_keys=True), flush=True)
    print("CONCURRENCIA: " + json.dumps(concurrencia, ensure_ascii=False), flush=True)
    print("PETICIONES_ASGI: " + json.dumps(peticiones, sort_keys=True), flush=True)
    print("AUDITORIA_API: " + json.dumps(auditoria_api, ensure_ascii=False), flush=True)
    print("COMPROBACIONES:", sum(conteos.values()), "FALLAS:", fallas, flush=True)
    print("RESULTADO:", "todas las pruebas pasaron" if fallas == 0 else "ejecución fallida", flush=True)
    return 1 if fallas else 0


# La importación deja las herramientas disponibles sin ejecutar el ciclo de pruebas.
if __name__ == "__main__":
    sys.exit(main())
