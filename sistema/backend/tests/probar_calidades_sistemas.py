"""HU09 — Pruebas reproducibles de calidades y sistemas productivos.

Ejecutar desde sistema/: docker compose exec -T backend python -m tests.probar_calidades_sistemas
Cada escenario corre dentro de una transacción externa que siempre se revierte:
los commits de los servicios quedan como savepoints y no se borra ninguna fila
(tampoco de auditoría) para limpiar. Importar este módulo no ejecuta pruebas.
"""

# Ejecuta solicitudes ASGI en memoria sin instalar un cliente HTTP.
import asyncio
# Calcula huellas del contenido de las tablas sin imprimir sus datos.
import hashlib
# Serializa solicitudes y lee respuestas y valores de auditoría.
import json
# Devuelve un código de salida distinto de cero si algo falla.
import sys
# Muestra la ubicación de errores inesperados sin contarlos como aprobados.
import traceback
# Genera nombres y ids ficticios que no chocan con datos existentes.
import uuid
# Administra la apertura y la limpieza de cada escenario aislado.
from contextlib import contextmanager
# Simula un fallo de auditoría solo durante un caso.
from unittest.mock import patch
# Separa la ruta y la query string al armar la solicitud ASGI.
from urllib.parse import urlsplit

# Consultas de verificación y lectura completa de tablas.
from sqlalchemy import func, select, text
# Sesión ligada a la conexión que controla la prueba.
from sqlalchemy.orm import Session

# Aplicación completa: autenticación, roles, routers y servicios reales.
from app.main import app
# Motor de desarrollo y dependencia de sesión que se reemplaza durante HTTP.
from app.core.database import engine, get_db
# Genera tokens válidos para los actores temporales.
from app.core.security import create_access_token
# Modelos que se verifican.
from app.models.auditoria import AccionAuditoria, Auditoria
from app.models.calidad import Calidad
from app.models.sistema_productivo import SistemaProductivo
from app.models.usuario import RolUsuario, Usuario, UsuarioRol
# Servicios y schemas para el caso de fallo de auditoría.
from app.schemas.calidad import CalidadCreate
from app.schemas.sistema_productivo import SistemaProductivoCreate
from app.services import calidad as servicio_calidad
from app.services import sistema_productivo as servicio_sistema

# Tablas cuyo contenido debe quedar idéntico al terminar.
TABLAS = ("usuarios", "usuario_roles", "auditoria", "calidades", "sistemas_productivos")

# Datos de cada catálogo para recorrer los mismos casos sobre ambos.
CATALOGOS = (
    {
        "nombre": "calidades",  # Tabla y tabla de auditoría.
        "ruta": "/api/v1/calidades",  # Ruta base de la API.
        "modelo": Calidad,  # Modelo ORM.
        "duplicado": "Ya existe una calidad con ese nombre",  # Mensaje 409.
        "no_encontrado": "Calidad no encontrada",  # Mensaje 404.
        "servicio": servicio_calidad,  # Módulo de servicio.
        "crear": servicio_calidad.crear_calidad,  # Función de alta.
        "schema": CalidadCreate,  # Schema de alta.
    },
    {
        "nombre": "sistemas_productivos",
        "ruta": "/api/v1/sistemas-productivos",
        "modelo": SistemaProductivo,
        "duplicado": "Ya existe un sistema productivo con ese nombre",
        "no_encontrado": "Sistema productivo no encontrado",
        "servicio": servicio_sistema,
        "crear": servicio_sistema.crear_sistema_productivo,
        "schema": SistemaProductivoCreate,
    },
)

# Contadores globales de la ejecución.
comprobaciones = 0
fallas = 0


# Registra una comprobación con el mismo formato de las demás pruebas del proyecto.
def comprobar(nombre: str, condicion: bool) -> None:
    global comprobaciones, fallas
    # Cuenta todas las comprobaciones ejecutadas.
    comprobaciones += 1
    # Cuenta y muestra solo las que fallan, para no inundar la salida.
    if not condicion:
        fallas += 1
        print("FALLA " + nombre, flush=True)


