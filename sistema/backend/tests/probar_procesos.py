"""HU18: prueba reproducible del registro de procesos de tarjas.

Ejecutar desde sistema/: docker compose exec -T backend python -m tests.probar_procesos
Todas las filas temporales quedan dentro de una transacción externa revertida.
"""

# Lee los valores que guarda la auditoría.
import json
# Imprime el detalle de un error inesperado.
import traceback
# Genera un RUT que no choca con datos existentes.
import uuid
# Compara fechas futuras.
from datetime import timedelta
# Pesos exactos, sin float.
from decimal import Decimal
# Simula el fallo de la auditoría.
from unittest.mock import patch

# Consultas de lectura y SQL directo.
from sqlalchemy import func, select, text
# Sesión del escenario.
from sqlalchemy.orm import Session

# Conexión a la base.
from app.core.database import engine
# Genera un token con un rol que la base no respalda.
from app.core.security import create_access_token
# Aplicación real que reciben las peticiones.
from app.main import app
# Modelos que se crean o se comprueban.
from app.models.auditoria import AccionAuditoria, Auditoria
from app.models.calidad import Calidad
from app.models.embalaje import Embalaje
from app.models.especie import Especie
from app.models.proceso import Proceso, ProcesoTarja
from app.models.productor import Productor
from app.models.sistema_productivo import SistemaProductivo
from app.models.tarja import EstadoTarja, Tarja
from app.models.usuario import RolUsuario
from app.models.variedad import Variedad
# Fecha de hoy en Chile.
from app.schemas.tarja import hoy_en_chile
# Funciones del service que se prueban directamente.
from app.services.proceso import anular_proceso, editar_proceso, recalcular_estado, registrar_proceso, terminar_tarja
# Entrada del service.
from app.schemas.proceso import ProcesoCreate, ProcesoEdicion
# Reutiliza el aislamiento, los actores y las peticiones de la prueba de tarjas.
from tests import probar_tarjas as base
from tests.probar_tarjas import aislado, api_con_sesion, comprobar, solicitar

# Ruta base del módulo.
BASE = "/api/v1/procesos"
# Ruta base de tarjas, para registrarlas y consultarlas.
BASE_TARJAS = "/api/v1/tarjas"


# Crea los datos comunes: los de la prueba de tarjas más los embalajes.
def preparar(db: Session) -> dict:
    # Actores, productor y catálogos.
    datos = base.preparar(db)
    # Embalaje fijo de 10 kg por caja.
    datos["caja_10"] = Embalaje(nombre=f"QA Caja 10 {datos['sistema'].id}", kg_por_caja=Decimal("10.00"), activo=True)
    # Embalaje fijo con decimales, igual al 5x5 libras del legado.
    datos["caja_1135"] = Embalaje(nombre=f"QA Caja 11,35 {datos['sistema'].id}", kg_por_caja=Decimal("11.35"), activo=True)
    # Embalaje a granel.
    datos["granel"] = Embalaje(nombre=f"QA Granel {datos['sistema'].id}", kg_por_caja=None, activo=True)
    # Embalaje desactivado.
    datos["inactivo"] = Embalaje(nombre=f"QA Inactivo {datos['sistema'].id}", kg_por_caja=Decimal("5.00"), activo=False)
    # Agrega los embalajes a la transacción.
    db.add_all([datos["caja_10"], datos["caja_1135"], datos["granel"], datos["inactivo"]])
    # Solo confirma el savepoint.
    db.commit()
    # Token del operador de recepción, que registra las tarjas.
    datos["token_recepcion"] = datos["actores"][RolUsuario.OPERADOR_RECEPCION][1]
    # Token del operador de proceso.
    datos["token_proceso"] = datos["actores"][RolUsuario.OPERADOR_PROCESO][1]
    # Token del administrador.
    datos["token_admin"] = datos["actores"][RolUsuario.ADMINISTRADOR][1]
    # Token de gerencia.
    datos["token_gerencia"] = datos["actores"][RolUsuario.GERENCIA][1]
    # Entrega los datos a los escenarios.
    return datos


# Registra una tarja de 920 kg por la API, como en la operación real.
def nueva_tarja(datos: dict, **cambios) -> dict:
    # Cada caso cambia solo el campo que prueba.
    estado, tarja = solicitar("POST", BASE_TARJAS, datos["token_recepcion"], {**base.cuerpo_valido(datos), **cambios})
    # Sin tarja no se puede seguir con el escenario.
    assert estado == 201, tarja
    # Entrega la tarja registrada.
    return tarja


# Arma el cuerpo de un proceso con una o varias filas.
def cuerpo(embalaje: Embalaje, *filas: dict, **cambios) -> dict:
    # Por defecto, elaborado hoy.
    return {"embalaje_id": embalaje.id, "fecha_elaboracion": hoy_en_chile().isoformat(), "tarjas": list(filas), **cambios}


# Arma una fila del proceso.
def fila(tarja: dict, cajas: int, **cambios) -> dict:
    # Solo lo que se indique además de la tarja y las cajas.
    return {"tarja_id": tarja["id"], "cantidad_cajas": cajas, **cambios}


# Registra un proceso con el operador de proceso y entrega código y respuesta.
def procesar(datos: dict, embalaje: Embalaje, *filas: dict, **cambios) -> tuple[int, object]:
    # Usa la API real.
    return solicitar("POST", BASE, datos["token_proceso"], cuerpo(embalaje, *filas, **cambios))


# Lee una tarja recién desde la base.
def tarja_de(db: Session, tarja: dict) -> Tarja:
    # Descarta lo que la sesión tenga en memoria.
    db.expire_all()
    # Devuelve la fila actual.
    return db.get(Tarja, tarja["id"])


# Cuenta procesos, filas, tarjas y eventos, para detectar escrituras.
def cantidades(db: Session) -> tuple[int, int, int, int]:
    # Las cuatro cantidades se comparan antes y después.
    return (
        db.scalar(select(func.count()).select_from(Proceso)),
        db.scalar(select(func.count()).select_from(ProcesoTarja)),
        db.scalar(select(func.count()).select_from(Tarja)),
        db.scalar(select(func.count()).select_from(Auditoria)),
    )


# Consulta los kilos de una tarja como los ve recepción (HU17).
def kilos_de(datos: dict, tarja: dict) -> tuple[Decimal, Decimal]:
    # Usa la API de tarjas.
    _, detalle = solicitar("GET", f"{BASE_TARJAS}/{tarja['id']}", datos["token_recepcion"])
    # Devuelve procesados y pendientes.
    return Decimal(detalle["kilos_procesados"]), Decimal(detalle["kilos_pendientes"])


# Solo proceso y administración entran, y el rol se lee de la base.
def probar_roles() -> None:
    # Escenario aislado.
    with aislado() as (db, _, _externa), api_con_sesion(db):
        # Datos comunes.
        datos = preparar(db)
        # Tarja para el proceso.
        tarja = nueva_tarja(datos)
        # Rutas que deben quedar protegidas.
        rutas = (
            ("GET", BASE),
            ("GET", f"{BASE}/embalajes"),
            ("GET", f"{BASE}/tarjas-disponibles"),
            ("GET", f"{BASE}/1"),
            ("POST", f"{BASE}/tarjas/{tarja['id']}/terminar"),
        )
        # Cuenta las filas antes de los rechazos.
        antes = cantidades(db)
        # Cada ruta rechaza a quien no corresponde.
        for metodo, ruta in rutas:
            # Sin token.
            comprobar(f"Roles - {metodo} {ruta} sin token 401", solicitar(metodo, ruta)[0] == 401)
            # Recepción no procesa.
            comprobar(f"Roles - {metodo} {ruta} recepción 403", solicitar(metodo, ruta, datos["token_recepcion"])[0] == 403)
            # Gerencia no procesa, aunque tenga más rango.
            comprobar(f"Roles - {metodo} {ruta} gerencia 403", solicitar(metodo, ruta, datos["token_gerencia"])[0] == 403)
        # Registrar también exige el rol.
        comprobar("Roles - registrar sin token 401", solicitar("POST", BASE, None, cuerpo(datos["caja_10"], fila(tarja, 1)))[0] == 401)
        comprobar("Roles - registrar recepción 403", solicitar("POST", BASE, datos["token_recepcion"], cuerpo(datos["caja_10"], fila(tarja, 1)))[0] == 403)
        comprobar("Roles - registrar gerencia 403", solicitar("POST", BASE, datos["token_gerencia"], cuerpo(datos["caja_10"], fila(tarja, 1)))[0] == 403)
        # El rol que cuenta es el de la base, no el del JWT.
        recepcion = datos["actores"][RolUsuario.OPERADOR_RECEPCION][0]
        token_obsoleto = create_access_token(recepcion.nombre_usuario, [RolUsuario.OPERADOR_PROCESO.value])
        comprobar("Roles - rol obsoleto del JWT 403", solicitar("POST", BASE, token_obsoleto, cuerpo(datos["caja_10"], fila(tarja, 1)))[0] == 403)
        # Nada de lo anterior escribió.
        comprobar("Roles - rechazos sin escrituras", cantidades(db) == antes)
        # El operador de proceso sí registra.
        estado, _ = procesar(datos, datos["caja_10"], fila(tarja, 1))
        comprobar("Roles - proceso 201", estado == 201)
        # El administrador también.
        estado, _ = solicitar("POST", BASE, datos["token_admin"], cuerpo(datos["caja_10"], fila(tarja, 1)))
        comprobar("Roles - administrador 201", estado == 201)
        # El operador de proceso lee embalajes sin acceder a los mantenedores.
        estado, lista = solicitar("GET", f"{BASE}/embalajes", datos["token_proceso"])
        nombres = {opcion["nombre"] for opcion in lista} if estado == 200 else set()
        comprobar("Roles - embalajes activos, sin el desactivado", datos["caja_10"].nombre in nombres and datos["inactivo"].nombre not in nombres)
        # Nunca se entrega información de credenciales.
        estado, detalle = solicitar("GET", f"{BASE}", datos["token_proceso"])
        comprobar("Roles - respuesta sin password_hash", estado == 200 and "password_hash" not in str(detalle))


