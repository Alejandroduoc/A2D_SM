"""HU10 — Pruebas reproducibles de tipos de bandeja y embalajes.

Ejecutar desde sistema/ con:
docker compose exec backend python -m tests.probar_bandejas_embalajes

Las escrituras usan una transacción externa. Los commit de los servicios quedan
como savepoints y todo se revierte al terminar, incluida la auditoría.
Importar este módulo no ejecuta pruebas.
"""

# Ejecuta solicitudes ASGI en memoria sin instalar un cliente HTTP.
import asyncio
# Calcula huellas del contenido de las tablas sin imprimir sus datos.
import hashlib
# Serializa cuerpos, respuestas y filas para las huellas.
import json
# Devuelve un código de salida distinto de cero si algo falla.
import sys
# Muestra la ubicación de errores inesperados sin contarlos como aprobados.
import traceback
# Genera nombres irrepetibles para no depender de los datos existentes.
import uuid
# Administra la apertura y la limpieza del escenario aislado.
from contextlib import contextmanager
# Simula un fallo de auditoría para comprobar atomicidad.
from unittest.mock import patch
# Separa la ruta y la query string al armar la solicitud ASGI.
from urllib.parse import urlsplit

# Cuenta registros y lee tablas completas para las huellas.
from sqlalchemy import func, select, text
# Sesión ligada a la conexión que controla la prueba.
from sqlalchemy.orm import Session

# Aplicación completa: autenticación, roles, routers y servicios reales.
from app.main import app
# Motor de desarrollo y dependencia de sesión que se reemplaza durante HTTP.
from app.core.database import engine, get_db
# Genera tokens válidos para los actores temporales.
from app.core.security import create_access_token
# Modelos que se crean, consultan y verifican.
from app.models.auditoria import AccionAuditoria, Auditoria
from app.models.embalaje import Embalaje
from app.models.tipo_bandeja import TipoBandeja
from app.models.usuario import RolUsuario, Usuario, UsuarioRol

# Tablas cuyo contenido debe quedar idéntico al terminar (incluye los actores temporales).
TABLAS = ("usuarios", "usuario_roles", "auditoria", "tipos_bandeja", "embalajes")

# Cuenta todas las condiciones evaluadas durante esta ejecución.
comprobaciones = 0
# Cuenta únicamente las condiciones que no se cumplieron.
fallas = 0


# Registra un resultado sin detener los casos posteriores.
def comprobar(nombre: str, condicion: bool) -> None:
    # Permite actualizar ambos contadores globales.
    global comprobaciones, fallas
    # Toda llamada representa una comprobación ejecutada.
    comprobaciones += 1
    # Sólo incrementa fallas cuando la condición es falsa.
    if not condicion:
        # Conserva el total de problemas encontrados.
        fallas += 1
        # Muestra el caso preciso que necesita revisión.
        print("FALLA " + nombre, flush=True)


# Calcula filas y huella SHA-256 de cada tabla, sin imprimir su contenido.
def huellas(conexion) -> dict:
    # Guarda (cantidad, huella) por tabla.
    salida = {}
    # Recorre las tablas que deben conservarse.
    for tabla in TABLAS:
        # Lee todas las filas como diccionarios.
        filas = conexion.execute(text("SELECT * FROM " + tabla)).mappings().all()
        # Ordena la serialización para que la huella no dependa del orden de lectura.
        serial = sorted(json.dumps(dict(f), sort_keys=True, default=str) for f in filas)
        # Guarda la cantidad y la huella del contenido.
        salida[tabla] = (len(filas), hashlib.sha256("\n".join(serial).encode("utf-8")).hexdigest())
    # Devuelve el resumen de todas las tablas.
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
            # Cierra la sesión.
            db.close()
            # Revierte todo, incluidas las auditorías del escenario.
            if externa.is_active:
                externa.rollback()


