"""HU11 — Pruebas reproducibles de las opciones de formularios para recepción (casos O1–O20).

Ejecutar desde sistema/: docker compose exec backend python -m tests.probar_opciones
Todo corre dentro de una transacción externa que siempre se revierte: los datos
de prueba se insertan como savepoints y no se borra ninguna fila para limpiar.
Importar este módulo no ejecuta pruebas.
"""

# Ejecuta solicitudes ASGI en memoria sin instalar un cliente HTTP.
import asyncio
# Calcula huellas del contenido de las tablas sin imprimir sus datos.
import hashlib
# Lee las respuestas JSON y serializa filas para las huellas.
import json
# Devuelve un código de salida distinto de cero si algo falla.
import sys
# Muestra la ubicación de errores inesperados sin contarlos como aprobados.
import traceback
# Genera nombres, ids y RUT ficticios que no chocan con datos existentes.
import uuid
# Administra la apertura y la limpieza del escenario aislado.
from contextlib import contextmanager
# Separa la ruta y la query string al armar la solicitud ASGI.
from urllib.parse import quote, urlsplit

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
# Modelos que se leen y se preparan para los casos.
from app.models.auditoria import Auditoria
from app.models.calidad import Calidad
from app.models.especie import Especie
from app.models.productor import Productor
from app.models.sistema_productivo import SistemaProductivo
from app.models.tipo_bandeja import TipoBandeja
from app.models.usuario import RolUsuario, Usuario, UsuarioRol
from app.models.variedad import Variedad

# Tablas cuyo contenido debe quedar idéntico al terminar (O19).
TABLAS = ("usuarios", "usuario_roles", "auditoria", "especies", "variedades", "calidades", "sistemas_productivos", "productores", "tipos_bandeja")
# Prefijo común de las seis rutas de HU11.
BASE = "/api/v1/opciones"
# Campos que debe devolver cada lista de catálogo (O13).
CAMPOS_OPCION = {"id", "nombre"}
# Campos que debe devolver la lista de tipos de bandeja (O20).
CAMPOS_BANDEJA = {"id", "nombre", "peso_tara_kg"}
# Campos que debe devolver el buscador de productores (O13).
CAMPOS_PRODUCTOR = {"id", "rut", "razon_social"}

# Contadores globales de la ejecución.
comprobaciones = 0
fallas = 0


# Registra una comprobación con el mismo formato de las demás pruebas del proyecto.
def comprobar(nombre: str, condicion: bool) -> None:
    global comprobaciones, fallas
    # Cuenta todas las comprobaciones ejecutadas.
    comprobaciones += 1
    # Cuenta las que fallan.
    if not condicion:
        fallas += 1
    # Muestra cada caso para poder copiarlo al acta.
    print(("OK    " if condicion else "FALLA ") + nombre, flush=True)


# Calcula filas y huella SHA-256 de cada tabla (sin imprimir su contenido).
def huellas(conexion) -> dict:
    # Guarda (cantidad, huella) por tabla.
    salida = {}
    # Recorre las tablas que deben conservarse.
    for tabla in TABLAS:
        # Lee todas las filas como diccionarios.
        filas = conexion.execute(text("SELECT * FROM " + tabla)).mappings().all()
        # Ordena la serialización para que la huella no dependa del orden de lectura.
        serial = sorted(json.dumps(dict(f), sort_keys=True, default=str) for f in filas)
        # Guarda cantidad y huella del contenido.
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
        # Los commit de la preparación se convierten en savepoints de esta transacción.
        db = Session(bind=conexion, autoflush=False, join_transaction_mode="create_savepoint")
        try:
            # Entrega la sesión al escenario.
            yield db
            # El escenario no debe haber cerrado la transacción externa.
            comprobar("Aislamiento — transacción externa activa", externa.is_active and conexion.in_transaction())
        finally:
            # Cierra la sesión.
            db.close()
            # Revierte todo lo insertado por el escenario.
            if externa.is_active:
                externa.rollback()


