"""Pruebas reproducibles de las mejoras de seguridad del 2026-10-25.

Ejecutar desde sistema/: docker compose exec -T backend python -m tests.probar_seguridad
Cubre: límite de intentos de login, tiempo igual para usuarios inexistentes,
largo de contraseñas, /auth/refresh, /auth/me/password, auditoría de usuarios,
validación de productores, /docs desactivable y CORS sin credenciales.
Cada escenario corre en una transacción externa que siempre se revierte: no se
borra ninguna fila para limpiar. Importar este módulo no ejecuta pruebas.
"""

# Ejecuta solicitudes ASGI en memoria sin instalar un cliente HTTP.
import asyncio
# Calcula huellas del contenido de las tablas sin imprimir sus datos.
import hashlib
# Serializa solicitudes y lee respuestas y valores de auditoría.
import json
# Lee variables de entorno para lanzar el subproceso de /docs.
import os
# Comprueba MOSTRAR_DOCS=false en un proceso aparte (la configuración se lee al importar).
import subprocess
# Devuelve un código de salida distinto de cero si algo falla.
import sys
# Muestra la ubicación de errores inesperados sin contarlos como aprobados.
import traceback
# Genera nombres ficticios que no chocan con datos existentes.
import uuid
# Administra la apertura y la limpieza de cada escenario aislado.
from contextlib import contextmanager
# Arma un token vencido a mano.
from datetime import datetime, timedelta, timezone
# Cuenta las llamadas a verify_password sin cambiar su resultado.
from unittest.mock import patch
# Separa la ruta y la query string al armar la solicitud ASGI; urlencode arma el formulario de /docs.
from urllib.parse import urlencode, urlsplit

# Firma tokens de prueba con otra clave o ya vencidos.
import jwt
# Consultas de verificación y lectura completa de tablas.
from sqlalchemy import select, text
# Sesión ligada a la conexión que controla la prueba.
from sqlalchemy.orm import Session

# Aplicación completa: autenticación, roles, routers y servicios reales.
from app.main import app
# Router de autenticación, para observar verify_password.
from app.api.routers import auth as router_auth
# Configuración vigente (clave, algoritmo, límites).
from app.core.config import settings
# Motor de desarrollo y dependencia de sesión que se reemplaza durante HTTP.
from app.core.database import engine, get_db
# Contador de intentos de login.
from app.core.limite_login import limite_login
# Tokens y hashes reales.
from app.core.security import HASH_FICTICIO, create_access_token, create_refresh_token, hash_password
# Modelos que se verifican.
from app.models.auditoria import Auditoria
from app.models.productor import Productor
from app.models.usuario import RolUsuario, Usuario, UsuarioRol

# Tablas cuyo contenido debe quedar idéntico al terminar.
TABLAS = ("usuarios", "usuario_roles", "auditoria", "productores")
# Contraseña ficticia de los actores temporales (solo existe dentro del rollback).
CLAVE = "Clave-QA-2026!"

# Contadores globales de la ejecución.
comprobaciones = 0
fallas = 0


# Registra una comprobación; solo imprime las que fallan.
def comprobar(nombre: str, condicion: bool) -> None:
    global comprobaciones, fallas
    comprobaciones += 1
    if not condicion:
        fallas += 1
        print("FALLA " + nombre, flush=True)


# Calcula filas y huella SHA-256 de cada tabla (sin imprimir su contenido).
def huellas(conexion) -> dict:
    salida = {}
    for tabla in TABLAS:
        filas = conexion.execute(text("SELECT * FROM " + tabla)).mappings().all()
        serial = sorted(json.dumps(dict(f), sort_keys=True, default=str) for f in filas)
        salida[tabla] = (len(filas), hashlib.sha256("\n".join(serial).encode("utf-8")).hexdigest())
    return salida


