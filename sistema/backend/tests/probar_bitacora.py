"""HU22: prueba reproducible de la consulta de la bitácora.

Ejecutar desde sistema/: docker compose exec -T backend python -m tests.probar_bitacora
Todas las filas temporales quedan dentro de una transacción externa revertida.
Los eventos llevan fechas de 2031 para no cruzarse con los datos reales de cada base.
"""

# Serializa los valores de la auditoría y las respuestas.
import json
# Imprime el detalle de un error inesperado.
import traceback
# Fechas exactas de los eventos, en UTC.
from datetime import datetime

# Cuenta filas.
from sqlalchemy import func, select

# Conexión a la base.
from app.core.database import engine
# Genera un token con un rol que la base no respalda.
from app.core.security import create_access_token
# Aplicación real que reciben las peticiones.
from app.main import app
# Modelo de la auditoría y sus acciones.
from app.models.auditoria import AccionAuditoria, Auditoria
# Roles de los actores.
from app.models.usuario import RolUsuario
# Reutiliza el aislamiento, los actores y las peticiones de las pruebas de tarjas.
from tests import probar_tarjas as base
from tests.probar_tarjas import aislado, api_con_sesion, comprobar, crear_actor, solicitar

# Ruta base del módulo.
BASE = "/api/v1/auditoria"
# Rutas de consulta protegidas.
RUTAS = (BASE, f"{BASE}/usuarios", f"{BASE}/tablas")
# Rango que contiene todos los eventos del escenario y ningún evento real.
VENTANA = "fecha_desde=2031-01-01&fecha_hasta=2031-12-31"
# Cantidad de eventos del escenario.
EVENTOS_ESCENARIO = 6


# Crea un evento con fecha fija, sin pasar por el servicio que la calcula.
def evento(actor, tabla: str, registro: str, accion: AccionAuditoria, fecha: datetime, antes=None, despues=None, motivo=None) -> Auditoria:
    # Serializa las instantáneas igual que el servicio de HU21.
    return Auditoria(
        usuario_id=actor.id,  # Responsable.
        tabla=tabla,  # Tabla afectada.
        registro_id=registro,  # Identifica el evento en las comprobaciones.
        accion=accion,  # Operación.
        valores_antes=None if antes is None else json.dumps(antes),  # Estado previo.
        valores_despues=None if despues is None else json.dumps(despues),  # Estado posterior.
        motivo=motivo,  # Justificación.
        fecha_hora=fecha,  # Instante en UTC.
    )  # Finaliza el evento.