# Criterio 1: folio único con la secuencia.
def probar_folio() -> None:
    # Dos conexiones, como dos operadores guardando a la vez.
    with engine.connect() as primera, engine.connect() as segunda:
        # Pedir un número no se bloquea.
        numero_1 = primera.scalar(text("SELECT NEXT VALUE FOR seq_numero_proceso"))
        numero_2 = segunda.scalar(text("SELECT NEXT VALUE FOR seq_numero_proceso"))
        # Nunca deben coincidir.
        comprobar("Criterio 1 - dos conexiones, números distintos", numero_1 != numero_2)
    # Escenario aislado.
    with aislado() as (db, _, _externa), api_con_sesion(db):
        # Datos comunes.
        datos = preparar(db)
        # Tarja para los procesos.
        tarja = nueva_tarja(datos)
        # Dos procesos seguidos.
        _, uno = procesar(datos, datos["caja_10"], fila(tarja, 1))
        _, dos = procesar(datos, datos["caja_10"], fila(tarja, 1))
        # El folio es P más un número.
        comprobar("Criterio 1 - folio P + número", uno["folio"].startswith("P") and uno["folio"][1:].isdigit())
        # El siguiente es mayor y distinto.
        comprobar("Criterio 1 - folio correlativo", int(dos["folio"][1:]) > int(uno["folio"][1:]))
        # El cliente no puede imponer el folio.
        antes = cantidades(db)
        estado, _ = procesar(datos, datos["caja_10"], fila(tarja, 1), folio="P1")
        comprobar("Criterio 1 - folio del cliente 422", estado == 422)
        # Tampoco los totales ni el usuario.
        estado, _ = procesar(datos, datos["caja_10"], fila(tarja, 1), kilos_salida="1.00")
        comprobar("Criterio 1 - totales del cliente 422", estado == 422)
        comprobar("Criterio 1 - rechazos sin escrituras", cantidades(db) == antes)


# Criterio 2: kilos calculados; a mano solo a granel.
def probar_kilos() -> None:
    # Escenario aislado.
    with aislado() as (db, _, _externa), api_con_sesion(db):
        # Datos comunes.
        datos = preparar(db)
        # Tarja de 920 kg.
        tarja = nueva_tarja(datos)
        # 30 cajas de 10 kg son 300 kg.
        estado, proceso = procesar(datos, datos["caja_10"], fila(tarja, 30))
        comprobar("Criterio 2 - 201", estado == 201)
        comprobar("Criterio 2 - kilos = cajas × kg", Decimal(proceso["tarjas"][0]["kilos_procesados"]) == 300)
        comprobar("Criterio 2 - totales de la cabecera", Decimal(proceso["cantidad_cajas"]) == 30 and Decimal(proceso["kilos_salida"]) == 300)
        comprobar("Criterio 2 - fecha de elaboración", proceso["fecha_elaboracion"] == hoy_en_chile().isoformat())
        comprobar("Criterio 2 - embalaje", proceso["embalaje"] == datos["caja_10"].nombre)
        # El peso con decimales se calcula exacto: 20 × 11,35 = 227,00.
        estado, proceso = procesar(datos, datos["caja_1135"], fila(tarja, 20))
        comprobar("Criterio 2 - decimales exactos", estado == 201 and Decimal(proceso["kilos_salida"]) == Decimal("227.00"))
        # Antes de probar rechazos, cuenta las filas.
        antes = cantidades(db)
        # Con embalaje fijo no se aceptan kilos del cliente.
        estado, respuesta = procesar(datos, datos["caja_10"], fila(tarja, 1, kilos_procesados="999.00"))
        comprobar("Criterio 2 - kilos del cliente en embalaje fijo 400", estado == 400 and "calcula" in respuesta["detail"])
        # A granel los kilos son obligatorios.
        estado, respuesta = procesar(datos, datos["granel"], fila(tarja, 1))
        comprobar("Criterio 2 - granel sin kilos 400", estado == 400 and "granel" in respuesta["detail"])
        # Los rechazos no gastan nada.
        comprobar("Criterio 2 - rechazos sin escrituras", cantidades(db) == antes)
        # A granel se conserva lo ingresado.
        estado, proceso = procesar(datos, datos["granel"], fila(tarja, 1, kilos_procesados="5.25"))
        comprobar("Criterio 2 - granel con kilos a mano", estado == 201 and Decimal(proceso["tarjas"][0]["kilos_procesados"]) == Decimal("5.25"))
        # Si no llega la fecha, queda la de hoy.
        estado, proceso = solicitar("POST", BASE, datos["token_proceso"], {"embalaje_id": datos["caja_10"].id, "tarjas": [fila(tarja, 1)]})
        comprobar("Criterio 2 - sin fecha usa hoy en Chile", estado == 201 and proceso["fecha_elaboracion"] == hoy_en_chile().isoformat())


# Validación del schema: datos inválidos responden 422 y no escriben.
def probar_validaciones() -> None:
    # Escenario aislado.
    with aislado() as (db, _, _externa), api_con_sesion(db):
        # Datos comunes.
        datos = preparar(db)
        # Tarja válida para los casos.
        tarja = nueva_tarja(datos)
        # Un día después de hoy.
        manana = (hoy_en_chile() + timedelta(days=1)).isoformat()
        # Cuenta las filas antes de los rechazos.
        antes = cantidades(db)
        # Cuerpos inválidos: nombre y cuerpo.
        casos = (
            ("sin tarjas", {"embalaje_id": datos["caja_10"].id, "tarjas": []}),
            ("sin embalaje", {"tarjas": [fila(tarja, 1)]}),
            ("tarja repetida", cuerpo(datos["caja_10"], fila(tarja, 1), fila(tarja, 2))),
            ("fecha futura", cuerpo(datos["caja_10"], fila(tarja, 1), fecha_elaboracion=manana)),
            ("cero cajas", cuerpo(datos["caja_10"], fila(tarja, 0))),
            ("cajas negativas", cuerpo(datos["caja_10"], fila(tarja, -1))),
            ("cajas con tres decimales", cuerpo(datos["caja_10"], fila(tarja, "1.234"))),
            ("cajas booleano", cuerpo(datos["caja_10"], fila(tarja, True))),
            ("cajas sobre DECIMAL(10,2)", cuerpo(datos["caja_10"], fila(tarja, "100000000.00"))),
            ("cajas de texto", cuerpo(datos["caja_10"], fila(tarja, "abc"))),
            ("embalaje como texto", {**cuerpo(datos["caja_10"], fila(tarja, 1)), "embalaje_id": str(datos["caja_10"].id)}),
            ("embalaje sobre INT", {**cuerpo(datos["caja_10"], fila(tarja, 1)), "embalaje_id": 2147483648}),
            ("tarja sobre INT", cuerpo(datos["caja_10"], {"tarja_id": 2147483648, "cantidad_cajas": 1})),
            ("kilos negativos", cuerpo(datos["granel"], fila(tarja, 1, kilos_procesados="-1"))),
            ("kilos cero", cuerpo(datos["granel"], fila(tarja, 1, kilos_procesados="0"))),
            ("kilos con tres decimales", cuerpo(datos["granel"], fila(tarja, 1, kilos_procesados="1.234"))),
            ("kilos sobre DECIMAL(10,2)", cuerpo(datos["granel"], fila(tarja, 1, kilos_procesados="100000000.00"))),
            ("kilos booleano", cuerpo(datos["granel"], fila(tarja, 1, kilos_procesados=True))),
            ("kilos Infinity", cuerpo(datos["granel"], fila(tarja, 1, kilos_procesados="Infinity"))),
            ("terminada como texto", cuerpo(datos["caja_10"], fila(tarja, 1, tarja_terminada="si"))),
            ("campo extra en la fila", cuerpo(datos["caja_10"], fila(tarja, 1, kilos_salida="1"))),
        )
        # Cada caso se prueba por separado.
        for nombre, datos_invalidos in casos:
            # Envía el cuerpo inválido.
            estado, _ = solicitar("POST", BASE, datos["token_proceso"], datos_invalidos)
            comprobar(f"Schema - {nombre} 422", estado == 422)
        # Un id de ruta fuera de rango responde 422.
        comprobar("Schema - id de proceso sobre INT 422", solicitar("GET", f"{BASE}/2147483648", datos["token_proceso"])[0] == 422)
        comprobar("Schema - id de tarja sobre INT 422", solicitar("POST", f"{BASE}/tarjas/2147483648/terminar", datos["token_proceso"])[0] == 422)
        comprobar("Schema - número de tarja sobre INT 422", solicitar("GET", f"{BASE}/tarjas-disponibles?numero_tarja=2147483648", datos["token_proceso"])[0] == 422)
        # Nada de lo anterior escribió.
        comprobar("Schema - rechazos sin escrituras", cantidades(db) == antes)
        # Embalaje inexistente y desactivado.
        estado, _ = solicitar("POST", BASE, datos["token_proceso"], {**cuerpo(datos["caja_10"], fila(tarja, 1)), "embalaje_id": 2147483647})
        comprobar("Negocio - embalaje inexistente 400", estado == 400)
        estado, _ = procesar(datos, datos["inactivo"], fila(tarja, 1))
        comprobar("Negocio - embalaje desactivado 400", estado == 400)
        # Tarja inexistente.
        estado, _ = solicitar("POST", BASE, datos["token_proceso"], cuerpo(datos["caja_10"], {"tarja_id": 2147483647, "cantidad_cajas": 1}))
        comprobar("Negocio - tarja inexistente 404", estado == 404)
        # Proceso inexistente.
        comprobar("Negocio - proceso inexistente 404", solicitar("GET", f"{BASE}/2147483647", datos["token_proceso"])[0] == 404)
        # Los rechazos de negocio tampoco escriben.
        comprobar("Negocio - rechazos sin escrituras", cantidades(db) == antes)