# Abre un escenario aislado: todo lo que pase dentro se revierte al salir.
@contextmanager
def aislado():
    # Cada escenario empieza sin intentos fallidos acumulados.
    limite_login.reiniciar()
    with engine.connect() as conexion:
        # Transacción externa que nunca se confirma.
        externa = conexion.begin()
        # Los commit de los servicios se convierten en savepoints de esta transacción.
        db = Session(bind=conexion, autoflush=False, join_transaction_mode="create_savepoint")
        # Todas las peticiones HTTP usan esta misma sesión.
        anteriores = dict(app.dependency_overrides)

        def proveedor():
            yield db

        app.dependency_overrides[get_db] = proveedor
        try:
            yield db
            comprobar("Aislamiento — transacción externa activa", externa.is_active)
        finally:
            # Restaura la app, cierra la sesión y revierte todo.
            app.dependency_overrides.clear()
            app.dependency_overrides.update(anteriores)
            db.close()
            if externa.is_active:
                externa.rollback()
            limite_login.reiniciar()


# Crea un usuario temporal con contraseña real y los roles indicados.
def crear_actor(db: Session, *roles: RolUsuario, activo: bool = True) -> Usuario:
    actor = Usuario(
        id=str(uuid.uuid4()),  # Id conocido antes del flush.
        nombre_usuario="qa_seg_" + uuid.uuid4().hex[:20],  # Respeta el límite de 50 caracteres.
        nombre_completo="Actor QA Seguridad",  # Nombre inventado.
        password_hash=hash_password(CLAVE),  # Permite probar el login real.
        activo=activo,  # Permite probar cuentas desactivadas.
        roles_asignados=[UsuarioRol(rol=rol) for rol in roles],  # Roles del escenario.
    )  # Finaliza la preparación del actor.
    db.add(actor)
    db.commit()
    return actor


# Token de acceso válido para un actor.
def token_de(actor: Usuario) -> str:
    return create_access_token(actor.nombre_usuario, [])


# Envía una solicitud a la aplicación en memoria y devuelve estado, cuerpo y cabeceras.
async def _solicitar(metodo, ruta, token, datos, ip, cabeceras_extra):
    partes = urlsplit(ruta)
    cuerpo = json.dumps(datos).encode("utf-8") if datos is not None else b""
    cabeceras = [(b"host", b"qa-seguridad")]
    if datos is not None:
        cabeceras += [(b"content-type", b"application/json"), (b"content-length", str(len(cuerpo)).encode())]
    if token:
        cabeceras.append((b"authorization", ("Bearer " + token).encode()))
    for nombre, valor in (cabeceras_extra or {}).items():
        cabeceras.append((nombre.lower().encode(), valor.encode()))
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": metodo, "scheme": "http", "path": partes.path,
        "raw_path": partes.path.encode(), "query_string": partes.query.encode(),
        "root_path": "", "headers": cabeceras, "client": (ip, 1), "server": ("qa-seguridad", 80),
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
    inicio = next(m for m in mensajes if m["type"] == "http.response.start")
    respuesta_cabeceras = {k.decode().lower(): v.decode() for k, v in inicio.get("headers", [])}
    texto = b"".join(m.get("body", b"") for m in mensajes if m["type"] == "http.response.body").decode("utf-8")
    try:
        return inicio["status"], json.loads(texto), respuesta_cabeceras
    except ValueError:
        return inicio["status"], texto, respuesta_cabeceras


# Versión síncrona del envío.
def solicitar(metodo, ruta, token=None, datos=None, ip="10.0.0.1", cabeceras=None):
    return asyncio.run(_solicitar(metodo, ruta, token, datos, ip, cabeceras))


# Atajo para el login.
def login(nombre, password, ip="10.0.0.1"):
    return solicitar("POST", "/api/v1/auth/login", datos={"nombre_usuario": nombre, "password": password}, ip=ip)