# Calcula filas y huella SHA-256 de cada tabla (sin imprimir su contenido).
def huellas(conexion) -> dict:
    salida = {}
    # Recorre las tablas que deben conservarse.
    for tabla in TABLAS:
        # Lee todas las filas como diccionarios.
        filas = conexion.execute(text("SELECT * FROM " + tabla)).mappings().all()
        # Ordena la serialización para que la huella no dependa del orden de lectura.
        serial = sorted(json.dumps(dict(f), sort_keys=True, default=str) for f in filas)
        # Guarda cantidad y huella del contenido.
        salida[tabla] = (len(filas), hashlib.sha256("\n".join(serial).encode("utf-8")).hexdigest())
    return salida


# Abre un escenario aislado: todo lo que pase dentro se revierte al salir.
@contextmanager
def aislado():
    # Conexión propia de la prueba.
    with engine.connect() as conexion:
        # Transacción externa que nunca se confirma.
        externa = conexion.begin()
        # Los commit de los servicios se convierten en savepoints de esta transacción.
        db = Session(bind=conexion, autoflush=False, join_transaction_mode="create_savepoint")
        try:
            # Entrega la sesión y la conexión al escenario.
            yield db, conexion
            # El escenario no debe haber cerrado la transacción externa.
            comprobar("Aislamiento — transacción externa activa", externa.is_active and conexion.in_transaction())
        finally:
            # Cierra la sesión y revierte todo, incluidas las auditorías del escenario.
            db.close()
            if externa.is_active:
                externa.rollback()


# Crea un usuario temporal con un rol, dentro del escenario aislado.
def crear_actor(db: Session, rol: RolUsuario) -> tuple[Usuario, str]:
    # Nombre único para no chocar con usuarios existentes.
    actor = Usuario(
        id=str(uuid.uuid4()),  # Id conocido antes del flush.
        nombre_usuario="qa_hu09_" + uuid.uuid4().hex[:20],  # Respeta el límite de 50 caracteres.
        nombre_completo="Actor QA HU09",  # Nombre inventado.
        password_hash="ficticio_no_sirve_para_login",  # No es una contraseña real.
        activo=True,  # Habilitado para pasar get_current_user.
        roles_asignados=[UsuarioRol(rol=rol)],  # Rol que se quiere probar.
    )  # Finaliza la preparación del actor.
    # Lo agrega y confirma solo dentro del savepoint del escenario.
    db.add(actor)
    db.commit()
    # Devuelve el actor y un token válido con su rol.
    return actor, create_access_token(actor.nombre_usuario, [rol.value])


# Envía una solicitud a la aplicación completa en memoria (sin red).
async def _solicitar(metodo: str, ruta: str, token: str | None, datos) -> tuple[int, object]:
    # Separa ruta y parámetros.
    partes = urlsplit(ruta)
    # Cuerpo JSON cuando corresponde.
    cuerpo = json.dumps(datos).encode("utf-8") if datos is not None else b""
    # Cabeceras mínimas.
    cabeceras = [(b"host", b"qa-hu09")]
    if datos is not None:
        cabeceras += [(b"content-type", b"application/json"), (b"content-length", str(len(cuerpo)).encode())]
    if token:
        cabeceras.append((b"authorization", ("Bearer " + token).encode()))
    # Descripción ASGI de la solicitud.
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": metodo, "scheme": "http", "path": partes.path,
        "raw_path": partes.path.encode(), "query_string": partes.query.encode(),
        "root_path": "", "headers": cabeceras, "client": ("127.0.0.1", 1), "server": ("qa-hu09", 80),
    }
    # Mensajes que devuelve la aplicación.
    mensajes = []
    entregado = False

    # Entrega el cuerpo una sola vez.
    async def receive():
        nonlocal entregado
        if entregado:
            return {"type": "http.disconnect"}
        entregado = True
        return {"type": "http.request", "body": cuerpo, "more_body": False}

    # Guarda cada mensaje de respuesta.
    async def send(mensaje):
        mensajes.append(mensaje)

    # Ejecuta la aplicación.
    await app(scope, receive, send)
    # Extrae estado y cuerpo.
    estado = next(m["status"] for m in mensajes if m["type"] == "http.response.start")
    texto = b"".join(m.get("body", b"") for m in mensajes if m["type"] == "http.response.body").decode("utf-8")
    try:
        return estado, json.loads(texto)
    except ValueError:
        return estado, texto