# Crea los seis eventos, en verano y en invierno de Chile, justo en los límites del día.
def crear_eventos(db, admin, gerencia) -> None:
    # Instantánea con credenciales, cambios reales y valores que no son cambios.
    antes_usuario = {
        "password_hash": "$2b$secreto",  # Nunca debe llegar a la respuesta.
        "activo": False,  # Booleano.
        "nombre_completo": "QA Antes",  # Texto.
        "kilos": "5.00",  # Misma cantidad escrita distinto: no es un cambio.
        "codigo": "007",  # Texto que parece número.
        "roles": ["gerencia"],  # Lista.
        "estado": "RECEPCIONADA",  # Se traduce.
        "razon_social": "PROCESADA",  # Misma palabra en otro campo: no se traduce.
        "cantidad_cajas": "40.00",  # Campo conocido por HU23.
        "tara_kg": "1.20",  # Cantidad sin formato propio.
        "impresa_en": "2031-07-01 03:30:00.840000",  # Fecha y hora en UTC, sin zona.
        "fecha_recepcion": "2031-06-30",  # Fecha sin hora.
        "nombre_raro": "1e99999999999999999999",  # Parece cantidad, pero no cabe en Decimal.
        "texto_fecha": "2026-13-45 99:99:99",  # Parece fecha, pero no existe.
        "igual": "x",  # No cambia.
        "solo_antes": "a",  # Campo que desapareció.
    }
    despues_usuario = {
        "password_hash": "$2b$nuevo",  # Nunca debe llegar a la respuesta.
        "activo": True,  # Booleano.
        "nombre_completo": "QA Después",  # Texto.
        "kilos": "5",  # Misma cantidad escrita distinto: no es un cambio.
        "codigo": "7",  # Texto que parece número.
        "roles": ["gerencia", "administrador"],  # Lista.
        "estado": "PROCESADA",  # Se traduce.
        "razon_social": "Procesada",  # Misma palabra en otro campo: no se traduce.
        "cantidad_cajas": "38.50",  # Campo conocido por HU23.
        "tara_kg": "1.50",  # Cantidad sin formato propio.
        "impresa_en": "2031-07-01 03:31:00.000000+00:00",  # Fecha y hora en UTC, con zona.
        "fecha_recepcion": "2031-07-01",  # Fecha sin hora.
        "nombre_raro": "5",  # Parece cantidad.
        "texto_fecha": "0001-01-01 00:00:00",  # Fecha que no cabe al pasar a Chile.
        "igual": "x",  # No cambia.
        "solo_despues": "b",  # Campo que apareció.
    }
    # Agrega los eventos a la transacción.
    db.add_all(
        [
            # 00:00:00 del 04/11 en Chile (verano, UTC-3): primer instante del día.
            evento(admin, "tarjas", "ini-verano", AccionAuditoria.UPDATE, datetime(2031, 11, 4, 3, 0, 0), {"veces": 1}, {"veces": 1}, "Sin cambio de datos"),
            # 23:59:59 del 04/11 en Chile: último instante del día.
            evento(gerencia, "tarjas", "fin-verano", AccionAuditoria.INSERT, datetime(2031, 11, 5, 2, 59, 59), None, {"nombre": "QA creada", "activo": True}),
            # 00:00:00 del 05/11 en Chile: ya es otro día.
            evento(admin, "productores", "sig-verano", AccionAuditoria.UPDATE, datetime(2031, 11, 5, 3, 0, 0), {"nombre": "A"}, {"nombre": "B"}),
            # 23:59:59 del 03/11 en Chile: todavía es el día anterior.
            evento(admin, "productores", "ant-verano", AccionAuditoria.INSERT, datetime(2031, 11, 4, 2, 59, 59), None, {"nombre": "A"}),
            # 23:30 del 01/07 en Chile (invierno, UTC-4): con UTC-3 caería en otro día.
            evento(gerencia, "proceso_tarjas", "dentro-invierno", AccionAuditoria.DELETE, datetime(2031, 7, 2, 3, 30), {"kilos_procesados": "15.00"}, None),
            # 23:30 del 30/06 en Chile: con UTC-3 caería en el 01/07.
            evento(admin, "usuarios", "fuera-invierno", AccionAuditoria.UPDATE, datetime(2031, 7, 1, 3, 30), antes_usuario, despues_usuario, "QA bitácora"),
        ]
    )
    # Hace visibles las filas antes de llamar a la API.
    db.flush()


# Consulta y devuelve los registros encontrados.
def registros(token: str, consulta: str) -> set[str] | None:
    # Pide hasta 100 filas.
    estado, resultado = solicitar("GET", f"{BASE}?limite=100&{consulta}", token)
    # Un error no es un conjunto vacío.
    return {item["registro_id"] for item in resultado["items"]} if estado == 200 else None


# Criterio 3: solo gerencia y administrador, en todas las rutas.
def probar_roles(db) -> None:
    # Un actor por rol.
    _, token_admin = crear_actor(db, RolUsuario.ADMINISTRADOR)
    _, token_gerencia = crear_actor(db, RolUsuario.GERENCIA)
    recepcion, token_recepcion = crear_actor(db, RolUsuario.OPERADOR_RECEPCION)
    _, token_proceso = crear_actor(db, RolUsuario.OPERADOR_PROCESO)
    desactivado, token_desactivado = crear_actor(db, RolUsuario.GERENCIA)
    # El rol que cuenta es el de la base, no el del JWT.
    token_obsoleto = create_access_token(recepcion.nombre_usuario, [RolUsuario.GERENCIA.value])
    # Un usuario desactivado no entra aunque su token siga vigente.
    desactivado.activo = False
    db.flush()
    # Revisa cada ruta con cada actor.
    for ruta in RUTAS:
        # Parte final de la ruta, para leer el resultado.
        nombre = ruta.removeprefix("/api/v1")
        comprobar(f"Roles {nombre} - sin token 401", solicitar("GET", ruta)[0] == 401)
        comprobar(f"Roles {nombre} - recepción 403", solicitar("GET", ruta, token_recepcion)[0] == 403)
        comprobar(f"Roles {nombre} - proceso 403", solicitar("GET", ruta, token_proceso)[0] == 403)
        comprobar(f"Roles {nombre} - rol obsoleto del JWT 403", solicitar("GET", ruta, token_obsoleto)[0] == 403)
        comprobar(f"Roles {nombre} - desactivado 401", solicitar("GET", ruta, token_desactivado)[0] == 401)
        comprobar(f"Roles {nombre} - gerencia 200", solicitar("GET", ruta, token_gerencia)[0] == 200)
        comprobar(f"Roles {nombre} - administrador 200", solicitar("GET", ruta, token_admin)[0] == 200)