# Login como lo envía el botón Authorize de /docs: formulario (username, password) a /auth/token.
async def _login_formulario(nombre, password, ip):
    # Cuerpo application/x-www-form-urlencoded, igual que Swagger UI.
    cuerpo = urlencode({"grant_type": "password", "username": nombre, "password": password}).encode()
    # Cabeceras de un formulario HTTP normal.
    cabeceras = [(b"host", b"qa-seguridad"), (b"content-type", b"application/x-www-form-urlencoded"), (b"content-length", str(len(cuerpo)).encode())]
    # Descripción ASGI de la solicitud.
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",  # Interfaz utilizada.
        "method": "POST", "scheme": "http", "path": "/api/v1/auth/token",  # Ruta que usa /docs.
        "raw_path": b"/api/v1/auth/token", "query_string": b"", "root_path": "",  # Sin parámetros en la URL.
        "headers": cabeceras, "client": (ip, 1), "server": ("qa-seguridad", 80),  # Contexto HTTP.
    }  # Finaliza la descripción de la solicitud.
    # Mensajes que devuelve la aplicación.
    mensajes = []
    # Controla que el cuerpo se entregue una sola vez.
    entregado = False

    # Entrega el formulario una sola vez.
    async def receive():
        nonlocal entregado
        # La segunda lectura indica que el cliente terminó.
        if entregado:
            return {"type": "http.disconnect"}
        # Marca la única entrega.
        entregado = True
        # Entrega el formulario completo.
        return {"type": "http.request", "body": cuerpo, "more_body": False}

    # Guarda cada mensaje de respuesta.
    async def send(mensaje):
        mensajes.append(mensaje)

    # Ejecuta la aplicación real.
    await app(scope, receive, send)
    # Extrae el código HTTP.
    estado = next(m["status"] for m in mensajes if m["type"] == "http.response.start")
    # Une el cuerpo de la respuesta.
    texto = b"".join(m.get("body", b"") for m in mensajes if m["type"] == "http.response.body").decode("utf-8")
    # Devuelve JSON cuando la respuesta lo es.
    try:
        return estado, json.loads(texto)
    except ValueError:
        return estado, texto


# Versión síncrona del login por formulario.
def login_formulario(nombre, password, ip="10.0.0.1"):
    return asyncio.run(_login_formulario(nombre, password, ip))


# Eventos de auditoría de un registro, en orden.
def eventos(db: Session, tabla: str, registro_id) -> list[Auditoria]:
    consulta = select(Auditoria).where(Auditoria.tabla == tabla, Auditoria.registro_id == str(registro_id)).order_by(Auditoria.id)
    return list(db.scalars(consulta))


# Comprueba que ningún evento guardó el hash ni una contraseña.
def sin_secretos(lista: list[Auditoria], *claves: str) -> bool:
    for evento in lista:
        texto = (evento.valores_antes or "") + (evento.valores_despues or "") + (evento.motivo or "")
        if "password_hash" in texto or "$2b$" in texto or any(clave in texto for clave in claves):
            return False
    return True


# Genera un RUT válido con cuerpo aleatorio (Módulo 11).
def rut_valido() -> str:
    cuerpo = str(uuid.uuid4().int % 80_000_000 + 10_000_000)
    suma, multiplicador = 0, 2
    for digito in reversed(cuerpo):
        suma += int(digito) * multiplicador
        multiplicador = multiplicador + 1 if multiplicador < 7 else 2
    resto = 11 - suma % 11
    dv = "0" if resto == 11 else "K" if resto == 10 else str(resto)
    return cuerpo + "-" + dv


# S01–S03: login correcto, mensaje único y bcrypt también para usuarios inexistentes.
def probar_login():
    with aislado() as db:
        actor = crear_actor(db, RolUsuario.OPERADOR_RECEPCION)
        inactivo = crear_actor(db, RolUsuario.ADMINISTRADOR, activo=False)
        estado, cuerpo, _ = login(actor.nombre_usuario, CLAVE)
        comprobar("S01 — login correcto 200", estado == 200 and {"access_token", "refresh_token"} <= set(cuerpo))
        comprobar("S01 — tipos de token", jwt.decode(cuerpo["refresh_token"], settings.secret_key, algorithms=[settings.algorithm])["type"] == "refresh")
        respuestas = [login(actor.nombre_usuario, "incorrecta"), login("qa_no_existe_" + uuid.uuid4().hex[:10], CLAVE), login(inactivo.nombre_usuario, CLAVE)]
        comprobar("S02 — 401 con el mismo mensaje en los tres casos", all(r[0] == 401 for r in respuestas) and len({r[1]["detail"] for r in respuestas}) == 1)
        # Cuenta las comparaciones bcrypt y qué hash se usó.
        llamadas = []
        original = router_auth.verify_password

        def espia(password, hashed):
            llamadas.append(hashed)
            return original(password, hashed)

        with patch.object(router_auth, "verify_password", side_effect=espia):
            login("qa_no_existe_" + uuid.uuid4().hex[:10], "x")
            login(inactivo.nombre_usuario, "x")
        comprobar("S03 — inexistente compara contra HASH_FICTICIO", llamadas[:1] == [HASH_FICTICIO])
        comprobar("S03 — inactivo también ejecuta bcrypt", len(llamadas) == 2)