# Crea un usuario temporal con un rol, dentro del escenario aislado.
def crear_actor(db: Session, rol: RolUsuario) -> tuple[Usuario, str]:
    # Usuario con nombre único para no chocar con los existentes.
    actor = Usuario(
        id=str(uuid.uuid4()),  # Id conocido antes del flush.
        nombre_usuario="qa_hu10_" + uuid.uuid4().hex[:20],  # Respeta el límite de 50 caracteres.
        nombre_completo="Actor QA HU10",  # Nombre inventado.
        password_hash="ficticio_no_sirve_para_login",  # No es una contraseña real.
        activo=True,  # Habilitado para pasar get_current_user.
        roles_asignados=[UsuarioRol(rol=rol)],  # Rol que se quiere probar.
    )  # Finaliza la preparación del actor.
    # Lo agrega a la sesión del escenario.
    db.add(actor)
    # Lo confirma solo dentro del savepoint del escenario.
    db.commit()
    # Devuelve el actor y un token válido con su rol.
    return actor, create_access_token(actor.nombre_usuario, [rol.value])


# Envía una solicitud a la aplicación completa en memoria (sin red).
async def _solicitar(metodo: str, ruta: str, token: str | None, datos) -> tuple[int, object]:
    # Separa ruta y parámetros.
    partes = urlsplit(ruta)
    # Cuerpo JSON cuando corresponde.
    cuerpo = json.dumps(datos).encode("utf-8") if datos is not None else b""
    # Cabecera mínima de una solicitud HTTP.
    cabeceras = [(b"host", b"qa-hu10")]
    # Declara tipo y largo del cuerpo cuando se envía JSON.
    if datos is not None:
        cabeceras += [(b"content-type", b"application/json"), (b"content-length", str(len(cuerpo)).encode())]
    # Agrega el token solo cuando el caso lo usa.
    if token:
        cabeceras.append((b"authorization", ("Bearer " + token).encode()))
    # Descripción ASGI de la solicitud.
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",  # Interfaz utilizada.
        "method": metodo, "scheme": "http", "path": partes.path,  # Método y ruta.
        "raw_path": partes.path.encode(), "query_string": partes.query.encode(),  # Parámetros de la URL.
        "root_path": "", "headers": cabeceras, "client": ("127.0.0.1", 1), "server": ("qa-hu10", 80),  # Contexto HTTP.
    }  # Finaliza la descripción de la solicitud.
    # Mensajes que devuelve la aplicación.
    mensajes = []
    # Controla que el cuerpo se entregue una sola vez.
    entregado = False

    # Entrega el cuerpo una sola vez.
    async def receive():
        nonlocal entregado
        # La segunda lectura indica que el cliente terminó.
        if entregado:
            return {"type": "http.disconnect"}
        # Marca la única entrega.
        entregado = True
        # Entrega el JSON completo.
        return {"type": "http.request", "body": cuerpo, "more_body": False}

    # Guarda cada mensaje de respuesta.
    async def send(mensaje):
        mensajes.append(mensaje)

    # Ejecuta la aplicación con autenticación, router y servicio reales.
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

    # Solo se reemplaza la sesión; autenticación y roles siguen siendo reales.
    app.dependency_overrides[get_db] = proveedor
    try:
        # Ejecuta los casos del escenario.
        yield
    finally:
        # No deja la aplicación en modo de prueba.
        app.dependency_overrides.clear()
        app.dependency_overrides.update(anteriores)


# Eventos de auditoría de un registro, en orden.
def eventos(db: Session, tabla: str, registro_id) -> list[Auditoria]:
    # Filtra por tabla y registro, ordenando por la PK creciente.
    consulta = select(Auditoria).where(Auditoria.tabla == tabla, Auditoria.registro_id == str(registro_id)).order_by(Auditoria.id)
    # Devuelve los eventos encontrados.
    return list(db.scalars(consulta))


# Total de eventos de auditoría (para comprobar que un error no agrega ninguno).
def total_auditoria(db: Session) -> int:
    # Cuenta todas las filas de auditoría visibles en la sesión.
    return db.scalar(select(func.count()).select_from(Auditoria))