# Criterios 3 y 4: tarjas disponibles, saldo y consumo parcial.
def probar_consumo_parcial() -> None:
    # Escenario aislado.
    with aislado() as (db, _, _externa), api_con_sesion(db):
        # Datos comunes.
        datos = preparar(db)
        # Tarja de 920 kg.
        tarja = nueva_tarja(datos)

        # Ayuda: la fila de la tarja en la lista de disponibles.
        def disponible() -> dict | None:
            # Consulta por número, como el formulario.
            _, lista = solicitar("GET", f"{BASE}/tarjas-disponibles?numero_tarja={tarja['numero_tarja']}", datos["token_proceso"])
            # Sin coincidencias, no está disponible.
            return lista[0] if lista else None

        # Parte disponible con todos sus kilos.
        fila_lista = disponible()
        comprobar("Criterio 3 - recién recibida está disponible", fila_lista is not None and fila_lista["estado"] == "RECEPCIONADA")
        comprobar("Criterio 3 - muestra los kilos que quedan", Decimal(fila_lista["kilos_pendientes"]) == 920 and Decimal(fila_lista["kilos_procesados"]) == 0)
        comprobar("Criterio 3 - muestra la fruta y el productor", fila_lista["especie"] and fila_lista["calidad"] and fila_lista["sistema_productivo"] and fila_lista["productor_razon_social"])
        # El listado completo la incluye.
        _, lista = solicitar("GET", f"{BASE}/tarjas-disponibles", datos["token_proceso"])
        comprobar("Criterio 3 - también en el listado completo", any(opcion["id"] == tarja["id"] for opcion in lista))

        # Primer proceso: 400 kg.
        estado, proceso_1 = procesar(datos, datos["caja_10"], fila(tarja, 40))
        comprobar("Criterio 6 - primer proceso deja la tarja parcial", estado == 201 and tarja_de(db, tarja).estado == EstadoTarja.PARCIAL)
        comprobar("Criterio 4 - quedan 520 kg", Decimal(disponible()["kilos_pendientes"]) == 520)
        # Recepción ve los mismos kilos.
        comprobar("Criterio 4 - HU17 muestra lo procesado", kilos_de(datos, tarja) == (Decimal(400), Decimal(520)))
        # HU12 descuenta lo procesado de los acumulados del productor.
        _, acumulado = solicitar("GET", f"{BASE_TARJAS}/pendientes?productor_id={datos['productor'].id}", datos["token_recepcion"])
        comprobar("HU12 - pendientes descuenta lo procesado", acumulado["tarjas_sin_procesar"] == 1 and Decimal(acumulado["kilos_sin_procesar"]) == 520)
        # HU24 sigue rechazando una tarja con kilos en procesos, ahora con un proceso real.
        estado, _ = solicitar("POST", f"{BASE_TARJAS}/{tarja['id']}/anular", datos["token_admin"])
        comprobar("HU24 - con proceso real no se anula", estado == 409 and tarja_de(db, tarja).estado == EstadoTarja.PARCIAL)

        # Pedir más de lo que queda se rechaza y no escribe.
        antes = cantidades(db)
        estado, respuesta = procesar(datos, datos["caja_10"], fila(tarja, 53))
        comprobar("Criterio 4 - sobreconsumo 409", estado == 409 and "520" in respuesta["detail"])
        comprobar("Criterio 4 - sobreconsumo sin escrituras", cantidades(db) == antes and tarja_de(db, tarja).estado == EstadoTarja.PARCIAL)

        # Un segundo proceso con lo justo deja el saldo en 0.
        estado, proceso_2 = procesar(datos, datos["caja_10"], fila(tarja, 52))
        comprobar("Criterio 4 - se puede consumir lo justo", estado == 201)
        # Decisión del 03/11: con saldo 0 se cierra sola, sin marca.
        comprobar("Cierre - saldo 0 deja la tarja procesada", tarja_de(db, tarja).estado == EstadoTarja.PROCESADA)
        comprobar("Cierre - no se inventa una marca", db.get(ProcesoTarja, (proceso_2["id"], tarja["id"])).tarja_terminada is False)
        comprobar("Criterio 5 - cerrada ya no aparece", disponible() is None)
        comprobar("Cierre - HU17 sin kilos pendientes", kilos_de(datos, tarja) == (Decimal(920), Decimal(0)))
        # Otra vez a procesarla: se rechaza.
        estado, respuesta = procesar(datos, datos["caja_10"], fila(tarja, 1))
        comprobar("Criterio 3 - terminada 409", estado == 409 and "terminada" in respuesta["detail"])

        # Un proceso anulado deja de contar y la tarja se abre sola (preparación de HU25).
        proceso = db.get(Proceso, proceso_1["id"])
        proceso.anulado = True
        db.flush()
        recalcular_estado(db, tarja_de(db, tarja))
        db.commit()
        comprobar("Anulado - vuelve a parcial sin merma inventada", tarja_de(db, tarja).estado == EstadoTarja.PARCIAL)
        comprobar("Anulado - sus kilos vuelven", kilos_de(datos, tarja) == (Decimal(520), Decimal(400)))
        comprobar("Anulado - vuelve a estar disponible", disponible() is not None)
        # Anulando también el otro, queda como recién recibida.
        db.get(Proceso, proceso_2["id"]).anulado = True
        db.flush()
        recalcular_estado(db, tarja_de(db, tarja))
        db.commit()
        comprobar("Anulado - sin procesos vuelve a recepcionada", tarja_de(db, tarja).estado == EstadoTarja.RECEPCIONADA)

        # Una tarja anulada no se procesa ni aparece.
        anulada = nueva_tarja(datos)
        solicitar("POST", f"{BASE_TARJAS}/{anulada['id']}/anular", datos["token_admin"])
        estado, respuesta = procesar(datos, datos["caja_10"], fila(anulada, 1))
        comprobar("Criterio 3 - anulada 409", estado == 409 and "anulada" in respuesta["detail"])
        _, lista = solicitar("GET", f"{BASE}/tarjas-disponibles?numero_tarja={anulada['numero_tarja']}", datos["token_proceso"])
        comprobar("Criterio 3 - anulada no aparece", lista == [])