# S04–S05: bloqueo por usuario y por IP.
def probar_limite():
    with aislado() as db:
        actor = crear_actor(db, RolUsuario.GERENCIA)
        otro = crear_actor(db, RolUsuario.GERENCIA)
        # 4 fallos + éxito reinicia el contador del usuario.
        for _ in range(4):
            login(actor.nombre_usuario, "mala")
        comprobar("S04 — éxito antes del límite", login(actor.nombre_usuario, CLAVE)[0] == 200)
        for _ in range(4):
            login(actor.nombre_usuario, "mala")
        comprobar("S04 — el éxito reinició el contador", login(actor.nombre_usuario, "mala")[0] == 401)
        # Ese fue el 5.º fallo seguido: ahora queda bloqueado aun con la clave correcta.
        estado, cuerpo, cabeceras = login(actor.nombre_usuario.upper(), CLAVE)
        comprobar("S04 — bloqueo 429 (sin distinguir mayúsculas)", estado == 429 and "Demasiados intentos" in cuerpo["detail"])
        comprobar("S04 — Retry-After presente", int(cabeceras.get("retry-after", "0")) > 0)
        comprobar("S04 — otro usuario de la misma IP no queda bloqueado", login(otro.nombre_usuario, CLAVE)[0] == 200)
        comprobar("S04 — reiniciar desbloquea", (limite_login.reiniciar(), login(actor.nombre_usuario, CLAVE))[1][0] == 200)
        # Límite por IP: muchos usuarios distintos desde la misma dirección.
        for indice in range(settings.login_max_intentos_ip):
            login(f"qa_ip_{indice}_{uuid.uuid4().hex[:6]}", "mala", ip="10.9.9.9")
        comprobar("S05 — IP bloqueada", login(otro.nombre_usuario, CLAVE, ip="10.9.9.9")[0] == 429)
        comprobar("S05 — otra IP sigue funcionando", login(otro.nombre_usuario, CLAVE, ip="10.9.9.8")[0] == 200)