# Casos de permisos, bandejas, embalajes y atomicidad, en un solo escenario reversible.
def probar_mantenimientos() -> None:
    # Ejecuta todos los casos en una única transacción externa reversible.
    with aislado() as (db, _):
        # Crea actores temporales con identidades y roles reales en la base.
        administrador, token_admin = crear_actor(db, RolUsuario.ADMINISTRADOR)
        _, token_gerencia = crear_actor(db, RolUsuario.GERENCIA)
        _, token_recepcion = crear_actor(db, RolUsuario.OPERADOR_RECEPCION)
        _, token_proceso = crear_actor(db, RolUsuario.OPERADOR_PROCESO)
        # Evita colisiones con datos creados manualmente.
        sufijo = uuid.uuid4().hex[:8]

        # Hace que autenticación, routers y servicios compartan la sesión aislada.
        with api_con_sesion(db):
            # Conserva cantidades para demostrar que los rechazos de permisos no escriben.
            cantidades_seguridad_antes = (
                db.scalar(select(func.count()).select_from(TipoBandeja)),
                db.scalar(select(func.count()).select_from(Embalaje)),
                total_auditoria(db),
            )
            # Verifica seguridad y métodos comunes de ambos mantenimientos.
            recursos_seguridad = (
                (
                    "/api/v1/tipos-bandeja",
                    {"nombre": "Sin permiso", "peso_tara_kg": "1.00"},
                    {"peso_tara_kg": "2.00"},
                ),
                (
                    "/api/v1/embalajes",
                    {"nombre": "Sin permiso", "kg_por_caja": "10.00"},
                    {"kg_por_caja": None},
                ),
            )
            # Recorre ambos recursos con cuerpos válidos para aislar la autorización.
            for ruta, cuerpo_alta, cuerpo_edicion in recursos_seguridad:
                # Una solicitud sin credenciales debe ser rechazada.
                comprobar(ruta + " — sin token 401", solicitar("GET", ruta)[0] == 401)
                # Protege también las dos operaciones que escriben datos.
                comprobar(ruta + " — POST sin token 401", solicitar("POST", ruta, datos=cuerpo_alta)[0] == 401)
                comprobar(ruta + " — PUT sin token 401", solicitar("PUT", ruta + "/999999999", datos=cuerpo_edicion)[0] == 401)
                # Los roles no administrativos no pueden leer ni modificar estos catálogos.
                for token in (token_gerencia, token_recepcion, token_proceso):
                    # Comprueba lectura y escrituras usando la autorización consultada en la base.
                    comprobar(ruta + " — otro rol 403", solicitar("GET", ruta, token)[0] == 403)
                    comprobar(ruta + " — POST otro rol 403", solicitar("POST", ruta, token, cuerpo_alta)[0] == 403)
                    comprobar(ruta + " — PUT otro rol 403", solicitar("PUT", ruta + "/999999999", token, cuerpo_edicion)[0] == 403)
                # El administrador puede consultar la colección.
                comprobar(ruta + " — administrador 200", solicitar("GET", ruta, token_admin)[0] == 200)
                # Una identidad inexistente produce un detalle 404.
                comprobar(ruta + " — inexistente 404", solicitar("GET", ruta + "/999999999", token_admin)[0] == 404)
                # No existe borrado físico ni endpoint DELETE.
                comprobar(ruta + " — DELETE 405", solicitar("DELETE", ruta + "/1", token_admin)[0] == 405)
            # Ningún rechazo de autenticación o autorización debe dejar datos ni eventos.
            comprobar(
                "Permisos — rechazos sin escrituras",
                cantidades_seguridad_antes
                == (
                    db.scalar(select(func.count()).select_from(TipoBandeja)),
                    db.scalar(select(func.count()).select_from(Embalaje)),
                    total_auditoria(db),
                ),
            )

            # Crea una bandeja con espacios sobrantes y tara decimal textual.
            estado, bandeja = solicitar(
                "POST",
                "/api/v1/tipos-bandeja",
                token_admin,
                {"nombre": f"  Bandeja   QA {sufijo} ", "peso_tara_kg": "1.25"},
            )
            # Debe normalizar el nombre, asignar id y nacer activa.
            comprobar(
                "B1 — alta de bandeja",
                estado == 201
                and bandeja["nombre"] == f"Bandeja QA {sufijo}"
                and bandeja["peso_tara_kg"] == "1.25"
                and bandeja["activo"] is True,
            )
            # La salida no debe incluir atributos internos.
            comprobar(
                "B2 — campos públicos",
                set(bandeja) == {"id", "nombre", "peso_tara_kg", "activo"},
            )
            # La creación debe producir un único evento con el actor autenticado.
            eventos_bandeja = eventos(db, "tipos_bandeja", bandeja["id"])
            comprobar(
                "B3 — auditoría INSERT",
                len(eventos_bandeja) == 1
                and eventos_bandeja[0].accion == AccionAuditoria.INSERT
                and eventos_bandeja[0].usuario_id == administrador.id,
            )
            # El mismo nombre con otras mayúsculas permanece reservado.
            estado, _ = solicitar(
                "POST",
                "/api/v1/tipos-bandeja",
                token_admin,
                {"nombre": f"BANDEJA QA {sufijo}", "peso_tara_kg": "2.00"},
            )
            comprobar("B4 — duplicado 409", estado == 409)
            # Recorre entradas de tara que deben fallar en la capa de schemas.
            for tara in (0, -1, "1.001", True, "10000.00"):
                # Cada valor debe ser rechazado antes de llegar al servicio.
                estado, _ = solicitar(
                    "POST",
                    "/api/v1/tipos-bandeja",
                    token_admin,
                    {"nombre": f"Inválida {uuid.uuid4().hex[:5]}", "peso_tara_kg": tara},
                )
                # FastAPI convierte la validación en 422.
                comprobar(f"B5 — tara inválida {tara!r}", estado == 422)
            # Actualiza simultáneamente la tara y el estado lógico.
            estado, bandeja_editada = solicitar(
                "PUT",
                f"/api/v1/tipos-bandeja/{bandeja['id']}",
                token_admin,
                {"peso_tara_kg": "1.50", "activo": False},
            )
            # Debe conservar identidad y reflejar ambos cambios.
            comprobar(
                "B6 — editar y desactivar",
                estado == 200
                and bandeja_editada["id"] == bandeja["id"]
                and bandeja_editada["peso_tara_kg"] == "1.50"
                and bandeja_editada["activo"] is False,
            )
            # La actualización efectiva agrega exactamente un evento UPDATE.
            eventos_bandeja = eventos(db, "tipos_bandeja", bandeja["id"])
            comprobar(
                "B7 — auditoría UPDATE",
                len(eventos_bandeja) == 2 and eventos_bandeja[-1].accion == AccionAuditoria.UPDATE,
            )
            # Los filtros deben separar correctamente ambos estados.
            _, activas = solicitar("GET", "/api/v1/tipos-bandeja?activo=true", token_admin)
            _, inactivas = solicitar("GET", "/api/v1/tipos-bandeja?activo=false", token_admin)
            comprobar("B8 — filtro activo", all(item["activo"] for item in activas))
            comprobar("B8 — filtro inactivo", any(item["id"] == bandeja["id"] for item in inactivas))
            # Enviar el mismo estado no debe generar auditoría adicional.
            total_antes = total_auditoria(db)
            estado, _ = solicitar(
                "PUT",
                f"/api/v1/tipos-bandeja/{bandeja['id']}",
                token_admin,
                {"activo": False},
            )
            comprobar("B9 — edición sin cambios 200", estado == 200)
            comprobar("B9 — edición sin cambios no audita", total_auditoria(db) == total_antes)

            # Crea un embalaje de peso fijo.
            estado, embalaje = solicitar(
                "POST",
                "/api/v1/embalajes",
                token_admin,
                {"nombre": f"Caja QA {sufijo}", "kg_por_caja": "12.50"},
            )
            # Debe indicar que no corresponde a granel.
            comprobar(
                "E1 — alta de embalaje fijo",
                estado == 201
                and embalaje["kg_por_caja"] == "12.50"
                and embalaje["es_granel"] is False,
            )
            # La salida contiene únicamente los cinco campos públicos.
            comprobar(
                "E2 — campos públicos",
                set(embalaje) == {"id", "nombre", "kg_por_caja", "activo", "es_granel"},
            )
            # Crea otro embalaje enviando null explícito para granel.
            estado, granel = solicitar(
                "POST",
                "/api/v1/embalajes",
                token_admin,
                {"nombre": f"Granel QA {sufijo}", "kg_por_caja": None},
            )
            # El servidor devuelve null y el indicador calculado verdadero.
            comprobar(
                "E3 — alta a granel",
                estado == 201 and granel["kg_por_caja"] is None and granel["es_granel"] is True,
            )
            # Omitir completamente el campo requerido es distinto de enviar null.
            comprobar(
                "E4 — kilos omitidos 422",
                solicitar(
                    "POST",
                    "/api/v1/embalajes",
                    token_admin,
                    {"nombre": f"Sin kilos {sufijo}"},
                )[0]
                == 422,
            )
            # Los kilos fijos no aceptan cero, negativos, exceso de decimales ni booleanos.
            for kilos in (0, -1, "1.001", False, "1000000.00"):
                # Usa un nombre distinto para aislar la validación del peso.
                estado, _ = solicitar(
                    "POST",
                    "/api/v1/embalajes",
                    token_admin,
                    {"nombre": f"Inválido {uuid.uuid4().hex[:5]}", "kg_por_caja": kilos},
                )
                # La entrada inválida produce 422.
                comprobar(f"E5 — kilos inválidos {kilos!r}", estado == 422)
            # Convierte el embalaje fijo a granel usando null explícito.
            estado, convertido = solicitar(
                "PUT",
                f"/api/v1/embalajes/{embalaje['id']}",
                token_admin,
                {"kg_por_caja": None},
            )
            # Comprueba que null no fue descartado por el servicio.
            comprobar(
                "E6 — conversión a granel",
                estado == 200 and convertido["kg_por_caja"] is None and convertido["es_granel"] is True,
            )
            # Convierte nuevamente el mismo registro a peso fijo.
            estado, convertido = solicitar(
                "PUT",
                f"/api/v1/embalajes/{embalaje['id']}",
                token_admin,
                {"kg_por_caja": "15.75"},
            )
            # Debe volver a marcarlo como no granel.
            comprobar(
                "E7 — conversión a peso fijo",
                estado == 200 and convertido["kg_por_caja"] == "15.75" and convertido["es_granel"] is False,
            )
            # El mismo nombre con otras mayúsculas produce conflicto.
            comprobar(
                "E8 — duplicado 409",
                solicitar(
                    "POST",
                    "/api/v1/embalajes",
                    token_admin,
                    {"nombre": f"CAJA QA {sufijo}", "kg_por_caja": None},
                )[0]
                == 409,
            )
            # Desactiva el embalaje sin eliminar su identidad ni sus conversiones anteriores.
            estado, desactivado = solicitar(
                "PUT",
                f"/api/v1/embalajes/{embalaje['id']}",
                token_admin,
                {"activo": False},
            )
            # El cambio de estado debe quedar visible en la respuesta.
            comprobar("E9 — desactivar", estado == 200 and desactivado["activo"] is False)
            # Los filtros deben excluirlo de activos e incluirlo entre inactivos.
            _, embalajes_activos = solicitar("GET", "/api/v1/embalajes?activo=true", token_admin)
            _, embalajes_inactivos = solicitar("GET", "/api/v1/embalajes?activo=false", token_admin)
            comprobar("E10 — filtro activo", all(item["id"] != embalaje["id"] for item in embalajes_activos))
            comprobar("E10 — filtro inactivo", any(item["id"] == embalaje["id"] for item in embalajes_inactivos))
            # Reactiva el mismo registro para comprobar ambos sentidos del cambio lógico.
            estado, reactivado = solicitar(
                "PUT",
                f"/api/v1/embalajes/{embalaje['id']}",
                token_admin,
                {"activo": True},
            )
            # La reactivación conserva kilos e identidad.
            comprobar(
                "E11 — reactivar",
                estado == 200
                and reactivado["activo"] is True
                and reactivado["kg_por_caja"] == "15.75",
            )
            # Deben existir INSERT y cuatro UPDATE: dos conversiones y dos estados.
            eventos_embalaje = eventos(db, "embalajes", embalaje["id"])
            comprobar(
                "E12 — auditoría completa",
                [evento.accion for evento in eventos_embalaje]
                == [
                    AccionAuditoria.INSERT,
                    AccionAuditoria.UPDATE,
                    AccionAuditoria.UPDATE,
                    AccionAuditoria.UPDATE,
                    AccionAuditoria.UPDATE,
                ],
            )

            # Comprueba que un fallo de auditoría revierte también el catálogo.
            nombre_fallido = f"Fallo auditoría {sufijo}"
            filas_antes = db.scalar(select(func.count()).select_from(TipoBandeja))
            # Sustituye únicamente el registrador usado por el servicio de bandejas.
            with patch(
                "app.services.tipo_bandeja.registrar_auditoria",
                side_effect=RuntimeError("fallo simulado"),
            ):
                # La excepción debe propagarse después del rollback del servicio.
                try:
                    solicitar(
                        "POST",
                        "/api/v1/tipos-bandeja",
                        token_admin,
                        {"nombre": nombre_fallido, "peso_tara_kg": "1.00"},
                    )
                # Confirma que se obtuvo exactamente el fallo simulado.
                except RuntimeError as error:
                    # El mensaje permite distinguirlo de otro error inesperado.
                    comprobar("A1 — fallo de auditoría propagado", str(error) == "fallo simulado")
                # Llegar aquí significaría que la API ocultó un fallo atómico.
                else:
                    # Registra explícitamente el incumplimiento.
                    comprobar("A1 — fallo de auditoría propagado", False)
            # El alta fallida no debe quedar persistida dentro del escenario.
            comprobar(
                "A2 — alta revertida",
                db.scalar(select(func.count()).select_from(TipoBandeja)) == filas_antes
                and db.scalar(select(TipoBandeja).where(TipoBandeja.nombre == nombre_fallido)) is None,
            )