# Criterio 5: la marca del operador y la rebaja a merma.
def probar_terminada_y_merma() -> None:
    # Escenario aislado.
    with aislado() as (db, _, _externa), api_con_sesion(db):
        # Datos comunes.
        datos = preparar(db)

        # Marca en el mismo proceso: lo que falta queda como merma.
        tarja = nueva_tarja(datos)
        estado, proceso = procesar(datos, datos["caja_10"], fila(tarja, 90, tarja_terminada=True))
        comprobar("Criterio 5 - con marca queda procesada", estado == 201 and tarja_de(db, tarja).estado == EstadoTarja.PROCESADA)
        comprobar("Criterio 5 - la fila guarda la marca", proceso["tarjas"][0]["tarja_terminada"] is True)
        comprobar("Criterio 5 - sin kilos pendientes", kilos_de(datos, tarja) == (Decimal(900), Decimal(0)))
        _, lista = solicitar("GET", f"{BASE}/tarjas-disponibles?numero_tarja={tarja['numero_tarja']}", datos["token_proceso"])
        comprobar("Criterio 5 - ya no aparece", lista == [])
        # Anular el proceso con la marca la reabre (HU25 criterio 3).
        db.get(Proceso, proceso["id"]).anulado = True
        db.flush()
        recalcular_estado(db, tarja_de(db, tarja))
        db.commit()
        comprobar("Criterio 5 - sin su proceso la marca se pierde", tarja_de(db, tarja).estado == EstadoTarja.RECEPCIONADA)

        # Rebaja a merma: 88 cajas de 11,35 son 998,80 kg; con 1.000 netos quedan 1,20 kg.
        grande = nueva_tarja(datos, kilos_brutos="1080.00")
        comprobar("Merma - tarja de 1.000 kg", grande["kilos_netos"] == 1000)
        # Ruta de la rebaja.
        ruta = f"{BASE}/tarjas/{grande['id']}/terminar"
        # Dos procesos, sin marca.
        estado, primero = procesar(datos, datos["caja_1135"], fila(grande, 40))
        estado, ultimo = procesar(datos, datos["caja_1135"], fila(grande, 48))
        comprobar("Merma - quedan 1,20 kg, menos que una caja", kilos_de(datos, grande) == (Decimal("998.80"), Decimal("1.20")))
        # Una caja completa no cabe.
        estado, _ = procesar(datos, datos["caja_1135"], fila(grande, 1))
        comprobar("Merma - otra caja no cabe 409", estado == 409)
        comprobar("Merma - sigue parcial", tarja_de(db, grande).estado == EstadoTarja.PARCIAL)
        # Un fallo al auditar revierte todo.
        antes = cantidades(db)
        with patch("app.services.proceso.registrar_auditoria", side_effect=RuntimeError("fallo simulado de auditoría")):
            # El error debe llegar hasta aquí.
            try:
                terminar_tarja(db, grande["id"], datos["actores"][RolUsuario.OPERADOR_PROCESO][0])
                revirtio = False
            # La rebaja se revierte.
            except RuntimeError:
                revirtio = True
        comprobar("Merma - fallo de auditoría revierte", revirtio and cantidades(db) == antes and tarja_de(db, grande).estado == EstadoTarja.PARCIAL and tarja_de(db, grande).merma_rebajada is False)
        # El operador de proceso rebaja el saldo.
        estado, resultado = solicitar("POST", ruta, datos["token_proceso"])
        comprobar("Merma - 200", estado == 200)
        comprobar("Merma - informa los kilos", Decimal(resultado["kilos_merma"]) == Decimal("1.20") and Decimal(resultado["kilos_procesados"]) == Decimal("998.80"))
        comprobar("Merma - queda procesada", resultado["estado"] == "PROCESADA" and tarja_de(db, grande).estado == EstadoTarja.PROCESADA)
        # La merma es de la recepción: el proceso no cambia.
        comprobar("Merma - queda en la tarja de recepción", tarja_de(db, grande).merma_rebajada is True)
        comprobar("Merma - no toca los procesos", db.get(ProcesoTarja, (ultimo["id"], grande["id"])).tarja_terminada is False and db.get(ProcesoTarja, (primero["id"], grande["id"])).tarja_terminada is False and db.get(Proceso, ultimo["id"]).kilos_salida == Decimal("544.80"))
        comprobar("Merma - HU17 sin kilos pendientes", kilos_de(datos, grande) == (Decimal("998.80"), Decimal(0)))
        # La bitácora deja quién y cuánto.
        eventos = db.scalars(select(Auditoria).where(Auditoria.motivo.like("%rebajado como merma"), Auditoria.tabla == "tarjas", Auditoria.registro_id == str(grande["id"]))).all()
        comprobar("Merma - auditoría con los kilos", len(eventos) == 1 and "1.20 kg" in eventos[0].motivo and eventos[0].accion == AccionAuditoria.UPDATE)
        # Rebajar dos veces no tiene sentido.
        estado, _ = solicitar("POST", ruta, datos["token_proceso"])
        comprobar("Merma - dos veces 409", estado == 409)
        # Tarja inexistente.
        comprobar("Merma - inexistente 404", solicitar("POST", f"{BASE}/tarjas/2147483647/terminar", datos["token_proceso"])[0] == 404)
        # Tarja anulada.
        anulada = nueva_tarja(datos)
        solicitar("POST", f"{BASE_TARJAS}/{anulada['id']}/anular", datos["token_admin"])
        comprobar("Merma - anulada 409", solicitar("POST", f"{BASE}/tarjas/{anulada['id']}/terminar", datos["token_proceso"])[0] == 409)

        # Reabrir: solo el administrador deshace una rebaja hecha por error.
        ruta_reabrir = f"{BASE}/tarjas/{grande['id']}/reabrir"
        comprobar("Reabrir - sin token 401", solicitar("POST", ruta_reabrir)[0] == 401)
        comprobar("Reabrir - recepción 403", solicitar("POST", ruta_reabrir, datos["token_recepcion"])[0] == 403)
        comprobar("Reabrir - gerencia 403", solicitar("POST", ruta_reabrir, datos["token_gerencia"])[0] == 403)
        comprobar("Reabrir - sin cambios tras los rechazos", tarja_de(db, grande).merma_rebajada is True)
        # La rebaja aparece en la lista desde la que se reabre, con su merma.
        ruta_rebajadas = f"{BASE}/tarjas-rebajadas"
        estado, rebajadas = solicitar("GET", ruta_rebajadas, datos["token_proceso"])
        en_lista = next((opcion for opcion in rebajadas if opcion["id"] == grande["id"]), None) if estado == 200 else None
        comprobar("Reabrir - aparece en la lista con su merma", en_lista is not None and Decimal(en_lista["kilos_pendientes"]) == Decimal("1.20"))
        comprobar("Reabrir - lista sin token 401", solicitar("GET", ruta_rebajadas)[0] == 401)
        comprobar("Reabrir - lista recepción 403", solicitar("GET", ruta_rebajadas, datos["token_recepcion"])[0] == 403)
        comprobar("Reabrir - lista gerencia 403", solicitar("GET", ruta_rebajadas, datos["token_gerencia"])[0] == 403)
        # Decisión del 03/11: el operador de proceso también reabre.
        estado, resultado = solicitar("POST", ruta_reabrir, datos["token_proceso"])
        comprobar("Reabrir - vuelve a parcial con sus kilos", estado == 200 and resultado["estado"] == "PARCIAL" and kilos_de(datos, grande) == (Decimal("998.80"), Decimal("1.20")))
        comprobar("Reabrir - quita la decisión", tarja_de(db, grande).merma_rebajada is False)
        eventos = db.scalars(select(Auditoria).where(Auditoria.motivo == "Merma rebajada deshecha", Auditoria.registro_id == str(grande["id"]))).all()
        comprobar("Reabrir - queda en la auditoría", len(eventos) == 1)
        comprobar("Reabrir - sin merma rebajada 409", solicitar("POST", ruta_reabrir, datos["token_admin"])[0] == 409)
        # Ya no aparece en la lista.
        _, rebajadas = solicitar("GET", ruta_rebajadas, datos["token_proceso"])
        comprobar("Reabrir - sale de la lista", all(opcion["id"] != grande["id"] for opcion in rebajadas))
        comprobar("Reabrir - inexistente 404", solicitar("POST", f"{BASE}/tarjas/2147483647/reabrir", datos["token_admin"])[0] == 404)

        # Los kilos que sobran se pueden poner en otro proceso: 0,11 cajas de 11,35 kg dejan el saldo exacto en 0.
        estado, saldo_final = procesar(datos, datos["caja_1135"], fila(grande, "0.11"))
        comprobar("Resto - cabe en otro proceso con cajas decimales", estado == 201 and Decimal(saldo_final["tarjas"][0]["kilos_procesados"]) == Decimal("1.20"))
        comprobar("Resto - llega a 0 y se cierra", tarja_de(db, grande).estado == EstadoTarja.PROCESADA and kilos_de(datos, grande) == (Decimal(1000), Decimal(0)))
        # Una caja armada con fruta de dos tarjas: media de cada una suma una caja completa.
        mitad_1 = nueva_tarja(datos)
        mitad_2 = nueva_tarja(datos)
        estado, caja_mixta = procesar(datos, datos["caja_10"], fila(mitad_1, "0.5"), fila(mitad_2, "0.5"))
        comprobar("Resto - caja armada con dos tarjas", estado == 201 and Decimal(caja_mixta["cantidad_cajas"]) == 1 and Decimal(caja_mixta["kilos_salida"]) == 10)
        # El redondeo no sirve para pasarse: dos centésimos de caja de más se rechazan.
        justa = nueva_tarja(datos)
        estado, _ = procesar(datos, datos["caja_10"], fila(justa, "92.02"))
        comprobar("Resto - pasarse del saldo sigue rechazado", estado == 409)
        estado, _ = procesar(datos, datos["caja_10"], fila(justa, "92.01"))
        comprobar("Resto - un centésimo de caja exacto de más también", estado == 409 and kilos_de(datos, justa) == (Decimal(0), Decimal(920)))

        # Merma de una tarja completa: toda su fruta se descartó antes de entrar a proceso.
        descartada = nueva_tarja(datos)
        estado, resultado = solicitar("POST", f"{BASE}/tarjas/{descartada['id']}/terminar", datos["token_proceso"])
        comprobar("Merma total - tarja sin procesos 200", estado == 200 and Decimal(resultado["kilos_merma"]) == 920 and Decimal(resultado["kilos_procesados"]) == 0)
        comprobar("Merma total - queda procesada", tarja_de(db, descartada).estado == EstadoTarja.PROCESADA)
        _, lista = solicitar("GET", f"{BASE}/tarjas-disponibles?numero_tarja={descartada['numero_tarja']}", datos["token_proceso"])
        comprobar("Merma total - ya no aparece", lista == [])
        estado, _ = procesar(datos, datos["caja_10"], fila(descartada, 1))
        comprobar("Merma total - no se puede procesar", estado == 409)
        # Sus bandejas siguen en el saldo: la fruta sí llegó.
        _, saldos = solicitar("GET", f"{BASE_TARJAS}/saldo-bandejas?productor_id={datos['productor'].id}", datos["token_recepcion"])
        comprobar("Merma total - las bandejas siguen sumando", any(fila_saldo["entradas"] >= 50 for fila_saldo in saldos))
        # Para anularla, primero se reabre.
        estado, respuesta = solicitar("POST", f"{BASE_TARJAS}/{descartada['id']}/anular", datos["token_admin"])
        comprobar("Merma total - anular pide reabrir", estado == 409 and "reabrir" in respuesta["detail"])
        estado, resultado = solicitar("POST", f"{BASE}/tarjas/{descartada['id']}/reabrir", datos["token_admin"])
        comprobar("Merma total - reabrir vuelve a recepcionada", estado == 200 and resultado["estado"] == "RECEPCIONADA")
        comprobar("Merma total - ya se puede anular", solicitar("POST", f"{BASE_TARJAS}/{descartada['id']}/anular", datos["token_admin"])[0] == 200)
        # El administrador también puede rebajar.
        otra = nueva_tarja(datos)
        procesar(datos, datos["caja_10"], fila(otra, 1))
        comprobar("Merma - administrador 200", solicitar("POST", f"{BASE}/tarjas/{otra['id']}/terminar", datos["token_admin"])[0] == 200)
        # Con la merma rebajada, anular un proceso no reabre la tarja sola: lo decide el administrador.
        recalcular_estado(db, tarja_de(db, otra))
        comprobar("Merma - recalcular respeta la decisión", tarja_de(db, otra).estado == EstadoTarja.PROCESADA)
        db.rollback()