# Criterio 1: cada filtro por separado y combinados.
def probar_filtros(token: str, admin, gerencia) -> None:
    # Todos los eventos del escenario.
    todos = {"ini-verano", "fin-verano", "sig-verano", "ant-verano", "dentro-invierno", "fuera-invierno"}
    comprobar("Filtros - la ventana contiene el escenario", registros(token, VENTANA) == todos)
    # Por usuario.
    comprobar("Filtros - solo usuario gerencia", registros(token, f"{VENTANA}&usuario_id={gerencia.id}") == {"fin-verano", "dentro-invierno"})
    comprobar("Filtros - solo usuario admin", registros(token, f"{VENTANA}&usuario_id={admin.id}") == todos - {"fin-verano", "dentro-invierno"})
    # Por tabla.
    comprobar("Filtros - solo tabla tarjas", registros(token, f"{VENTANA}&tabla=tarjas") == {"ini-verano", "fin-verano"})
    comprobar("Filtros - tabla inexistente sin filas", registros(token, f"{VENTANA}&tabla=no_existe") == set())
    # Por acción.
    comprobar("Filtros - solo INSERT", registros(token, f"{VENTANA}&accion=INSERT") == {"fin-verano", "ant-verano"})
    comprobar("Filtros - solo UPDATE", registros(token, f"{VENTANA}&accion=UPDATE") == {"ini-verano", "sig-verano", "fuera-invierno"})
    comprobar("Filtros - solo DELETE", registros(token, f"{VENTANA}&accion=DELETE") == {"dentro-invierno"})
    # Combinados.
    comprobar("Filtros - usuario, tabla y acción", registros(token, f"{VENTANA}&usuario_id={admin.id}&tabla=productores&accion=UPDATE") == {"sig-verano"})
    comprobar("Filtros - sin coincidencias", registros(token, f"{VENTANA}&usuario_id={gerencia.id}&tabla=productores") == set())


# Criterio 1: los días son de Chile, con su horario de verano e invierno.
def probar_fechas(token: str, admin) -> None:
    # Verano: el día va de 03:00 a 02:59:59 UTC, con los dos extremos incluidos.
    comprobar("Fechas - verano, día completo", registros(token, "fecha_desde=2031-11-04&fecha_hasta=2031-11-04") == {"ini-verano", "fin-verano"})
    comprobar("Fechas - verano, día siguiente", registros(token, "fecha_desde=2031-11-05&fecha_hasta=2031-11-05") == {"sig-verano"})
    comprobar("Fechas - verano, día anterior", registros(token, "fecha_desde=2031-11-03&fecha_hasta=2031-11-03") == {"ant-verano"})
    # Invierno: el día va de 04:00 a 03:59:59 UTC.
    comprobar("Fechas - invierno, 23:30 sigue en el día", registros(token, "fecha_desde=2031-07-01&fecha_hasta=2031-07-01") == {"dentro-invierno"})
    comprobar("Fechas - invierno, 23:30 del día anterior", registros(token, "fecha_desde=2031-06-30&fecha_hasta=2031-06-30") == {"fuera-invierno"})
    # Cada límite también funciona solo.
    comprobar("Fechas - solo desde", registros(token, "fecha_desde=2031-11-05") == {"sig-verano"})
    comprobar("Fechas - solo hasta", registros(token, f"fecha_hasta=2031-06-30&usuario_id={admin.id}") == {"fuera-invierno"})