# Versión síncrona del envío, para escribir los casos en orden.
def solicitar(metodo: str, ruta: str, token: str | None = None, datos=None) -> tuple[int, object]:
    return asyncio.run(_solicitar(metodo, ruta, token, datos))


# Hace que cada solicitud HTTP use la sesión del escenario aislado.
@contextmanager
def api_con_sesion(db: Session):
    # Conserva las dependencias previas para restaurarlas exactamente.
    anteriores = dict(app.dependency_overrides)

    # Entrega siempre la misma sesión aislada.
    def proveedor():
        yield db

    app.dependency_overrides[get_db] = proveedor
    try:
        yield
    finally:
        # No deja la aplicación en modo de prueba.
        app.dependency_overrides.clear()
        app.dependency_overrides.update(anteriores)


# Cuenta los eventos de auditoría de un registro.
def eventos(db: Session, tabla: str, registro_id) -> list[Auditoria]:
    consulta = select(Auditoria).where(Auditoria.tabla == tabla, Auditoria.registro_id == str(registro_id)).order_by(Auditoria.id)
    return list(db.scalars(consulta))


# Total de eventos de auditoría (para comprobar que un error no agrega ninguno).
def total_auditoria(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(Auditoria))


# Casos HTTP de un catálogo: alta, duplicados, validación, filtros, edición, estado, 404 y permisos.
def probar_catalogo_http(cat: dict) -> None:
    n = cat["nombre"]
    ruta = cat["ruta"]
    sufijo = uuid.uuid4().hex[:8]
    with aislado() as (db, _):
        # Actores del escenario.
        admin, t_admin = crear_actor(db, RolUsuario.ADMINISTRADOR)
        _, t_gerencia = crear_actor(db, RolUsuario.GERENCIA)
        _, t_operador = crear_actor(db, RolUsuario.OPERADOR_RECEPCION)
        with api_con_sesion(db):
            # Q1: alta con espacios sobrantes; se guarda normalizado y activo.
            estado, creado = solicitar("POST", ruta, t_admin, {"nombre": f"  QA Extra   {sufijo} "})
            comprobar(f"{n} Q1 — alta 201 con nombre normalizado", estado == 201 and creado["nombre"] == f"QA Extra {sufijo}" and creado["activo"] is True)
            comprobar(f"{n} Q1 — solo campos públicos", set(creado) == {"id", "nombre", "activo"})
            # Q2: auditoría INSERT con el actor real.
            ev = eventos(db, n, creado["id"])
            comprobar(f"{n} Q2 — auditoría INSERT", len(ev) == 1 and ev[0].accion == AccionAuditoria.INSERT and ev[0].usuario_id == admin.id and ev[0].valores_antes is None)
            comprobar(f"{n} Q2 — valores después", json.loads(ev[0].valores_despues) == creado)
            # Q3: mismo nombre con otras mayúsculas → 409 y sin auditoría nueva.
            antes = total_auditoria(db)
            estado, cuerpo = solicitar("POST", ruta, t_admin, {"nombre": f"qa extra {sufijo}".upper()})
            comprobar(f"{n} Q3 — duplicado sin distinguir mayúsculas 409", estado == 409 and cuerpo["detail"] == cat["duplicado"])
            comprobar(f"{n} Q3 — duplicado sin auditoría", total_auditoria(db) == antes)
            # Q4: distinta tilde → nombre distinto (collation CI_AS).
            e1, a1 = solicitar("POST", ruta, t_admin, {"nombre": f"Orgánico {sufijo}"})
            e2, a2 = solicitar("POST", ruta, t_admin, {"nombre": f"Organico {sufijo}"})
            comprobar(f"{n} Q4 — tilde distinta permitida", e1 == 201 and e2 == 201 and a1["id"] != a2["id"])
            # Q5: validaciones 422 (vacío, solo espacios, largo, tipo, campo extra).
            for datos in ({"nombre": ""}, {"nombre": "   "}, {"nombre": "X" * 51}, {"nombre": 12}, {}, {"nombre": "Ok", "activo": False}):
                estado, _ = solicitar("POST", ruta, t_admin, datos)
                comprobar(f"{n} Q5 — 422 con {list(datos)}", estado == 422)
            # Q6: renombrar → 200 y auditoría UPDATE con antes y después.
            id_ = creado["id"]
            estado, editado = solicitar("PUT", f"{ruta}/{id_}", t_admin, {"nombre": f"QA Premium {sufijo}"})
            ev = eventos(db, n, id_)
            comprobar(f"{n} Q6 — renombrar 200", estado == 200 and editado["nombre"] == f"QA Premium {sufijo}")
            comprobar(f"{n} Q6 — auditoría UPDATE", ev[-1].accion == AccionAuditoria.UPDATE and json.loads(ev[-1].valores_antes)["nombre"] == f"QA Extra {sufijo}" and json.loads(ev[-1].valores_despues)["nombre"] == f"QA Premium {sufijo}")
            # Q7: PUT vacío o con el mismo valor → 200 sin auditoría.
            antes = total_auditoria(db)
            e_vacio, _ = solicitar("PUT", f"{ruta}/{id_}", t_admin, {})
            e_igual, _ = solicitar("PUT", f"{ruta}/{id_}", t_admin, {"nombre": f"  QA Premium   {sufijo} "})
            comprobar(f"{n} Q7 — sin cambios 200", e_vacio == 200 and e_igual == 200)
            comprobar(f"{n} Q7 — sin cambios no audita", total_auditoria(db) == antes)
            # Q8: renombrar al nombre de otro registro → 409.
            estado, cuerpo = solicitar("PUT", f"{ruta}/{a1['id']}", t_admin, {"nombre": f"Organico {sufijo}"})
            comprobar(f"{n} Q8 — renombrar a nombre ocupado 409", estado == 409 and cuerpo["detail"] == cat["duplicado"])
            # Q9: desactivar → sigue existiendo, auditado; filtros correctos.
            estado, desactivado = solicitar("PUT", f"{ruta}/{id_}", t_admin, {"activo": False})
            comprobar(f"{n} Q9 — desactivar 200", estado == 200 and desactivado["activo"] is False)
            comprobar(f"{n} Q9 — desactivar auditado", eventos(db, n, id_)[-1].accion == AccionAuditoria.UPDATE)
            _, todos = solicitar("GET", ruta, t_admin)
            _, activos = solicitar("GET", ruta + "?activo=true", t_admin)
            _, inactivos = solicitar("GET", ruta + "?activo=false", t_admin)
            comprobar(f"{n} Q9 — sigue en el listado general", id_ in {r["id"] for r in todos})
            comprobar(f"{n} Q9 — filtros por estado", id_ not in {r["id"] for r in activos} and id_ in {r["id"] for r in inactivos} and all(r["activo"] for r in activos) and not any(r["activo"] for r in inactivos))
            # Q10: el nombre de un inactivo sigue reservado.
            estado, _ = solicitar("POST", ruta, t_admin, {"nombre": f"QA Premium {sufijo}"})
            comprobar(f"{n} Q10 — nombre de inactivo reservado 409", estado == 409)
            # Q11: 404 en detalle y edición.
            e_get, c_get = solicitar("GET", f"{ruta}/999999999", t_admin)
            e_put, _ = solicitar("PUT", f"{ruta}/999999999", t_admin, {"activo": False})
            comprobar(f"{n} Q11 — 404", e_get == 404 and c_get["detail"] == cat["no_encontrado"] and e_put == 404)
            # Q12: permisos.
            for metodo, sufijo_ruta, datos in (("GET", "", None), ("POST", "", {"nombre": "QA Permiso"}), ("GET", f"/{id_}", None), ("PUT", f"/{id_}", {"activo": True})):
                comprobar(f"{n} Q12 — {metodo}{sufijo_ruta or ''} sin token 401", solicitar(metodo, ruta + sufijo_ruta, None, datos)[0] == 401)
                comprobar(f"{n} Q12 — {metodo} gerencia 403", solicitar(metodo, ruta + sufijo_ruta, t_gerencia, datos)[0] == 403)
                comprobar(f"{n} Q12 — {metodo} operador 403", solicitar(metodo, ruta + sufijo_ruta, t_operador, datos)[0] == 403)
            # Q13: no existe borrado físico.
            comprobar(f"{n} Q13 — DELETE 405", solicitar("DELETE", f"{ruta}/{id_}", t_admin)[0] == 405)
            comprobar(f"{n} Q13 — registro conservado", db.get(cat["modelo"], id_) is not None)