# HU25: anular un proceso; todo queda pendiente y la merma la vuelve a decidir el operador.
def probar_anulacion() -> None:
    # Escenario aislado.
    with aislado() as (db, _, _externa), api_con_sesion(db):
        # Datos comunes.
        datos = preparar(db)

        # Ayuda: anula con el token indicado.
        def anular(proceso_id: int, token: str | None = datos["token_admin"]) -> tuple[int, object]:
            # Usa la API real.
            return solicitar("POST", f"{BASE}/{proceso_id}/anular", token)

        # Criterio 1: solo el administrador.
        tarja = nueva_tarja(datos)
        _, proceso = procesar(datos, datos["caja_10"], fila(tarja, 40))
        antes = cantidades(db)
        comprobar("HU25 - sin token 401", anular(proceso["id"], None)[0] == 401)
        comprobar("HU25 - operador de proceso 403", anular(proceso["id"], datos["token_proceso"])[0] == 403)
        comprobar("HU25 - recepción 403", anular(proceso["id"], datos["token_recepcion"])[0] == 403)
        comprobar("HU25 - gerencia 403", anular(proceso["id"], datos["token_gerencia"])[0] == 403)
        # El rol que cuenta es el de la base, no el del JWT.
        operador = datos["actores"][RolUsuario.OPERADOR_PROCESO][0]
        token_obsoleto = create_access_token(operador.nombre_usuario, [RolUsuario.ADMINISTRADOR.value])
        comprobar("HU25 - rol obsoleto del JWT 403", anular(proceso["id"], token_obsoleto)[0] == 403)
        comprobar("HU25 - rechazos sin escrituras", cantidades(db) == antes and db.get(Proceso, proceso["id"]).anulado is False)
        comprobar("HU25 - inexistente 404", anular(2147483647)[0] == 404)
        comprobar("HU25 - id sobre INT 422", anular(2147483648)[0] == 422)

        # Un fallo al auditar revierte todo (criterio 4).
        with patch("app.services.proceso.registrar_auditoria", side_effect=RuntimeError("fallo simulado de auditoría")):
            # El error debe llegar hasta aquí.
            try:
                anular_proceso(db, proceso["id"], datos["actores"][RolUsuario.ADMINISTRADOR][0])
                revirtio = False
            # La anulación se revierte.
            except RuntimeError:
                revirtio = True
        db.expire_all()
        comprobar("HU25 - fallo de auditoría revierte", revirtio and cantidades(db) == antes and db.get(Proceso, proceso["id"]).anulado is False and tarja_de(db, tarja).estado == EstadoTarja.PARCIAL and kilos_de(datos, tarja) == (Decimal(400), Decimal(520)))

        # Anular: los kilos vuelven y la tarja queda como recién recibida (criterio 3).
        filas_antes = db.scalar(select(func.count()).select_from(ProcesoTarja))
        estado, anulado = anular(proceso["id"])
        comprobar("HU25 - 200 y queda anulado", estado == 200 and anulado["anulado"] is True)
        comprobar("HU25 - sin procesos vuelve a recepcionada", tarja_de(db, tarja).estado == EstadoTarja.RECEPCIONADA)
        comprobar("HU25 - los kilos vuelven", kilos_de(datos, tarja) == (Decimal(0), Decimal(920)))
        _, lista = solicitar("GET", f"{BASE}/tarjas-disponibles?numero_tarja={tarja['numero_tarja']}", datos["token_proceso"])
        comprobar("HU25 - vuelve a estar disponible", len(lista) == 1 and Decimal(lista[0]["kilos_pendientes"]) == 920)
        # Criterio 2: no se borra y conserva su folio.
        comprobar("HU25 - no borra nada", db.scalar(select(func.count()).select_from(ProcesoTarja)) == filas_antes and db.get(Proceso, proceso["id"]).folio == proceso["folio"])
        _, detalle = solicitar("GET", f"{BASE}/{proceso['id']}", datos["token_proceso"])
        comprobar("HU25 - el detalle sigue disponible, marcado", detalle["anulado"] is True and detalle["folio"] == proceso["folio"] and len(detalle["tarjas"]) == 1)
        _, listado = solicitar("GET", BASE, datos["token_proceso"])
        comprobar("HU25 - sigue en el listado", any(p["id"] == proceso["id"] and p["anulado"] is True for p in listado))
        comprobar("HU25 - DELETE no existe", solicitar("DELETE", f"{BASE}/{proceso['id']}", datos["token_admin"])[0] == 405)
        # El folio no se reutiliza.
        _, siguiente = procesar(datos, datos["caja_10"], fila(tarja, 1))
        comprobar("HU25 - el folio no se reutiliza", int(siguiente["folio"][1:]) > int(proceso["folio"][1:]))
        # Anularlo dos veces no tiene sentido.
        antes = cantidades(db)
        comprobar("HU25 - dos veces 409", anular(proceso["id"])[0] == 409 and cantidades(db) == antes)
        # Un proceso anulado no se edita.
        comprobar("HU25 - anulado no se edita", solicitar("PUT", f"{BASE}/{proceso['id']}", datos["token_proceso"], {"tarjas": [fila(tarja, 1)]})[0] == 409)
        # La auditoría registra quién y cuándo, sin exigir motivo al administrador.
        admin = datos["actores"][RolUsuario.ADMINISTRADOR][0]
        eventos = list(db.scalars(select(Auditoria).where(Auditoria.tabla == "procesos", Auditoria.registro_id == str(proceso["id"]), Auditoria.accion == AccionAuditoria.UPDATE)))
        comprobar("HU25 - auditoría de la cabecera", len(eventos) == 1 and eventos[0].usuario_id == admin.id and json.loads(eventos[0].valores_antes)["anulado"] is False and json.loads(eventos[0].valores_despues)["anulado"] is True and proceso["folio"] in eventos[0].motivo)
        eventos = list(db.scalars(select(Auditoria).where(Auditoria.tabla == "tarjas", Auditoria.registro_id == str(tarja["id"]), Auditoria.motivo == f"Anulación del proceso {proceso['folio']}")))
        comprobar("HU25 - auditoría de la tarja", len(eventos) == 1 and "PARCIAL" in eventos[0].valores_antes and "RECEPCIONADA" in eventos[0].valores_despues)

        # Con otro proceso vigente queda parcial, con lo de ese proceso.
        con_otro = nueva_tarja(datos)
        _, p_1 = procesar(datos, datos["caja_10"], fila(con_otro, 10))
        _, p_2 = procesar(datos, datos["caja_10"], fila(con_otro, 20))
        anular(p_1["id"])
        comprobar("HU25 - con otro proceso queda parcial", tarja_de(db, con_otro).estado == EstadoTarja.PARCIAL and kilos_de(datos, con_otro) == (Decimal(200), Decimal(720)))
        # HU12 descuenta solo lo vigente.
        anular(p_2["id"])
        comprobar("HU25 - sin procesos vigentes vuelve a recepcionada", tarja_de(db, con_otro).estado == EstadoTarja.RECEPCIONADA)

        # Una tarja cerrada con saldo 0 se reabre.
        cerrada = nueva_tarja(datos)
        _, p_c1 = procesar(datos, datos["caja_10"], fila(cerrada, 90))
        _, p_c2 = procesar(datos, datos["caja_10"], fila(cerrada, 2))
        comprobar("HU25 - parte cerrada con saldo 0", tarja_de(db, cerrada).estado == EstadoTarja.PROCESADA)
        anular(p_c1["id"])
        comprobar("HU25 - saldo 0 se reabre", tarja_de(db, cerrada).estado == EstadoTarja.PARCIAL and kilos_de(datos, cerrada) == (Decimal(20), Decimal(900)))

        # Marca en el proceso anulado: se pierde.
        marca_propia = nueva_tarja(datos)
        _, p_m = procesar(datos, datos["caja_10"], fila(marca_propia, 10, tarja_terminada=True))
        anular(p_m["id"])
        comprobar("HU25 - su propia marca se pierde", tarja_de(db, marca_propia).estado == EstadoTarja.RECEPCIONADA and kilos_de(datos, marca_propia) == (Decimal(0), Decimal(920)))

        # Marca en otro proceso: también se pierde, porque se decidió con otros kilos.
        marca_otra = nueva_tarja(datos)
        _, p_a = procesar(datos, datos["caja_10"], fila(marca_otra, 5))
        _, p_b = procesar(datos, datos["caja_10"], fila(marca_otra, 5, tarja_terminada=True))
        comprobar("HU25 - parte con marca en otro proceso", tarja_de(db, marca_otra).estado == EstadoTarja.PROCESADA)
        anular(p_a["id"])
        db.expire_all()
        comprobar("HU25 - la marca de otro proceso se pierde", db.get(ProcesoTarja, (p_b["id"], marca_otra["id"])).tarja_terminada is False)
        comprobar("HU25 - queda pendiente, no con más merma", tarja_de(db, marca_otra).estado == EstadoTarja.PARCIAL and kilos_de(datos, marca_otra) == (Decimal(50), Decimal(870)))
        eventos = list(db.scalars(select(Auditoria).where(Auditoria.tabla == "proceso_tarjas", Auditoria.registro_id == f"{p_b['id']}:{marca_otra['id']}", Auditoria.motivo == f"Anulación del proceso {p_a['folio']}")))
        comprobar("HU25 - quitar la marca queda auditado", len(eventos) == 1)

        # Merma rebajada: se pierde; la vuelve a decidir el operador.
        rebajada = nueva_tarja(datos)
        _, p_r = procesar(datos, datos["caja_10"], fila(rebajada, 10))
        solicitar("POST", f"{BASE}/tarjas/{rebajada['id']}/terminar", datos["token_proceso"])
        comprobar("HU25 - parte con merma rebajada", tarja_de(db, rebajada).merma_rebajada is True)
        anular(p_r["id"])
        comprobar("HU25 - la merma rebajada se pierde", tarja_de(db, rebajada).merma_rebajada is False and tarja_de(db, rebajada).estado == EstadoTarja.RECEPCIONADA)
        _, rebajadas = solicitar("GET", f"{BASE}/tarjas-rebajadas", datos["token_proceso"])
        comprobar("HU25 - sale de las rebajadas", all(opcion["id"] != rebajada["id"] for opcion in rebajadas))
        # El sistema no decide solo: sigue pendiente hasta que el operador lo decida.
        estado, resultado = solicitar("POST", f"{BASE}/tarjas/{rebajada['id']}/terminar", datos["token_proceso"])
        comprobar("HU25 - el operador la vuelve a rebajar", estado == 200 and Decimal(resultado["kilos_merma"]) == 920)
        solicitar("POST", f"{BASE}/tarjas/{rebajada['id']}/reabrir", datos["token_proceso"])

        # Varias tarjas: todas vuelven.
        una = nueva_tarja(datos)
        otra = nueva_tarja(datos)
        _, p_v = procesar(datos, datos["caja_10"], fila(una, 3), fila(otra, 4))
        anular(p_v["id"])
        comprobar("HU25 - todas sus tarjas vuelven", kilos_de(datos, una) == (Decimal(0), Decimal(920)) and kilos_de(datos, otra) == (Decimal(0), Decimal(920)))
        # Se pueden procesar de nuevo.
        estado, de_nuevo = procesar(datos, datos["caja_10"], fila(una, 3))
        comprobar("HU25 - se procesa de nuevo con otro folio", estado == 201 and de_nuevo["folio"] != p_v["folio"] and kilos_de(datos, una) == (Decimal(30), Decimal(890)))
        # HU24: una tarja sin procesos vigentes ya se puede anular; el proceso anulado no lo impide.
        estado, _ = solicitar("POST", f"{BASE_TARJAS}/{otra['id']}/anular", datos["token_admin"])
        comprobar("HU24 - tras anular el proceso, la tarja se puede anular", estado == 200 and tarja_de(db, otra).estado == EstadoTarja.ANULADA)
        # El detalle del proceso anulado no ofrece kilos de la tarja anulada como disponibles para la fila.
        _, detalle = solicitar("GET", f"{BASE}/{p_v['id']}", datos["token_proceso"])
        comprobar("HU25 - el detalle muestra el estado actual de sus tarjas", {f["estado_tarja"] for f in detalle["tarjas"]} == {"PARCIAL", "ANULADA"})