# Crea un usuario temporal con un rol, dentro del escenario aislado.
def crear_actor(db: Session, rol: RolUsuario) -> Usuario:
    # Usuario con nombre único para no chocar con los existentes.
    actor = Usuario(
        id=str(uuid.uuid4()),  # Id conocido antes del flush.
        nombre_usuario="qa_hu11_" + uuid.uuid4().hex[:20],  # Respeta el límite de 50 caracteres.
        nombre_completo="Actor QA HU11",  # Nombre inventado.
        password_hash="ficticio_no_sirve_para_login",  # No es una contraseña real.
        activo=True,  # Habilitado para pasar get_current_user.
        roles_asignados=[UsuarioRol(rol=rol)],  # Rol que se quiere probar.
    )  # Finaliza la preparación del actor.
    # Lo agrega a la sesión del escenario.
    db.add(actor)
    # Devuelve el actor para crear su token.
    return actor


# Calcula el dígito verificador (módulo 11) de un cuerpo de RUT.
def digito_verificador(cuerpo: str) -> str:
    # Multiplica los dígitos de derecha a izquierda por 2, 3, 4, 5, 6, 7 y vuelve a 2.
    suma = sum(int(digito) * (2 + indice % 6) for indice, digito in enumerate(reversed(cuerpo)))
    # Resto según el algoritmo chileno.
    resto = 11 - suma % 11
    # 11 se escribe 0 y 10 se escribe K.
    return "0" if resto == 11 else "K" if resto == 10 else str(resto)


# Genera un RUT válido de 8 dígitos que no exista en la base ni en esta prueba.
def rut_libre(db: Session, usados: set[str]) -> str:
    # Limita los intentos por si la tabla estuviera muy llena.
    for _ in range(100):
        # Cuerpo de 8 dígitos que no empieza con 0.
        cuerpo = str(10_000_000 + uuid.uuid4().int % 80_000_000)
        # RUT en el formato que guarda la aplicación (cuerpo-DV, sin puntos).
        rut = cuerpo + "-" + digito_verificador(cuerpo)
        # Lo acepta si nadie lo usa.
        if rut not in usados and db.scalar(select(Productor.id).where(Productor.rut == rut)) is None:
            # Lo reserva para los siguientes productores de la prueba.
            usados.add(rut)
            # Devuelve el RUT libre.
            return rut
    # Si no encuentra uno libre, la precondición falla de forma visible.
    raise RuntimeError("No se pudo obtener un RUT de prueba libre")


# Envía una solicitud a la aplicación completa en memoria (sin red).
async def _solicitar(metodo: str, ruta: str, token: str | None) -> tuple[int, object]:
    # Separa ruta y parámetros.
    partes = urlsplit(ruta)
    # Cabecera mínima de una solicitud HTTP.
    cabeceras = [(b"host", b"qa-hu11")]
    # Agrega el token solo cuando el caso lo usa.
    if token:
        cabeceras.append((b"authorization", ("Bearer " + token).encode()))
    # Descripción ASGI de la solicitud.
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",  # Interfaz utilizada.
        "method": metodo, "scheme": "http", "path": partes.path,  # Método y ruta.
        "raw_path": partes.path.encode(), "query_string": partes.query.encode(),  # Parámetros de la URL.
        "root_path": "", "headers": cabeceras, "client": ("127.0.0.1", 1), "server": ("qa-hu11", 80),  # Contexto HTTP.
    }  # Finaliza la descripción de la solicitud.
    # Mensajes que devuelve la aplicación.
    mensajes = []
    # Controla que el cuerpo (vacío) se entregue una sola vez.
    entregado = False

    # Entrega el cuerpo vacío una sola vez.
    async def receive():
        nonlocal entregado
        # La segunda lectura indica que el cliente terminó.
        if entregado:
            return {"type": "http.disconnect"}
        # Marca la única entrega.
        entregado = True
        # Las rutas de HU11 no reciben cuerpo.
        return {"type": "http.request", "body": b"", "more_body": False}

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
def solicitar(metodo: str, ruta: str, token: str | None = None) -> tuple[int, object]:
    return asyncio.run(_solicitar(metodo, ruta, token))


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


# Ids devueltos por una lista, en el orden recibido.
def ids(lista: list) -> list[int]:
    return [elemento["id"] for elemento in lista]