# Criterio 2: cada registro muestra qué cambió.
def probar_valores(token: str, admin, gerencia) -> None:
    # Pide el escenario una sola vez.
    estado, resultado = solicitar("GET", f"{BASE}?limite=100&{VENTANA}", token)
    # Ordena los eventos por el registro que los identifica.
    eventos = {item["registro_id"]: item for item in resultado["items"]} if estado == 200 else {}

    # Modificación: solo los campos que cambiaron, con su valor anterior y nuevo.
    usuario = eventos["fuera-invierno"]
    cambios = {cambio["campo"]: (cambio["antes"], cambio["despues"]) for cambio in usuario["cambios"]}
    comprobar("Valores - booleano con palabras", cambios.get("Activo") == ("No", "Sí"))
    comprobar("Valores - texto cambiado con nombre legible", cambios.get("Nombre completo") == ("QA Antes", "QA Después"))
    comprobar("Valores - lista separada por comas", cambios.get("Roles") == ("gerencia", "gerencia, administrador"))
    comprobar("Valores - estado con su texto visible", cambios.get("Estado") == ("Recepcionada", "Procesada"))
    comprobar("Valores - campo de HU23 con su nombre y formato", cambios.get("Cajas") == ("40", "38,5"))
    comprobar("Valores - 007 y 7 son textos distintos", cambios.get("Codigo") == ("007", "7"))
    comprobar("Valores - 5.00 y 5 no son un cambio", "Kilos" not in cambios)
    comprobar("Valores - lo que no cambió no aparece", "Igual" not in cambios)
    comprobar("Valores - campo solo en el valor anterior", cambios.get("Solo antes") == ("a", None))
    comprobar("Valores - campo solo en el valor nuevo", cambios.get("Solo despues") == (None, "b"))
    comprobar("Valores - solo el campo estado se traduce", cambios.get("Razon social") == ("PROCESADA", "Procesada"))
    comprobar("Valores - cantidad con coma", cambios.get("Tara kg") == ("1,20", "1,50"))
    comprobar("Valores - fecha y hora en Chile, con o sin zona", cambios.get("Impresa en") == ("30-06-2031 23:30:00", "30-06-2031 23:31:00"))
    comprobar("Valores - fecha sin hora, sin cambiar de día", cambios.get("Fecha recepcion") == ("30-06-2031", "01-07-2031"))
    comprobar("Valores - exponente imposible no rompe la página", cambios.get("Nombre raro") == ("1e99999999999999999999", "5"))
    comprobar("Valores - fecha imposible se muestra tal cual", cambios.get("Texto fecha") == ("2026-13-45 99:99:99", "0001-01-01 00:00:00"))
    comprobar("Valores - cantidad exacta de cambios", len(cambios) == 14)
    # Los datos de una modificación son los más recientes, con todos sus campos.
    datos_usuario = {dato["campo"]: dato["valor"] for dato in usuario["datos"]}
    comprobar("Valores - la modificación muestra sus datos nuevos", datos_usuario.get("Nombre completo") == "QA Después" and datos_usuario.get("Activo") == "Sí")
    comprobar("Valores - la modificación conserva lo que no cambió", datos_usuario.get("Igual") == "x" and datos_usuario.get("Kilos") == "5")
    # Sin cambios de datos, como un cambio de contraseña.
    sin_cambios = eventos["ini-verano"]
    comprobar("Valores - modificación sin cambios", sin_cambios["cambios"] == [] and sin_cambios["motivo"] == "Sin cambio de datos")
    # Creación: los valores nuevos.
    creado = eventos["fin-verano"]
    comprobar("Valores - INSERT sin cambios y con datos nuevos", creado["cambios"] == [] and creado["datos"] == [{"campo": "Nombre", "valor": "QA creada"}, {"campo": "Activo", "valor": "Sí"}])
    # Eliminación: los valores anteriores.
    eliminado = eventos["dentro-invierno"]
    comprobar("Valores - DELETE sin cambios y con datos anteriores", eliminado["cambios"] == [] and eliminado["datos"] == [{"campo": "Kilos procesados", "valor": "15,00"}])
    # Datos del evento.
    comprobar("Evento - motivo", usuario["motivo"] == "QA bitácora" and creado["motivo"] is None)
    comprobar("Evento - nombre del responsable", usuario["usuario"] == admin.nombre_completo and usuario["usuario_id"] == admin.id and creado["usuario_id"] == gerencia.id)
    comprobar("Evento - tabla y acción", usuario["tabla"] == "usuarios" and usuario["accion"] == "UPDATE")
    comprobar("Evento - fecha en UTC, sin zona", usuario["fecha_hora"] == "2031-07-01T03:30:00")

    # Credenciales: no aparecen en ninguna parte de la respuesta.
    texto = json.dumps(resultado)
    comprobar("Seguridad - sin password_hash", "password_hash" not in texto and "Password hash" not in texto)
    comprobar("Seguridad - sin el hash", "$2b$" not in texto)