# Decisión del 03/11: un proceso ya registrado se edita y los kilos que salen vuelven a la recepción.
def probar_edicion() -> None:
    # Escenario aislado.
    with aislado() as (db, _, _externa), api_con_sesion(db):
        # Datos comunes.
        datos = preparar(db)
        # Dos tarjas de la misma fruta.
        una = nueva_tarja(datos)
        otra = nueva_tarja(datos)
        # Proceso ya guardado con 10 cajas de 10 kg.
        _, proceso = procesar(datos, datos["caja_10"], fila(una, 10))
        # Ruta de la corrección.
        ruta = f"{BASE}/{proceso['id']}"

        # Ayuda: envía cómo debe quedar el proceso.
        def editar(*filas: dict, token: str | None = datos["token_proceso"], destino: str = ruta) -> tuple[int, object]:
            # Usa la API real.
            return solicitar("PUT", destino, token, {"tarjas": list(filas)})

        # Solo proceso y administración.
        antes = cantidades(db)
        comprobar("Editar - sin token 401", editar(fila(una, 1), token=None)[0] == 401)
        comprobar("Editar - recepción 403", editar(fila(una, 1), token=datos["token_recepcion"])[0] == 403)
        comprobar("Editar - gerencia 403", editar(fila(una, 1), token=datos["token_gerencia"])[0] == 403)
        # Datos inválidos.
        comprobar("Editar - sin tarjas 422", editar()[0] == 422)
        comprobar("Editar - tarja repetida 422", editar(fila(una, 1), fila(una, 2))[0] == 422)
        comprobar("Editar - cero cajas 422", editar(fila(una, 0))[0] == 422)
        comprobar("Editar - cambiar el embalaje 422", solicitar("PUT", ruta, datos["token_proceso"], {"embalaje_id": datos["granel"].id, "tarjas": [fila(una, 1)]})[0] == 422)
        comprobar("Editar - id sobre INT 422", editar(fila(una, 1), destino=f"{BASE}/2147483648")[0] == 422)
        # Lo que no existe.
        comprobar("Editar - proceso inexistente 404", editar(fila(una, 1), destino=f"{BASE}/2147483647")[0] == 404)
        comprobar("Editar - tarja inexistente 404", editar({"tarja_id": 2147483647, "cantidad_cajas": 1})[0] == 404)
        # Con embalaje fijo, los kilos los sigue calculando el sistema.
        comprobar("Editar - kilos del cliente 400", editar(fila(una, 1, kilos_procesados="1.00"))[0] == 400)
        # Nunca más de lo que tiene la tarja.
        estado, respuesta = editar(fila(una, 93))
        comprobar("Editar - sobreconsumo 409", estado == 409 and "920" in respuesta["detail"])
        comprobar("Editar - rechazos sin escrituras", cantidades(db) == antes and db.get(Proceso, proceso["id"]).kilos_salida == 100)
        # Lo disponible al editar incluye lo que la fila ya tiene.
        _, detalle = solicitar("GET", ruta, datos["token_proceso"])
        comprobar("Editar - informa lo disponible", Decimal(detalle["tarjas"][0]["kilos_disponibles"]) == 920)

        # Agregar fruta: la fila sube y se rebaja de la tarja de recepción.
        estado, editado = editar(fila(una, 15))
        comprobar("Editar - subir cajas 200", estado == 200 and Decimal(editado["tarjas"][0]["cantidad_cajas"]) == 15 and Decimal(editado["tarjas"][0]["kilos_procesados"]) == 150)
        comprobar("Editar - los totales se recalculan", Decimal(editado["cantidad_cajas"]) == 15 and Decimal(editado["kilos_salida"]) == 150)
        comprobar("Editar - conserva folio y embalaje", editado["folio"] == proceso["folio"] and editado["embalaje"] == proceso["embalaje"])
        comprobar("Editar - rebaja de la tarja de recepción", kilos_de(datos, una) == (Decimal(150), Decimal(770)))

        # El caso de Alejandro: sobraban 15 kilos y vuelven a su tarja de recepción.
        estado, editado = editar(fila(una, "13.5"))
        comprobar("Devolver - quitar 15 kg del proceso", estado == 200 and Decimal(editado["kilos_salida"]) == 135 and Decimal(editado["cantidad_cajas"]) == Decimal("13.5"))
        comprobar("Devolver - los 15 kg vuelven a la recepción", kilos_de(datos, una) == (Decimal(135), Decimal(785)))
        _, disponibles = solicitar("GET", f"{BASE}/tarjas-disponibles?numero_tarja={una['numero_tarja']}", datos["token_proceso"])
        comprobar("Devolver - quedan disponibles para otro proceso", Decimal(disponibles[0]["kilos_pendientes"]) == 785)

        # Otra tarja: se crea su fila.
        estado, editado = editar(fila(una, "13.5"), fila(otra, 3))
        comprobar("Editar - otra tarja crea su fila", estado == 200 and len(editado["tarjas"]) == 2 and Decimal(editado["kilos_salida"]) == 165)
        comprobar("Editar - la otra tarja queda parcial", tarja_de(db, otra).estado == EstadoTarja.PARCIAL)
        # Quitarla devuelve todos sus kilos; la fila se borra y la auditoría la conserva.
        estado, editado = editar(fila(una, "13.5"))
        comprobar("Quitar - la fila sale del proceso", estado == 200 and len(editado["tarjas"]) == 1 and Decimal(editado["kilos_salida"]) == 135)
        comprobar("Quitar - la tarja vuelve a recepcionada", tarja_de(db, otra).estado == EstadoTarja.RECEPCIONADA and kilos_de(datos, otra) == (Decimal(0), Decimal(920)))
        eventos = list(db.scalars(select(Auditoria).where(Auditoria.tabla == "proceso_tarjas", Auditoria.registro_id == f"{proceso['id']}:{otra['id']}", Auditoria.accion == AccionAuditoria.DELETE)))
        comprobar("Quitar - la auditoría conserva la fila", len(eventos) == 1 and "3.00" in eventos[0].valores_antes and eventos[0].valores_despues is None)
        # Sin cambios no se escribe nada.
        antes = cantidades(db)
        estado, _ = editar(fila(una, "13.5"))
        comprobar("Editar - sin cambios no escribe", estado == 200 and cantidades(db) == antes)
        # La auditoría guarda el antes y el después.
        eventos = list(db.scalars(select(Auditoria).where(Auditoria.tabla == "procesos", Auditoria.registro_id == str(proceso["id"]), Auditoria.accion == AccionAuditoria.UPDATE)))
        comprobar("Editar - auditoría de la cabecera", len(eventos) == 4 and all(proceso["folio"] in evento.motivo and evento.valores_antes for evento in eventos))
        eventos = list(db.scalars(select(Auditoria).where(Auditoria.tabla == "proceso_tarjas", Auditoria.registro_id == f"{proceso['id']}:{una['id']}", Auditoria.accion == AccionAuditoria.UPDATE)))
        eventos.sort(key=lambda evento: evento.id)
        comprobar("Editar - auditoría de la fila", len(eventos) == 2 and Decimal(json.loads(eventos[1].valores_antes)["cantidad_cajas"]) == 15 and Decimal(json.loads(eventos[1].valores_despues)["cantidad_cajas"]) == Decimal("13.5"))

        # Tarja cerrada sola con saldo 0: al devolver kilos vuelve a estar pendiente.
        cerrada_sola = nueva_tarja(datos)
        _, p_sola = procesar(datos, datos["caja_10"], fila(cerrada_sola, 92))
        comprobar("Devolver - parte cerrada con saldo 0", tarja_de(db, cerrada_sola).estado == EstadoTarja.PROCESADA)
        editar(fila(cerrada_sola, "90.5"), destino=f"{BASE}/{p_sola['id']}")
        comprobar("Devolver - saldo 0 se reabre", tarja_de(db, cerrada_sola).estado == EstadoTarja.PARCIAL and kilos_de(datos, cerrada_sola) == (Decimal(905), Decimal(15)))
        # Tarja con merma rebajada: la merma se tomó con otros kilos y deja de valer.
        rebajada = nueva_tarja(datos)
        _, p_reb = procesar(datos, datos["caja_10"], fila(rebajada, 10))
        solicitar("POST", f"{BASE}/tarjas/{rebajada['id']}/terminar", datos["token_proceso"])
        editar(fila(rebajada, "8.5"), destino=f"{BASE}/{p_reb['id']}")
        comprobar("Devolver - merma rebajada se reabre", tarja_de(db, rebajada).estado == EstadoTarja.PARCIAL and tarja_de(db, rebajada).merma_rebajada is False and kilos_de(datos, rebajada) == (Decimal(85), Decimal(835)))
        eventos = list(db.scalars(select(Auditoria).where(Auditoria.tabla == "tarjas", Auditoria.registro_id == str(rebajada["id"]), Auditoria.motivo == f"Edición del proceso {p_reb['folio']}")))
        comprobar("Devolver - la reapertura queda auditada", len(eventos) == 1)
        # Subir cajas no reabre: la merma solo baja.
        subida = nueva_tarja(datos)
        _, p_sub = procesar(datos, datos["caja_10"], fila(subida, 10))
        solicitar("POST", f"{BASE}/tarjas/{subida['id']}/terminar", datos["token_proceso"])
        estado, _ = editar(fila(subida, 12), destino=f"{BASE}/{p_sub['id']}")
        comprobar("Editar - subir con merma rebajada sigue cerrada", estado == 200 and tarja_de(db, subida).estado == EstadoTarja.PROCESADA and tarja_de(db, subida).merma_rebajada is True and kilos_de(datos, subida) == (Decimal(120), Decimal(0)))
        # La marca de otro proceso también deja de valer.
        marcada = nueva_tarja(datos)
        _, p_1 = procesar(datos, datos["caja_10"], fila(marcada, 5))
        _, p_2 = procesar(datos, datos["caja_10"], fila(marcada, 5, tarja_terminada=True))
        comprobar("Devolver - parte con marca", tarja_de(db, marcada).estado == EstadoTarja.PROCESADA)
        editar(fila(marcada, "3.5"), destino=f"{BASE}/{p_1['id']}")
        comprobar("Devolver - la marca de otro proceso se quita", tarja_de(db, marcada).estado == EstadoTarja.PARCIAL and db.get(ProcesoTarja, (p_2["id"], marcada["id"])).tarja_terminada is False)
        # Bajar y marcar a la vez es una decisión nueva: queda cerrada.
        decidida = nueva_tarja(datos)
        _, p_dec = procesar(datos, datos["caja_10"], fila(decidida, 10))
        editar(fila(decidida, 8, tarja_terminada=True), destino=f"{BASE}/{p_dec['id']}")
        comprobar("Editar - bajar y marcar queda cerrada", tarja_de(db, decidida).estado == EstadoTarja.PROCESADA and kilos_de(datos, decidida) == (Decimal(80), Decimal(0)))
        # Quitar la marca reabre la tarja.
        editar(fila(decidida, 8), destino=f"{BASE}/{p_dec['id']}")
        comprobar("Editar - quitar la marca reabre", tarja_de(db, decidida).estado == EstadoTarja.PARCIAL)

        # Una fila sin cambios conserva sus kilos aunque el catálogo cambie el peso.
        historica = nueva_tarja(datos)
        complemento = nueva_tarja(datos)
        _, p_hist = procesar(datos, datos["caja_1135"], fila(historica, 3))
        db.get(Embalaje, datos["caja_1135"].id).kg_por_caja = Decimal("12.00")
        db.commit()
        estado, editado = editar(fila(historica, 3), fila(complemento, 1), destino=f"{BASE}/{p_hist['id']}")
        comprobar("Editar - fila sin cambios conserva sus kilos", estado == 200 and Decimal(editado["kilos_salida"]) == Decimal("46.05"))
        db.get(Embalaje, datos["caja_1135"].id).kg_por_caja = Decimal("11.35")
        db.commit()

        # La regla de mezcla también vale al editar: el legado la olvidó.
        calidad_2 = Calidad(nombre=f"QA Calidad edición {datos['sistema'].id}", activo=True)
        db.add(calidad_2)
        db.commit()
        distinta = nueva_tarja(datos, calidad_id=calidad_2.id)
        antes = cantidades(db)
        estado, respuesta = editar(fila(una, "13.5"), fila(distinta, 1))
        comprobar("Editar - otra calidad 400 sin escrituras", estado == 400 and "calidad" in respuesta["detail"] and cantidades(db) == antes)
        # Tarjas nuevas cerradas o anuladas.
        cerrada = nueva_tarja(datos)
        solicitar("POST", f"{BASE}/tarjas/{cerrada['id']}/terminar", datos["token_proceso"])
        comprobar("Editar - tarja nueva terminada 409", editar(fila(una, "13.5"), fila(cerrada, 1))[0] == 409)
        anulada = nueva_tarja(datos)
        solicitar("POST", f"{BASE_TARJAS}/{anulada['id']}/anular", datos["token_admin"])
        comprobar("Editar - tarja nueva anulada 409", editar(fila(una, "13.5"), fila(anulada, 1))[0] == 409)
        # Un fallo al auditar revierte todo.
        antes = cantidades(db)
        actor = datos["actores"][RolUsuario.OPERADOR_PROCESO][0]
        entrada = ProcesoEdicion(tarjas=[{"tarja_id": una["id"], "cantidad_cajas": "1"}])
        with patch("app.services.proceso.registrar_auditoria", side_effect=RuntimeError("fallo simulado de auditoría")):
            # El error debe llegar hasta aquí.
            try:
                editar_proceso(db, proceso["id"], entrada, actor)
                revirtio = False
            # La corrección se revierte.
            except RuntimeError:
                revirtio = True
        db.expire_all()
        comprobar("Editar - fallo de auditoría revierte", revirtio and cantidades(db) == antes and db.get(Proceso, proceso["id"]).kilos_salida == 135 and kilos_de(datos, una) == (Decimal(135), Decimal(785)))
        # El embalaje desactivado no impide la corrección.
        db.get(Embalaje, datos["caja_10"].id).activo = False
        db.commit()
        comprobar("Editar - embalaje desactivado no bloquea", editar(fila(una, 14))[0] == 200)
        db.get(Embalaje, datos["caja_10"].id).activo = True
        db.commit()
        # A granel los kilos se ajustan a mano y lo que sobra vuelve.
        de_granel = nueva_tarja(datos)
        _, proceso_granel = procesar(datos, datos["granel"], fila(de_granel, 1, kilos_procesados="10.00"))
        ruta_granel = f"{BASE}/{proceso_granel['id']}"
        comprobar("Editar - granel sin kilos 400", editar(fila(de_granel, 1), destino=ruta_granel)[0] == 400)
        estado, editado = editar(fila(de_granel, 1, kilos_procesados="7.50"), destino=ruta_granel)
        comprobar("Editar - granel devuelve lo que sobra", estado == 200 and Decimal(editado["kilos_salida"]) == Decimal("7.50") and kilos_de(datos, de_granel) == (Decimal("7.50"), Decimal("912.50")))
        # Un proceso anulado no se edita.
        db.get(Proceso, proceso["id"]).anulado = True
        db.commit()
        estado, respuesta = editar(fila(una, 1))
        comprobar("Editar - proceso anulado 409", estado == 409 and "anulado" in respuesta["detail"])