# S16: el botón Authorize de /docs usa /auth/token (formulario) con las mismas reglas que /auth/login.
def probar_login_docs():
    with aislado() as db:
        # Actores temporales: uno activo y uno desactivado.
        actor = crear_actor(db, RolUsuario.ADMINISTRADOR)
        inactivo = crear_actor(db, RolUsuario.ADMINISTRADOR, activo=False)
        # El esquema de seguridad de /docs apunta a /auth/token, y esa ruta no se lista en /docs.
        esquema = app.openapi()["components"]["securitySchemes"]["OAuth2PasswordBearer"]
        comprobar("S16 — Authorize de /docs apunta a /auth/token", esquema["flows"]["password"]["tokenUrl"] == "/api/v1/auth/token")
        comprobar("S16 — /auth/token no aparece en /docs", "/api/v1/auth/token" not in app.openapi()["paths"])
        # Credenciales correctas: entrega tokens de tipo bearer, como espera Swagger UI.
        estado, cuerpo = login_formulario(actor.nombre_usuario, CLAVE)
        comprobar("S16 — formulario correcto 200 con token bearer", estado == 200 and cuerpo.get("token_type") == "bearer" and "access_token" in cuerpo)
        # El token entregado sirve para una ruta protegida.
        comprobar("S16 — el token del formulario sirve en /auth/me", solicitar("GET", "/api/v1/auth/me", token=cuerpo.get("access_token"))[0] == 200)
        # Clave incorrecta, usuario inexistente o desactivado: 401 con el mismo mensaje que /auth/login.
        respuestas = [login_formulario(actor.nombre_usuario, "incorrecta"), login_formulario("qa_no_existe_" + uuid.uuid4().hex[:10], CLAVE), login_formulario(inactivo.nombre_usuario, CLAVE)]
        mensaje_json = login(actor.nombre_usuario, "incorrecta")[1]["detail"]
        comprobar("S16 — 401 con el mismo mensaje que /auth/login", all(r[0] == 401 and r[1]["detail"] == mensaje_json for r in respuestas))
        # Un nombre vacío se rechaza sin comparar contraseñas.
        comprobar("S16 — nombre vacío 422", login_formulario("", CLAVE)[0] == 422)
        # El límite de intentos es el mismo: los fallos por formulario bloquean también el login en JSON.
        limite_login.reiniciar()
        for _ in range(settings.login_max_intentos):
            login_formulario(actor.nombre_usuario, "mala")
        comprobar("S16 — 5 fallos por formulario bloquean (429)", login_formulario(actor.nombre_usuario, CLAVE)[0] == 429)
        comprobar("S16 — el bloqueo también aplica a /auth/login", login(actor.nombre_usuario, CLAVE)[0] == 429)
        limite_login.reiniciar()
        # Sin /docs publicado (producción), la ruta no existe para el cliente.
        with patch.object(router_auth.settings, "mostrar_docs", False):
            comprobar("S16 — sin /docs responde 404", login_formulario(actor.nombre_usuario, CLAVE)[0] == 404)


# S06: largos de contraseña y campos extra.
def probar_largos():
    with aislado() as db:
        admin = crear_actor(db, RolUsuario.ADMINISTRADOR)
        t = token_de(admin)
        comprobar("S06 — login con contraseña de 129 caracteres 422", login(admin.nombre_usuario, "a" * 129)[0] == 422)
        comprobar("S06 — login con nombre de 51 caracteres 422", login("a" * 51, CLAVE)[0] == 422)
        base = {"nombre_completo": "Usuario QA", "roles": ["gerencia"]}
        casos = {"7 caracteres": "a" * 7, "73 bytes": "a" * 73, "37 eñes = 74 bytes": "ñ" * 37}
        for nombre, clave in casos.items():
            datos = dict(base, nombre_usuario="qa_l_" + uuid.uuid4().hex[:10], password=clave)
            comprobar("S06 — alta con " + nombre + " 422", solicitar("POST", "/api/v1/auth/usuarios", t, datos)[0] == 422)
        datos = dict(base, nombre_usuario="qa_l_" + uuid.uuid4().hex[:10], password="a" * 72)
        comprobar("S06 — alta con 72 bytes 201", solicitar("POST", "/api/v1/auth/usuarios", t, datos)[0] == 201)
        datos = dict(base, nombre_usuario="qa_l_" + uuid.uuid4().hex[:10], password=CLAVE, activo=False)
        comprobar("S06 — alta con campo extra 422", solicitar("POST", "/api/v1/auth/usuarios", t, datos)[0] == 422)