# Paginación: orden, saltos y totales.
def probar_paginacion(token: str) -> None:
    # Reúne las cuatro páginas del escenario.
    paginas = [solicitar("GET", f"{BASE}?{VENTANA}&limite=2&offset={offset}", token)[1] for offset in (0, 2, 4, 6)]
    # Identificadores en el orden recibido.
    ids = [item["id"] for pagina in paginas for item in pagina["items"]]
    comprobar("Paginación - cada página respeta el límite", [len(pagina["items"]) for pagina in paginas] == [2, 2, 2, 0])
    comprobar("Paginación - sin repetidos entre páginas", len(set(ids)) == EVENTOS_ESCENARIO)
    comprobar("Paginación - primero lo más reciente", ids == sorted(ids, reverse=True))
    comprobar("Paginación - hay_mas hasta la penúltima", [pagina["hay_mas"] for pagina in paginas] == [True, True, False, False])
    comprobar("Paginación - total en todas las páginas", all(pagina["total"] == EVENTOS_ESCENARIO for pagina in paginas))
    comprobar("Paginación - informa su posición", paginas[1]["limite"] == 2 and paginas[1]["offset"] == 2)
    # Sin indicarlo, 50 filas.
    comprobar("Paginación - 50 por defecto", solicitar("GET", BASE, token)[1]["limite"] == 50)


# Entradas fuera de rango: nunca un error interno.
def probar_entradas(token: str) -> None:
    # Entradas que deben rechazarse.
    invalidas = {
        "límite cero": "limite=0",
        "límite sobre 100": "limite=101",
        "offset negativo": "offset=-1",
        "offset sobre INT": "offset=2147483648",
        "offset enorme": "offset=9223372036854775808",
        "fecha imposible": "fecha_desde=2026-13-45",
        "último día del calendario": "fecha_hasta=9999-12-31",
        "rango invertido": "fecha_desde=2031-11-05&fecha_hasta=2031-11-04",
        "acción inexistente": "accion=LOGIN",
        "tabla muy larga": "tabla=" + "x" * 51,
        "usuario muy largo": "usuario_id=" + "x" * 37,
    }
    # Revisa cada una.
    for nombre, consulta in invalidas.items():
        comprobar(f"Entradas - {nombre} 422", solicitar("GET", f"{BASE}?{consulta}", token)[0] == 422)
    # Las dos reglas de fechas se explican en español.
    comprobar("Entradas - mensaje del rango invertido", "fecha inicial" in solicitar("GET", f"{BASE}?fecha_desde=2031-11-05&fecha_hasta=2031-11-04", token)[1]["detail"])
    comprobar("Entradas - mensaje del último día", "fuera de rango" in solicitar("GET", f"{BASE}?fecha_hasta=9999-12-31", token)[1]["detail"])
    # Los extremos válidos responden.
    comprobar("Entradas - límite 100", solicitar("GET", f"{BASE}?limite=100", token)[0] == 200)
    comprobar("Entradas - offset en el máximo", solicitar("GET", f"{BASE}?offset=2147483647", token)[0] == 200)
    comprobar("Entradas - penúltimo día del calendario", solicitar("GET", f"{BASE}?fecha_hasta=9999-12-30", token)[0] == 200)
    comprobar("Entradas - primer día del calendario", solicitar("GET", f"{BASE}?fecha_desde=0001-01-01", token)[0] == 200)
    comprobar("Entradas - usuario inexistente sin filas", registros(token, "usuario_id=no-existe") == set())
    # Una comilla no cambia la consulta.
    comprobar("Entradas - comilla en la tabla", registros(token, "tabla=' OR 1=1--") == set())


# Listas de los filtros: solo lo que tiene eventos.
def probar_listas(token: str, admin, gerencia, sin_eventos) -> None:
    # Usuarios del selector.
    usuarios = solicitar("GET", f"{BASE}/usuarios", token)[1]
    ids = [usuario["id"] for usuario in usuarios]
    comprobar("Usuarios - solo id y nombre", all(set(usuario) == {"id", "nombre_completo"} for usuario in usuarios))
    comprobar("Usuarios - incluye a quienes tienen eventos", admin.id in ids and gerencia.id in ids)
    comprobar("Usuarios - excluye a quien no tiene eventos", sin_eventos.id not in ids)
    comprobar("Usuarios - sin repetidos", len(ids) == len(set(ids)))
    # Tablas del selector.
    tablas = solicitar("GET", f"{BASE}/tablas", token)[1]
    comprobar("Tablas - incluye las del escenario", {"tarjas", "productores", "proceso_tarjas", "usuarios"} <= set(tablas))
    comprobar("Tablas - sin repetidas y ordenadas", tablas == sorted(set(tablas)))