# Varias tarjas en un proceso, sin mezclar fruta distinta.
def probar_varias_tarjas() -> None:
    # Escenario aislado.
    with aislado() as (db, _, _externa), api_con_sesion(db):
        # Datos comunes.
        datos = preparar(db)
        # Dos tarjas de la misma fruta.
        una = nueva_tarja(datos)
        otra = nueva_tarja(datos)
        # Se registran juntas.
        estado, proceso = procesar(datos, datos["caja_10"], fila(una, 10), fila(otra, 20, tarja_terminada=True))
        comprobar("Varias - 201", estado == 201 and len(proceso["tarjas"]) == 2)
        comprobar("Varias - totales suman las filas", Decimal(proceso["cantidad_cajas"]) == 30 and Decimal(proceso["kilos_salida"]) == 300)
        comprobar("Varias - cada tarja con su estado", tarja_de(db, una).estado == EstadoTarja.PARCIAL and tarja_de(db, otra).estado == EstadoTarja.PROCESADA)
        # Criterio 7: lo procesado queda vinculado a su tarja y a su productor.
        estado, detalle = solicitar("GET", f"{BASE}/{proceso['id']}", datos["token_proceso"])
        comprobar("Criterio 7 - detalle con tarja y productor", estado == 200 and {f["numero_tarja"] for f in detalle["tarjas"]} == {una["numero_tarja"], otra["numero_tarja"]} and all(f["productor_codigo"] == datos["productor"].codigo and f["productor_razon_social"] == datos["productor"].razon_social for f in detalle["tarjas"]))
        comprobar("Criterio 7 - detalle con el estado de cada tarja", {f["estado_tarja"] for f in detalle["tarjas"]} == {"PARCIAL", "PROCESADA"})
        comprobar("Criterio 7 - detalle con el responsable", detalle["registrado_por"] == "Actor QA Tarjas")
        # El listado muestra el proceso.
        _, lista = solicitar("GET", BASE, datos["token_proceso"])
        comprobar("Listado - el más reciente primero", lista and lista[0]["id"] == proceso["id"] and lista[0]["folio"] == proceso["folio"])

        # Caso de la planta (03/11): a un pallet le falta fruta y se completa con otra tarja de recepción.
        principal = nueva_tarja(datos)
        # El complemento puede venir de otro productor.
        otro_productor = Productor(rut=uuid.uuid4().hex[:8] + "-1", razon_social=f"QA Otro productor {datos['sistema'].id}", activo=True)
        db.add(otro_productor)
        db.commit()
        complemento = nueva_tarja(datos, productor_id=otro_productor.id)
        # Pallet de 100 cajas: 92 agotan la primera tarja y 8 salen de la segunda.
        estado, pallet = procesar(datos, datos["caja_10"], fila(principal, 92), fila(complemento, 8))
        comprobar("Pallet - se completa con otra tarja", estado == 201 and Decimal(pallet["cantidad_cajas"]) == 100 and Decimal(pallet["kilos_salida"]) == 1000)
        comprobar("Pallet - la primera se cierra sola", tarja_de(db, principal).estado == EstadoTarja.PROCESADA)
        comprobar("Pallet - la segunda sigue disponible con su saldo", tarja_de(db, complemento).estado == EstadoTarja.PARCIAL and kilos_de(datos, complemento) == (Decimal(80), Decimal(840)))
        comprobar("Pallet - cada fila conserva su productor", {f["productor_razon_social"] for f in pallet["tarjas"]} == {datos["productor"].razon_social, otro_productor.razon_social})

        # Dos tarjas distintas: si una no alcanza, no se guarda ninguna.
        antes = cantidades(db)
        limpia = nueva_tarja(datos)
        antes = cantidades(db)
        estado, _ = procesar(datos, datos["caja_10"], fila(limpia, 1), fila(una, 100))
        comprobar("Varias - una sin saldo rechaza todo", estado == 409 and cantidades(db) == antes and tarja_de(db, limpia).estado == EstadoTarja.RECEPCIONADA)

        # Otra calidad.
        calidad_2 = Calidad(nombre=f"QA Calidad 2 {datos['sistema'].id}", activo=True)
        # Otro sistema productivo.
        sistema_2 = SistemaProductivo(nombre=f"QA Sistema 2 {datos['sistema'].id}", activo=True)
        # Otra especie con su variedad.
        especie_2 = Especie(nombre=f"QA Especie 2 {datos['sistema'].id}", activo=True)
        db.add_all([calidad_2, sistema_2, especie_2])
        db.flush()
        variedad_otra_especie = Variedad(especie_id=especie_2.id, nombre=f"QA Variedad 2 {datos['sistema'].id}", activo=True)
        # Otra variedad de la misma especie.
        variedad_misma_especie = Variedad(especie_id=datos["variedad"].especie_id, nombre=f"QA Variedad 3 {datos['sistema'].id}", activo=True)
        db.add_all([variedad_otra_especie, variedad_misma_especie])
        db.commit()
        # Cada mezcla se rechaza con su mensaje.
        distinta_calidad = nueva_tarja(datos, calidad_id=calidad_2.id)
        distinto_sistema = nueva_tarja(datos, sistema_productivo_id=sistema_2.id)
        distinta_especie = nueva_tarja(datos, variedad_id=variedad_otra_especie.id)
        antes = cantidades(db)
        estado, respuesta = procesar(datos, datos["caja_10"], fila(limpia, 1), fila(distinta_calidad, 1))
        comprobar("Mezcla - otra calidad 400", estado == 400 and "calidad" in respuesta["detail"])
        estado, respuesta = procesar(datos, datos["caja_10"], fila(limpia, 1), fila(distinto_sistema, 1))
        comprobar("Mezcla - otro sistema productivo 400", estado == 400 and "sistema productivo" in respuesta["detail"])
        estado, respuesta = procesar(datos, datos["caja_10"], fila(limpia, 1), fila(distinta_especie, 1))
        comprobar("Mezcla - otra especie 400", estado == 400 and "especie" in respuesta["detail"])
        comprobar("Mezcla - rechazos sin escrituras", cantidades(db) == antes)
        # La variedad sí puede variar.
        misma_especie = nueva_tarja(datos, variedad_id=variedad_misma_especie.id)
        estado, _ = procesar(datos, datos["caja_10"], fila(limpia, 1), fila(misma_especie, 1))
        comprobar("Mezcla - otra variedad de la misma especie 201", estado == 201)

        # Sin máximo operativo, pero los totales deben caber en las columnas.
        muy_grande_1 = nueva_tarja(datos)
        muy_grande_2 = nueva_tarja(datos)
        db.get(Tarja, muy_grande_1["id"]).kilos_netos = 60000000
        db.get(Tarja, muy_grande_2["id"]).kilos_netos = 60000000
        db.commit()
        antes = cantidades(db)
        estado, respuesta = procesar(
            datos,
            datos["granel"],
            fila(muy_grande_1, 1, kilos_procesados="60000000.00"),
            fila(muy_grande_2, 1, kilos_procesados="60000000.00"),
        )
        comprobar("Capacidad - total sobre DECIMAL(10,2) 400", estado == 400 and "capacidad" in respuesta["detail"] and cantidades(db) == antes)