# S07–S08: renovación de sesión y tokens manipulados.
def probar_refresh():
    with aislado() as db:
        actor = crear_actor(db, RolUsuario.OPERADOR_PROCESO)
        ruta = "/api/v1/auth/refresh"
        estado, cuerpo, _ = solicitar("POST", ruta, datos={"refresh_token": create_refresh_token(actor.nombre_usuario)})
        comprobar("S07 — refresh válido entrega tokens nuevos", estado == 200 and {"access_token", "refresh_token"} <= set(cuerpo))
        comprobar("S07 — el access nuevo sirve en /me", solicitar("GET", "/api/v1/auth/me", cuerpo["access_token"])[0] == 200)
        vencido = jwt.encode({"sub": actor.nombre_usuario, "type": "refresh", "exp": datetime.now(timezone.utc) - timedelta(seconds=5)}, settings.secret_key, algorithm=settings.algorithm)
        rechazos = {
            "access usado como refresh": token_de(actor),
            "token basura": "no-es-un-jwt",
            "refresh vencido": vencido,
            "firmado con otra clave": jwt.encode({"sub": actor.nombre_usuario, "type": "refresh", "exp": datetime.now(timezone.utc) + timedelta(days=1)}, "otra-clave-cualquiera-de-32-bytes!", algorithm="HS256"),
            "sin exp": jwt.encode({"sub": actor.nombre_usuario, "type": "refresh"}, settings.secret_key, algorithm=settings.algorithm),
        }
        for nombre, token in rechazos.items():
            comprobar("S07 — " + nombre + " 401", solicitar("POST", ruta, datos={"refresh_token": token})[0] == 401)
        comprobar("S07 — campo extra 422", solicitar("POST", ruta, datos={"refresh_token": "x", "otro": 1})[0] == 422)
        # Desactivar la cuenta corta la renovación.
        refresh = create_refresh_token(actor.nombre_usuario)
        actor.activo = False
        db.commit()
        comprobar("S07 — usuario desactivado no renueva", solicitar("POST", ruta, datos={"refresh_token": refresh})[0] == 401)
        # Token con algoritmo "none" o firmado con otra clave no entra a /me.
        sin_firma = jwt.encode({"sub": actor.nombre_usuario, "type": "access", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)}, None, algorithm="none")
        comprobar("S08 — alg none rechazado en /me", solicitar("GET", "/api/v1/auth/me", sin_firma)[0] == 401)


# S09–S10: alta y edición de usuarios auditadas, sin hash.
def probar_auditoria_usuarios():
    with aislado() as db:
        admin = crear_actor(db, RolUsuario.ADMINISTRADOR)
        t = token_de(admin)
        clave_nueva = "Inicial-QA-" + uuid.uuid4().hex[:6]
        estado, creado, _ = solicitar("POST", "/api/v1/auth/usuarios", t, {"nombre_usuario": "qa_u_" + uuid.uuid4().hex[:10], "nombre_completo": "Usuario QA", "password": clave_nueva, "roles": ["gerencia", "operador_proceso"]})
        comprobar("S09 — alta 201 sin password_hash", estado == 201 and "password_hash" not in creado)
        lista = eventos(db, "usuarios", creado["id"])
        comprobar("S09 — un INSERT del administrador", len(lista) == 1 and lista[0].accion.value == "INSERT" and lista[0].usuario_id == admin.id)
        comprobar("S09 — instantánea con roles", json.loads(lista[0].valores_despues)["roles"] == ["gerencia", "operador_proceso"])
        comprobar("S09 — sin hash ni contraseña en auditoría", sin_secretos(lista, clave_nueva))
        ruta = "/api/v1/auth/usuarios/" + creado["id"]
        # Cambios sin efecto: nada se audita.
        for datos in ({}, {"nombre_completo": "Usuario QA"}, {"roles": ["operador_proceso", "gerencia"]}, {"activo": True}):
            solicitar("PUT", ruta, t, datos)
        comprobar("S10 — PUT sin cambios no audita", len(eventos(db, "usuarios", creado["id"])) == 1)
        estado, editado, _ = solicitar("PUT", ruta, t, {"roles": ["administrador"]})
        lista = eventos(db, "usuarios", creado["id"])
        comprobar("S10 — cambio de roles 200 y UPDATE", estado == 200 and editado["roles"] == ["administrador"] and len(lista) == 2)
        comprobar("S10 — antes/después con roles", json.loads(lista[1].valores_antes)["roles"] == ["gerencia", "operador_proceso"] and json.loads(lista[1].valores_despues)["roles"] == ["administrador"])
        solicitar("PUT", ruta, t, {"activo": False})
        comprobar("S10 — desactivación auditada", json.loads(eventos(db, "usuarios", creado["id"])[-1].valores_despues)["activo"] is False)
        solicitar("PUT", ruta, t, {"activo": True})
        # Restablecimiento de contraseña por el administrador.
        clave_reset = "Reset-QA-" + uuid.uuid4().hex[:6]
        comprobar("S10 — restablecer contraseña 200", solicitar("PUT", ruta, t, {"password": clave_reset})[0] == 200)
        ultimo = eventos(db, "usuarios", creado["id"])[-1]
        comprobar("S10 — motivo de restablecimiento", ultimo.motivo == "Restablecimiento de contraseña por administrador")
        comprobar("S10 — login con la clave restablecida", login(creado["nombre_usuario"], clave_reset)[0] == 200)
        comprobar("S10 — la clave anterior ya no sirve", login(creado["nombre_usuario"], clave_nueva)[0] == 401)
        comprobar("S10 — sin secretos tras restablecer", sin_secretos(eventos(db, "usuarios", creado["id"]), clave_nueva, clave_reset))
        comprobar("S10 — el admin no restablece su propia clave por esta ruta", solicitar("PUT", "/api/v1/auth/usuarios/" + admin.id, t, {"password": "Otra-Clave-123"})[0] == 400)
        comprobar("S10 — campo extra en edición 422", solicitar("PUT", ruta, t, {"nombre_usuario": "otro"})[0] == 422)
        gerencia = crear_actor(db, RolUsuario.GERENCIA)
        comprobar("S10 — gerencia no edita usuarios 403", solicitar("PUT", ruta, token_de(gerencia), {"activo": False})[0] == 403)