# Recorre toda la bitácora por la API: también los datos reales de esta base.
def probar_recorrido_completo(db, token: str) -> None:
    # Eventos que debe recorrer.
    total = db.scalar(select(func.count()).select_from(Auditoria))
    # Cuenta los eventos vistos y reúne el texto.
    vistos, offset, texto, correcto = 0, 0, "", True
    # Avanza hasta la última página.
    while True:
        # Pide la página.
        estado, pagina = solicitar("GET", f"{BASE}?limite=100&offset={offset}", token)
        # Un evento que no se pueda presentar rompería la pantalla.
        if estado != 200:
            correcto = False
            break
        # Suma lo recibido.
        vistos += len(pagina["items"])
        texto += json.dumps(pagina)
        # Sin más páginas, termina.
        if not pagina["hay_mas"]:
            break
        # Siguiente página.
        offset += 100
    comprobar("Recorrido - todos los eventos se presentan", correcto and vistos == total)
    comprobar("Recorrido - sin credenciales", "password_hash" not in texto and "$2b$" not in texto)


# Solo lectura: HU21 criterio 3.
def probar_solo_lectura(db, token: str, antes: int) -> None:
    # Ninguna ruta acepta escribir.
    for ruta in RUTAS:
        for metodo in ("POST", "PUT", "PATCH", "DELETE"):
            comprobar(f"Solo lectura - {metodo} {ruta.removeprefix('/api/v1')} 405", solicitar(metodo, ruta, token, {} if metodo != "DELETE" else None)[0] == 405)
    # Tampoco existe una ruta por evento.
    comprobar("Solo lectura - sin ruta por evento", solicitar("DELETE", f"{BASE}/1", token)[0] == 404)
    # Consultar no agrega auditoría.
    comprobar("Solo lectura - consultar no agrega eventos", db.scalar(select(func.count()).select_from(Auditoria)) == antes)


# Criterios de HU22.
def probar_bitacora() -> None:
    # Escenario aislado.
    with aislado() as (db, _, _externa), api_con_sesion(db):
        # Actores del escenario.
        admin, token_admin = crear_actor(db, RolUsuario.ADMINISTRADOR)
        gerencia, token_gerencia = crear_actor(db, RolUsuario.GERENCIA)
        sin_eventos, _ = crear_actor(db, RolUsuario.OPERADOR_PROCESO)
        # Eventos con fechas lejanas a los datos reales.
        crear_eventos(db, admin, gerencia)
        # Cuenta las filas antes de consultar.
        antes = db.scalar(select(func.count()).select_from(Auditoria))

        # Criterio 3: acceso.
        probar_roles(db)
        # Criterio 1: filtros y días de Chile.
        probar_filtros(token_gerencia, admin, gerencia)
        probar_fechas(token_gerencia, admin)
        # Criterio 2: valor anterior y valor nuevo, sin credenciales.
        probar_valores(token_gerencia, admin, gerencia)
        # Pantalla: páginas, entradas y listas de los filtros.
        probar_paginacion(token_admin)
        probar_entradas(token_admin)
        probar_listas(token_gerencia, admin, gerencia, sin_eventos)
        # Toda la bitácora de esta base se puede presentar.
        probar_recorrido_completo(db, token_admin)
        # La consulta no escribe.
        probar_solo_lectura(db, token_admin, antes)


# Ejecuta el escenario y entrega el resultado.
def main() -> None:
    # Huellas iniciales en una conexión propia.
    with engine.connect() as conexion:
        inicio = base.huellas(conexion)
    # Guarda las dependencias para restaurarlas.
    overrides_anteriores = dict(app.dependency_overrides)
    # Un error inesperado no debe esconder el informe.
    try:
        # Criterios de HU22.
        probar_bitacora()
    # Registra el error sin detener el informe.
    except Exception:
        # Cuenta el error como falla.
        base.fallas += 1
        # Identifica el error en la salida.
        print("FALLA probar_bitacora: error inesperado", flush=True)
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
        comprobar("Final - tablas idénticas al inicio", base.huellas(conexion) == inicio)
    # Línea de resultado que se copia al acta.
    print(f"COMPROBACIONES: {base.comprobaciones} FALLAS: {base.fallas}", flush=True)
    # Con fallas, termina con error.
    if base.fallas:
        # Informa cuántas fallaron.
        print(f"RESULTADO: {base.fallas} comprobación(es) fallaron", flush=True)
        # Código de salida distinto de cero.
        raise SystemExit(1)
    # Sin fallas.
    print("RESULTADO: todas las pruebas pasaron", flush=True)


# No ejecuta nada al importar el módulo.
if __name__ == "__main__":
    main()