# Criterio 6: todo en una transacción y con auditoría.
def probar_transaccion_y_auditoria() -> None:
    # Escenario aislado.
    with aislado() as (db, _, _externa), api_con_sesion(db):
        # Datos comunes.
        datos = preparar(db)
        # Tarja para el proceso.
        tarja = nueva_tarja(datos)
        # Actor del service.
        actor = datos["actores"][RolUsuario.OPERADOR_PROCESO][0]
        # Entrada ya validada, como la entrega FastAPI.
        entrada = ProcesoCreate(embalaje_id=datos["caja_10"].id, tarjas=[{"tarja_id": tarja["id"], "cantidad_cajas": 10}])
        # Cuenta las filas antes del fallo.
        antes = cantidades(db)
        # Un fallo en cualquier evento de auditoría revierte todo.
        with patch("app.services.proceso.registrar_auditoria", side_effect=RuntimeError("fallo simulado de auditoría")):
            # El error debe llegar hasta aquí.
            try:
                registrar_proceso(db, entrada, actor)
                revirtio = False
            # El proceso se revierte.
            except RuntimeError:
                revirtio = True
        comprobar("Criterio 6 - fallo de auditoría propaga el error", revirtio)
        comprobar("Criterio 6 - fallo de auditoría sin filas", cantidades(db) == antes)
        comprobar("Criterio 6 - fallo de auditoría sin cambio de estado", tarja_de(db, tarja).estado == EstadoTarja.RECEPCIONADA)

        # Sin fallo, se guarda con sus tres auditorías.
        estado, proceso = procesar(datos, datos["caja_10"], fila(tarja, 10))
        comprobar("Criterio 6 - proceso guardado", estado == 201)
        # Ayuda: eventos de una tabla y un registro.
        def eventos(tabla: str, registro) -> list[Auditoria]:
            # Consulta en la misma transacción.
            return list(db.scalars(select(Auditoria).where(Auditoria.tabla == tabla, Auditoria.registro_id == str(registro))))
        # Cabecera.
        de_proceso = eventos("procesos", proceso["id"])
        comprobar("Auditoría - cabecera INSERT", len(de_proceso) == 1 and de_proceso[0].accion == AccionAuditoria.INSERT and de_proceso[0].usuario_id == actor.id and proceso["folio"] in de_proceso[0].valores_despues)
        # Detalle.
        de_fila = eventos("proceso_tarjas", f"{proceso['id']}:{tarja['id']}")
        comprobar("Auditoría - fila INSERT", len(de_fila) == 1 and de_fila[0].accion == AccionAuditoria.INSERT)
        # Tarja: pasa de RECEPCIONADA a PARCIAL.
        de_tarja = [evento for evento in eventos("tarjas", tarja["id"]) if evento.accion == AccionAuditoria.UPDATE]
        comprobar("Auditoría - tarja UPDATE con el cambio", len(de_tarja) == 1 and "RECEPCIONADA" in de_tarja[0].valores_antes and "PARCIAL" in de_tarja[0].valores_despues)
        # Un segundo proceso no cambia el estado: no se audita de nuevo la tarja.
        procesar(datos, datos["caja_10"], fila(tarja, 10))
        de_tarja = [evento for evento in eventos("tarjas", tarja["id"]) if evento.accion == AccionAuditoria.UPDATE]
        comprobar("Auditoría - sin cambio de estado no hay evento de tarja", len(de_tarja) == 1)
        # Consultar no audita.
        antes = cantidades(db)
        solicitar("GET", BASE, datos["token_proceso"])
        solicitar("GET", f"{BASE}/{proceso['id']}", datos["token_proceso"])
        solicitar("GET", f"{BASE}/tarjas-disponibles", datos["token_proceso"])
        solicitar("GET", f"{BASE}/embalajes", datos["token_proceso"])
        comprobar("Auditoría - consultar no escribe", cantidades(db) == antes)


# Ejecuta todos los escenarios y entrega el resultado.
def main() -> None:
    # Huellas iniciales en una conexión propia.
    with engine.connect() as conexion:
        inicio = base.huellas(conexion)
    # Guarda las dependencias para restaurarlas.
    overrides_anteriores = dict(app.dependency_overrides)
    # Un error inesperado no debe esconder el informe.
    try:
        # Roles de cada ruta.
        probar_roles()
        # Criterio 1.
        probar_folio()
        # Criterio 2.
        probar_kilos()
        # Datos inválidos.
        probar_validaciones()
        # Criterios 3, 4 y 6, con HU12, HU17 y HU24.
        probar_consumo_parcial()
        # Criterio 5 y rebaja a merma.
        probar_terminada_y_merma()
        # Varias tarjas, mezcla y criterio 7.
        probar_varias_tarjas()
        # Corrección de un proceso ya registrado.
        probar_edicion()
        # Anulación de un proceso (HU25).
        probar_anulacion()
        # Transacción y auditoría.
        probar_transaccion_y_auditoria()
    # Registra el error sin detener el informe.
    except Exception:
        # Cuenta el error como falla.
        base.fallas += 1
        # Identifica el error en la salida.
        print("FALLA probar_procesos: error inesperado", flush=True)
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