# S11: cambio de la propia contraseña.
def probar_cambio_password():
    with aislado() as db:
        actor = crear_actor(db, RolUsuario.OPERADOR_RECEPCION)
        t = token_de(actor)
        ruta = "/api/v1/auth/me/password"
        antes = len(eventos(db, "usuarios", actor.id))
        estado, cuerpo, _ = solicitar("PUT", ruta, t, {"password_actual": "equivocada", "password_nueva": "Nueva-Clave-123"})
        comprobar("S11 — actual incorrecta 400", estado == 400 and cuerpo["detail"] == "La contraseña actual no es correcta")
        comprobar("S11 — misma contraseña 400", solicitar("PUT", ruta, t, {"password_actual": CLAVE, "password_nueva": CLAVE})[0] == 400)
        comprobar("S11 — nueva muy corta 422", solicitar("PUT", ruta, t, {"password_actual": CLAVE, "password_nueva": "corta"})[0] == 422)
        comprobar("S11 — sin token 401", solicitar("PUT", ruta, None, {"password_actual": CLAVE, "password_nueva": "Nueva-Clave-123"})[0] == 401)
        comprobar("S11 — los rechazos no auditan", len(eventos(db, "usuarios", actor.id)) == antes)
        estado, cuerpo, _ = solicitar("PUT", ruta, t, {"password_actual": CLAVE, "password_nueva": "Nueva-Clave-123"})
        comprobar("S11 — cambio correcto 204 sin cuerpo", estado == 204 and cuerpo == "")
        lista = eventos(db, "usuarios", actor.id)
        comprobar("S11 — un UPDATE propio con motivo", len(lista) == antes + 1 and lista[-1].usuario_id == actor.id and lista[-1].motivo == "Cambio de contraseña propia")
        comprobar("S11 — sin secretos", sin_secretos(lista, CLAVE, "Nueva-Clave-123"))
        comprobar("S11 — login con la nueva", login(actor.nombre_usuario, "Nueva-Clave-123")[0] == 200)
        comprobar("S11 — la anterior ya no sirve", login(actor.nombre_usuario, CLAVE)[0] == 401)