# Q14: si la auditoría falla, no queda ni el registro ni el evento.
def probar_fallo_auditoria(cat: dict) -> None:
    n = cat["nombre"]
    with aislado() as (db, _):
        admin, _ = crear_actor(db, RolUsuario.ADMINISTRADOR)
        filas_antes = db.scalar(select(func.count()).select_from(cat["modelo"]))
        eventos_antes = total_auditoria(db)
        # Hace fallar la auditoría dentro del servicio, después del flush del registro.
        with patch.object(cat["servicio"], "registrar_auditoria", side_effect=RuntimeError("fallo simulado")):
            try:
                cat["crear"](db, cat["schema"](nombre="QA Fallo " + uuid.uuid4().hex[:8]), admin)
                recibido = None
            except RuntimeError as error:
                recibido = error
        comprobar(f"{n} Q14 — el error se propaga", recibido is not None)
        comprobar(f"{n} Q14 — sin registro nuevo", db.scalar(select(func.count()).select_from(cat["modelo"])) == filas_antes)
        comprobar(f"{n} Q14 — sin auditoría nueva", total_auditoria(db) == eventos_antes)


# Ejecuta todo y compara el estado final con el inicial.
def main() -> int:
    global fallas
    # Huella antes de cualquier escenario (lectura sin transacción abierta).
    with engine.connect() as conexion:
        inicial = huellas(conexion)
    dependencias = dict(app.dependency_overrides)
    # Cada catálogo y cada caso de fallo en su propio escenario.
    for cat in CATALOGOS:
        for escenario in (probar_catalogo_http, probar_fallo_auditoria):
            try:
                escenario(cat)
            except Exception:
                fallas += 1
                print(f"FALLA {cat['nombre']} {escenario.__name__}: error inesperado", flush=True)
                traceback.print_exc()
    # Q15: nada quedó en la base y la app volvió a su estado normal.
    with engine.connect() as conexion:
        final = huellas(conexion)
    comprobar("Q15 — tablas idénticas al inicio (sin filas residuales)", final == inicial)
    comprobar("Q15 — dependencias de la app restauradas", app.dependency_overrides == dependencias)
    print(f"\nCOMPROBACIONES: {comprobaciones} FALLAS: {fallas}")
    print("RESULTADO:", "todas las pruebas pasaron" if fallas == 0 else f"{fallas} prueba(s) fallaron")
    return 1 if fallas else 0


# No ejecuta nada al importar el módulo.
if __name__ == "__main__":
    sys.exit(main())