# Comprueba en la base que todos los ids devueltos correspondan a registros activos.
def todos_activos(db: Session, modelo, lista: list) -> bool:
    # Una lista vacía no tiene inactivos.
    if not lista:
        return True
    # Cuenta cuántos de los ids devueltos están inactivos.
    inactivos = db.scalar(select(func.count()).select_from(modelo).where(modelo.id.in_(ids(lista)), modelo.activo == False))  # noqa: E712
    # Debe ser cero.
    return inactivos == 0


# Escenario único: prepara catálogos y productores, y recorre los casos O1–O18.
def probar_opciones() -> None:
    # Sufijo que distingue los datos de esta ejecución.
    sufijo = uuid.uuid4().hex[:8]
    with aislado() as db:
        # Actores con cada uno de los cuatro roles.
        actores = {rol: crear_actor(db, rol) for rol in RolUsuario}

        # Especies: A y B activas (O2), una inactiva (O1 y O3).
        especie_a = Especie(nombre=f"QA Alfa {sufijo}", activo=True)
        especie_b = Especie(nombre=f"QA Beta {sufijo}", activo=True)
        especie_inactiva = Especie(nombre=f"QA Gamma {sufijo}", activo=False)
        db.add_all([especie_a, especie_b, especie_inactiva])
        # Asigna los ids de las especies antes de crear sus variedades.
        db.flush()

        # Variedades: dos activas y una inactiva de A, una activa de B y una activa de la especie inactiva.
        var_a2 = Variedad(especie_id=especie_a.id, nombre=f"QA Variedad B {sufijo}", activo=True)
        var_a1 = Variedad(especie_id=especie_a.id, nombre=f"QA Variedad A {sufijo}", activo=True)
        var_a_inactiva = Variedad(especie_id=especie_a.id, nombre=f"QA Variedad C {sufijo}", activo=False)
        var_b = Variedad(especie_id=especie_b.id, nombre=f"QA Variedad B1 {sufijo}", activo=True)
        var_de_inactiva = Variedad(especie_id=especie_inactiva.id, nombre=f"QA Variedad G {sufijo}", activo=True)
        db.add_all([var_a2, var_a1, var_a_inactiva, var_b, var_de_inactiva])

        # Calidades y sistemas productivos: dos activos (en orden inverso al alfabético) y uno inactivo.
        calidades = [Calidad(nombre=f"QA Calidad B {sufijo}", activo=True), Calidad(nombre=f"QA Calidad A {sufijo}", activo=True), Calidad(nombre=f"QA Calidad C {sufijo}", activo=False)]
        sistemas = [SistemaProductivo(nombre=f"QA Sistema B {sufijo}", activo=True), SistemaProductivo(nombre=f"QA Sistema A {sufijo}", activo=True), SistemaProductivo(nombre=f"QA Sistema C {sufijo}", activo=False)]
        db.add_all(calidades + sistemas)

        # Tipos de bandeja (HU10): dos activos (en orden inverso al alfabético) y uno inactivo.
        bandejas = [TipoBandeja(nombre=f"QA Bandeja B {sufijo}", peso_tara_kg="1.25", activo=True), TipoBandeja(nombre=f"QA Bandeja A {sufijo}", peso_tara_kg="0.80", activo=True), TipoBandeja(nombre=f"QA Bandeja C {sufijo}", peso_tara_kg="2.00", activo=False)]
        db.add_all(bandejas)

        # Productores: uno activo y uno inactivo con la misma marca en la razón social.
        marca = "qaopc" + sufijo
        usados: set[str] = set()
        productor = Productor(rut=rut_libre(db, usados), razon_social=f"Agricola {marca} Sur", direccion="Calle QA 123", telefono="+56900000000", activo=True)
        productor_inactivo = Productor(rut=rut_libre(db, usados), razon_social=f"Agricola {marca} Norte", activo=False)
        # 21 productores activos con otra marca, para el tope de 20 resultados (O12).
        marca_muchos = "qamuchos" + sufijo
        muchos = [Productor(rut=rut_libre(db, usados), razon_social=f"Productor {marca_muchos} {n:02d}", activo=True) for n in range(21, 0, -1)]
        db.add_all([productor, productor_inactivo] + muchos)
        # Confirma solo el savepoint de preparación.
        db.commit()

        # Tokens: el JWT dice el rol, pero la autorización lo vuelve a leer en la base.
        tokens = {rol: create_access_token(actor.nombre_usuario, [rol.value]) for rol, actor in actores.items()}
        admin = tokens[RolUsuario.ADMINISTRADOR]
        recepcion = tokens[RolUsuario.OPERADOR_RECEPCION]

        # Eventos de auditoría antes de las lecturas (O18).
        auditoria_antes = db.scalar(select(func.count()).select_from(Auditoria))

        with api_con_sesion(db):
            # O1: especies activas; la inactiva no aparece.
            estado, especies = solicitar("GET", f"{BASE}/especies", recepcion)
            comprobar("O1 — especies 200", estado == 200)
            comprobar("O1 — aparecen las especies activas", {especie_a.id, especie_b.id} <= set(ids(especies)))
            comprobar("O1 — no aparece la especie inactiva", especie_inactiva.id not in ids(especies))
            comprobar("O1 — todas las devueltas están activas", todos_activos(db, Especie, especies))
            comprobar("O1 — orden por nombre (Alfa antes que Beta)", ids(especies).index(especie_a.id) < ids(especies).index(especie_b.id))

            # O2: variedades de A; solo las activas de A y en orden por nombre.
            estado, variedades = solicitar("GET", f"{BASE}/variedades?especie_id={especie_a.id}", recepcion)
            comprobar("O2 — variedades de A 200", estado == 200)
            comprobar("O2 — solo las activas de A, ordenadas por nombre", ids(variedades) == [var_a1.id, var_a2.id])
            comprobar("O2 — sin la inactiva de A ni la de B", var_a_inactiva.id not in ids(variedades) and var_b.id not in ids(variedades))

            # O3: especie inactiva con una variedad activa → lista vacía.
            estado, variedades = solicitar("GET", f"{BASE}/variedades?especie_id={especie_inactiva.id}", recepcion)
            comprobar("O3 — especie inactiva devuelve []", estado == 200 and variedades == [])

            # O4: especie inexistente → 200 y lista vacía.
            inexistente = (db.scalar(select(func.max(Especie.id))) or 0) + 1000
            estado, variedades = solicitar("GET", f"{BASE}/variedades?especie_id={inexistente}", recepcion)
            comprobar("O4 — especie inexistente 200 y []", estado == 200 and variedades == [])

            # O5: especie_id ausente, cero, negativo o no numérico → 422.
            for consulta in ("", "?especie_id=0", "?especie_id=-1", "?especie_id=abc"):
                estado, _ = solicitar("GET", f"{BASE}/variedades{consulta}", recepcion)
                comprobar(f"O5 — variedades{consulta or ' sin especie_id'} 422", estado == 422)

            # O6: calidades y sistemas productivos; solo activos y ordenados por nombre.
            for nombre, ruta, modelo, filas in (("calidades", "calidades", Calidad, calidades), ("sistemas productivos", "sistemas-productivos", SistemaProductivo, sistemas)):
                estado, lista = solicitar("GET", f"{BASE}/{ruta}", recepcion)
                recibidos = ids(lista)
                comprobar(f"O6 — {nombre} 200", estado == 200)
                comprobar(f"O6 — {nombre}: aparecen los activos", {filas[0].id, filas[1].id} <= set(recibidos))
                comprobar(f"O6 — {nombre}: no aparece el inactivo", filas[2].id not in recibidos)
                comprobar(f"O6 — {nombre}: todos los devueltos están activos", todos_activos(db, modelo, lista))
                comprobar(f"O6 — {nombre}: orden por nombre (A antes que B)", recibidos.index(filas[1].id) < recibidos.index(filas[0].id))

            # O7: buscar por RUT con puntos, sin puntos y completo con guion.
            cuerpo, dv = productor.rut.split("-")
            con_puntos = f"{cuerpo[:2]}.{cuerpo[2:5]}"
            completo = f"{cuerpo[:2]}.{cuerpo[2:5]}.{cuerpo[5:]}-{dv.lower()}"
            for texto in (con_puntos, cuerpo[:5], productor.rut, completo):
                estado, lista = solicitar("GET", f"{BASE}/productores?buscar={quote(texto)}", recepcion)
                comprobar(f"O7 — RUT '{texto}' encuentra al productor", estado == 200 and productor.id in ids(lista))

            # O8: buscar por parte de la razón social; el inactivo no aparece.
            estado, lista = solicitar("GET", f"{BASE}/productores?buscar={marca}", recepcion)
            comprobar("O8 — razón social parcial encuentra al activo", estado == 200 and ids(lista) == [productor.id])
            comprobar("O8 — el productor inactivo no aparece", productor_inactivo.id not in ids(lista))

            # O9: distinta capitalización; el resultado depende de la collation de razon_social.
            collation = db.scalar(text("SELECT collation_name FROM sys.columns WHERE object_id = OBJECT_ID('productores') AND name = 'razon_social'"))
            estado, lista = solicitar("GET", f"{BASE}/productores?buscar={marca.upper()}", recepcion)
            encontrado = productor.id in ids(lista)
            print(f"      O9 observado: collation {collation}; búsqueda en mayúsculas {'encuentra' if encontrado else 'no encuentra'} al productor", flush=True)
            comprobar("O9 — capitalización según la collation", encontrado == ("_CI_" in (collation or "")))

            # O10: % y _ no funcionan como comodines (autoescape).
            for texto in ("%%", "__", "%_"):
                estado, lista = solicitar("GET", f"{BASE}/productores?buscar={quote(texto)}", recepcion)
                comprobar(f"O10 — '{texto}' solo devuelve razones sociales que lo contienen", estado == 200 and all(texto in p["razon_social"] for p in lista))

            # O11: menos de 2 caracteres (también tras quitar espacios) → lista vacía.
            for texto in ("a", " a ", ""):
                estado, lista = solicitar("GET", f"{BASE}/productores?buscar={quote(texto)}", recepcion)
                comprobar(f"O11 — buscar '{texto}' devuelve []", estado == 200 and lista == [])

            # O12: 21 coincidencias → máximo 20, ordenadas por razón social.
            estado, lista = solicitar("GET", f"{BASE}/productores?buscar={marca_muchos}", recepcion)
            esperados = sorted(muchos, key=lambda p: p.razon_social)[:20]
            comprobar("O12 — máximo 20 resultados", estado == 200 and len(lista) == 20)
            comprobar("O12 — ordenados por razón social", ids(lista) == [p.id for p in esperados])

            # O12b: buscar sin el parámetro o con más de 50 caracteres → 422.
            comprobar("O12 — productores sin buscar 422", solicitar("GET", f"{BASE}/productores", recepcion)[0] == 422)
            comprobar("O12 — buscar de 51 caracteres 422", solicitar("GET", f"{BASE}/productores?buscar={'x' * 51}", recepcion)[0] == 422)

            # O13: las respuestas tienen solo los campos de los schemas.
            for ruta in ("especies", f"variedades?especie_id={especie_a.id}", "calidades", "sistemas-productivos"):
                _, lista = solicitar("GET", f"{BASE}/{ruta}", recepcion)
                comprobar(f"O13 — {ruta.split('?')[0]}: solo id y nombre", bool(lista) and all(set(e) == CAMPOS_OPCION for e in lista))
            _, lista = solicitar("GET", f"{BASE}/productores?buscar={marca}", recepcion)
            comprobar("O13 — productores: solo id, rut y razon_social (sin activo, dirección ni teléfono)", bool(lista) and all(set(p) == CAMPOS_PRODUCTOR for p in lista))

            # O20: tipos de bandeja activos, ordenados por nombre y con su tara exacta (HU11 paso 8).
            estado, lista = solicitar("GET", f"{BASE}/tipos-bandeja", recepcion)
            recibidos = ids(lista)
            comprobar("O20 — tipos de bandeja 200", estado == 200)
            comprobar("O20 — aparecen las bandejas activas", {bandejas[0].id, bandejas[1].id} <= set(recibidos))
            comprobar("O20 — no aparece la bandeja inactiva (criterio 2 de HU10)", bandejas[2].id not in recibidos)
            comprobar("O20 — todas las devueltas están activas", todos_activos(db, TipoBandeja, lista))
            comprobar("O20 — orden por nombre (A antes que B)", recibidos.index(bandejas[1].id) < recibidos.index(bandejas[0].id))
            comprobar("O20 — solo id, nombre y peso_tara_kg", bool(lista) and all(set(b) == CAMPOS_BANDEJA for b in lista))
            # La tara viaja como texto decimal para no perder precisión en el cálculo de kilos netos.
            tara = next(b["peso_tara_kg"] for b in lista if b["id"] == bandejas[1].id)
            comprobar("O20 — tara exacta como texto decimal ('0.80')", tara == "0.80")

            # Rutas válidas de HU11 para los casos de permisos.
            rutas = [f"{BASE}/especies", f"{BASE}/variedades?especie_id={especie_a.id}", f"{BASE}/calidades", f"{BASE}/sistemas-productivos", f"{BASE}/productores?buscar={marca}", f"{BASE}/tipos-bandeja"]

            # O14: sin token, o con un token inválido → 401.
            for ruta in rutas:
                comprobar(f"O14 — sin token 401 {urlsplit(ruta).path}", solicitar("GET", ruta)[0] == 401)
                comprobar(f"O14 — token inválido 401 {urlsplit(ruta).path}", solicitar("GET", ruta, "token_invalido")[0] == 401)

            # O15: gerencia y operador de proceso → 403.
            for rol in (RolUsuario.GERENCIA, RolUsuario.OPERADOR_PROCESO):
                for ruta in rutas:
                    comprobar(f"O15 — {rol.value} 403 {urlsplit(ruta).path}", solicitar("GET", ruta, tokens[rol])[0] == 403)
            # O15: un JWT que dice operador_recepcion no sirve si la base dice gerencia.
            falso = create_access_token(actores[RolUsuario.GERENCIA].nombre_usuario, [RolUsuario.OPERADOR_RECEPCION.value])
            for ruta in rutas:
                comprobar(f"O15 — rol del JWT ignorado 403 {urlsplit(ruta).path}", solicitar("GET", ruta, falso)[0] == 403)

            # O16: operador de recepción y administrador → 200.
            for nombre, token in (("operador_recepcion", recepcion), ("administrador", admin)):
                for ruta in rutas:
                    comprobar(f"O16 — {nombre} 200 {urlsplit(ruta).path}", solicitar("GET", ruta, token)[0] == 200)

            # O17: POST, PUT y DELETE no existen → 405.
            for metodo in ("POST", "PUT", "DELETE"):
                for ruta in rutas:
                    comprobar(f"O17 — {metodo} 405 {urlsplit(ruta).path}", solicitar(metodo, ruta, admin)[0] == 405)

        # O18: ninguna lectura escribió en auditoría.
        comprobar("O18 — sin eventos de auditoría nuevos", db.scalar(select(func.count()).select_from(Auditoria)) == auditoria_antes)


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
        probar_opciones()
    except Exception:
        fallas += 1
        print("FALLA probar_opciones: error inesperado", flush=True)
        traceback.print_exc()
    # O19: nada quedó en la base y la app volvió a su estado normal.
    with engine.connect() as conexion:
        final = huellas(conexion)
    comprobar("O19 — tablas idénticas al inicio (sin filas residuales)", final == inicial)
    comprobar("O19 — dependencias de la app restauradas", app.dependency_overrides == dependencias)
    # Resumen para el acta.
    print(f"\nCOMPROBACIONES: {comprobaciones} FALLAS: {fallas}")
    print("RESULTADO:", "todas las pruebas pasaron" if fallas == 0 else f"{fallas} prueba(s) fallaron")
    # Código de salida para la terminal.
    return 1 if fallas else 0


# No ejecuta nada al importar el módulo.
if __name__ == "__main__":
    sys.exit(main())