# S12: validación más estricta de productores.
def probar_productores():
    with aislado() as db:
        admin = crear_actor(db, RolUsuario.ADMINISTRADOR)
        t = token_de(admin)
        ruta = "/api/v1/productores"
        invalidos = {
            "razón social solo espacios": {"rut": rut_valido(), "razon_social": "     "},
            "teléfono con letras": {"rut": rut_valido(), "razon_social": "QA Agrícola", "telefono": "abc<script>"},
            "teléfono con pocos dígitos": {"rut": rut_valido(), "razon_social": "QA Agrícola", "telefono": "12-34"},
            "campo extra": {"rut": rut_valido(), "razon_social": "QA Agrícola", "activo": False},
        }
        for nombre, datos in invalidos.items():
            comprobar("S12 — alta con " + nombre + " 422", solicitar("POST", ruta, t, datos)[0] == 422)
        estado, creado, _ = solicitar("POST", ruta, t, {"rut": rut_valido(), "razon_social": "  QA   Agrícola  Sur ", "direccion": "   ", "telefono": " +56 9 1234-5678 "})
        comprobar("S12 — alta normaliza espacios", estado == 201 and creado["razon_social"] == "QA Agrícola Sur" and creado["telefono"] == "+56 9 1234-5678")
        comprobar("S12 — dirección vacía queda NULL", creado["direccion"] is None)
        ruta_uno = ruta + "/" + str(creado["id"])
        # Desde la decisión D3 (2026-10-31), un teléfono vacío al editar lo quita (NULL) en vez de responder 422.
        estado, sin_telefono, _ = solicitar("PUT", ruta_uno, t, {"telefono": "  "})
        comprobar("S12 — edición con teléfono vacío lo quita", estado == 200 and sin_telefono["telefono"] is None)
        comprobar("S12 — edición con campo extra 422", solicitar("PUT", ruta_uno, t, {"id": 1})[0] == 422)
        estado, editado, _ = solicitar("PUT", ruta_uno, t, {"razon_social": "QA  Agrícola Norte"})
        comprobar("S12 — edición normaliza y guarda", estado == 200 and editado["razon_social"] == "QA Agrícola Norte")
        comprobar("S12 — fila guardada normalizada", db.get(Productor, creado["id"]).razon_social == "QA Agrícola Norte")


# S13–S14: /docs desactivable y CORS sin credenciales.
def probar_configuracion():
    comprobar("S13 — /docs publicado en desarrollo", solicitar("GET", "/docs")[0] == 200)
    entorno = dict(os.environ, MOSTRAR_DOCS="false")
    codigo = "from app.main import app; print(app.docs_url, app.redoc_url, app.openapi_url)"
    salida = subprocess.run([sys.executable, "-c", codigo], env=entorno, capture_output=True, text=True, timeout=60)
    comprobar("S13 — MOSTRAR_DOCS=false apaga /docs, /redoc y /openapi.json", salida.stdout.strip() == "None None None")
    _, _, cabeceras = solicitar("OPTIONS", "/api/v1/productores", cabeceras={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "Authorization"})
    comprobar("S14 — CORS mantiene el origen del frontend", cabeceras.get("access-control-allow-origin") == "http://localhost:5173")
    comprobar("S14 — CORS sin allow-credentials", "access-control-allow-credentials" not in cabeceras)
    comprobar("S14 — CORS sin DELETE", "DELETE" not in cabeceras.get("access-control-allow-methods", ""))


# Ejecuta todo y compara el estado final con el inicial.
def main() -> int:
    global fallas
    with engine.connect() as conexion:
        inicial = huellas(conexion)
    dependencias = dict(app.dependency_overrides)
    for escenario in (probar_login, probar_limite, probar_login_docs, probar_largos, probar_refresh, probar_auditoria_usuarios, probar_cambio_password, probar_productores, probar_configuracion):
        try:
            escenario()
        except Exception:
            fallas += 1
            print(f"FALLA {escenario.__name__}: error inesperado", flush=True)
            traceback.print_exc()
    # S15: nada quedó en la base y la app volvió a su estado normal.
    with engine.connect() as conexion:
        final = huellas(conexion)
    comprobar("S15 — tablas idénticas al inicio (sin filas residuales)", final == inicial)
    comprobar("S15 — dependencias de la app restauradas", app.dependency_overrides == dependencias)
    print(f"\nCOMPROBACIONES: {comprobaciones} FALLAS: {fallas}")
    print("RESULTADO:", "todas las pruebas pasaron" if fallas == 0 else f"{fallas} prueba(s) fallaron")
    return 1 if fallas else 0


# No ejecuta nada al importar el módulo.
if __name__ == "__main__":
    sys.exit(main())