# Ejecuta todo y compara el estado final con el inicial.
def main() -> int:
    global fallas
    # Huella antes de cualquier escenario (lectura sin transacción abierta).
    with engine.connect() as conexion:
        inicial = huellas(conexion)
    # Dependencias de la app antes de las pruebas.
    dependencias = dict(app.dependency_overrides)
    # Un error inesperado cuenta como falla y muestra su ubicación.
    try:
        probar_mantenimientos()
    except Exception:
        fallas += 1
        print("FALLA probar_mantenimientos: error inesperado", flush=True)
        traceback.print_exc()
    # Al salir del escenario se revirtieron usuarios, catálogos y auditorías temporales.
    with engine.connect() as conexion:
        final = huellas(conexion)
    # Compara contenido, no solo cantidades: un UPDATE no revertido también se detecta.
    comprobar("Final — tablas idénticas al inicio (sin residuos)", final == inicial)
    comprobar("Final — dependencias de la app restauradas", app.dependency_overrides == dependencias)
    # Resumen con el mismo formato de las demás pruebas, para el acta.
    print(f"\nCOMPROBACIONES: {comprobaciones} FALLAS: {fallas}")
    print("RESULTADO:", "todas las pruebas pasaron" if fallas == 0 else f"{fallas} prueba(s) fallaron")
    # Código de salida distinto de cero si hubo fallas.
    return 1 if fallas else 0


# No ejecuta nada al importar el módulo.
if __name__ == "__main__":
    sys.exit(main())
