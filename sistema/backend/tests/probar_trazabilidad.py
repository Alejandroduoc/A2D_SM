"""HU23: prueba reproducible de la trazabilidad de una tarja.

Ejecutar desde sistema/: docker compose exec -T backend python -m tests.probar_trazabilidad
Todas las filas temporales quedan dentro de una transacción externa revertida.
"""

# Imprime el detalle de un error inesperado.
import traceback
# Pesos exactos, sin float.
from decimal import Decimal

# Conexión a la base.
from app.core.database import engine
# Genera un token con un rol que la base no respalda.
from app.core.security import create_access_token
# Aplicación real que reciben las peticiones.
from app.main import app
# Actores de la prueba.
from app.models.usuario import RolUsuario
# Reutiliza el aislamiento, los actores y los datos de las pruebas de tarjas y procesos.
from tests import probar_tarjas as base
from tests.probar_procesos import BASE as BASE_PROCESOS, BASE_TARJAS, cantidades, fila, nueva_tarja, preparar, procesar
from tests.probar_tarjas import aislado, api_con_sesion, comprobar, solicitar

# Ruta base del módulo.
BASE = "/api/v1/trazabilidad/tarjas"


# Busca en el historial el primer evento que contenga el texto.
def evento_con(historial: list[dict], texto: str) -> dict | None:
    # Sin coincidencias, None.
    return next((e for e in historial if texto in e["descripcion"]), None)


# Criterios de HU23.
def probar_trazabilidad() -> None:
    # Escenario aislado.
    with aislado() as (db, _, _externa), api_con_sesion(db):
        # Datos comunes.
        datos = preparar(db)
        # Tarja de 920 kg.
        tarja = nueva_tarja(datos)
        # Ruta de la consulta.
        ruta = f"{BASE}/{tarja['numero_tarja']}"
        # Cuenta las filas antes de consultar.
        antes = cantidades(db)

        # Roles: gerencia y administrador.
        comprobar("Roles - sin token 401", solicitar("GET", ruta)[0] == 401)
        comprobar("Roles - recepción 403", solicitar("GET", ruta, datos["token_recepcion"])[0] == 403)
        comprobar("Roles - proceso 403", solicitar("GET", ruta, datos["token_proceso"])[0] == 403)
        # El rol que cuenta es el de la base, no el del JWT.
        recepcion = datos["actores"][RolUsuario.OPERADOR_RECEPCION][0]
        token_obsoleto = create_access_token(recepcion.nombre_usuario, [RolUsuario.GERENCIA.value])
        comprobar("Roles - rol obsoleto del JWT 403", solicitar("GET", ruta, token_obsoleto)[0] == 403)
        estado, recorrido = solicitar("GET", ruta, datos["token_gerencia"])
        comprobar("Roles - gerencia 200", estado == 200)
        comprobar("Roles - administrador 200", solicitar("GET", ruta, datos["token_admin"])[0] == 200)
        # Entradas inválidas.
        comprobar("Consulta - inexistente 404", solicitar("GET", f"{BASE}/2147483647", datos["token_gerencia"])[0] == 404)
        comprobar("Consulta - número sobre INT 422", solicitar("GET", f"{BASE}/2147483648", datos["token_gerencia"])[0] == 422)
        comprobar("Consulta - número cero 422", solicitar("GET", f"{BASE}/0", datos["token_gerencia"])[0] == 422)
        comprobar("Consulta - texto 422", solicitar("GET", f"{BASE}/abc", datos["token_gerencia"])[0] == 422)

        # Criterio 3: no permite modificar datos.
        for metodo in ("POST", "PUT", "PATCH", "DELETE"):
            comprobar(f"Criterio 3 - {metodo} 405", solicitar(metodo, ruta, datos["token_gerencia"], {} if metodo != "DELETE" else None)[0] == 405)
        comprobar("Criterio 3 - consultar no escribe", cantidades(db) == antes)
        comprobar("Seguridad - sin credenciales", "password_hash" not in str(recorrido))

        # Criterio 1: productor y datos de la recepción.
        datos_tarja = recorrido["tarja"]
        comprobar("Criterio 1 - productor", datos_tarja["productor_razon_social"] == datos["productor"].razon_social and datos_tarja["productor_rut"] == datos["productor"].rut and datos_tarja["productor_codigo"] == datos["productor"].codigo)
        comprobar("Criterio 1 - datos de la recepción", datos_tarja["kilos_netos"] == 920 and datos_tarja["cantidad_bandejas"] == 50 and datos_tarja["especie"] and datos_tarja["variedad"] and datos_tarja["calidad"] and datos_tarja["sistema_productivo"] and datos_tarja["fecha_recepcion"])
        comprobar("Criterio 1 - recién recibida, sin procesos", recorrido["procesos"] == [] and Decimal(datos_tarja["kilos_pendientes"]) == 920)
        # Criterio 2: el alta queda en el historial.
        comprobar("Criterio 2 - alta de la tarja y de sus bandejas", evento_con(recorrido["historial"], "Tarja registrada") is not None and evento_con(recorrido["historial"], "Entrada de 50 bandejas") is not None)
        comprobar("Criterio 2 - responsable del alta", evento_con(recorrido["historial"], "Tarja registrada")["usuario"] == "Actor QA Tarjas")

        # Una impresión queda en el historial, con su cambio.
        solicitar("POST", f"{BASE_TARJAS}/{tarja['id']}/imprimir", datos["token_recepcion"])

        # Dos procesos.
        _, p_1 = procesar(datos, datos["caja_10"], fila(tarja, 40))
        _, p_2 = procesar(datos, datos["caja_1135"], fila(tarja, 20))
        _, recorrido = solicitar("GET", ruta, datos["token_gerencia"])
        # Criterio 1: los procesos en que entró, con su resultado.
        comprobar("Criterio 1 - sus procesos, en orden", [p["folio"] for p in recorrido["procesos"]] == [p_1["folio"], p_2["folio"]])
        proceso_1 = recorrido["procesos"][0]
        comprobar("Criterio 1 - resultado de cada proceso", Decimal(proceso_1["cantidad_cajas"]) == 40 and Decimal(proceso_1["kilos_procesados"]) == 400 and proceso_1["embalaje"] == datos["caja_10"].nombre and proceso_1["anulado"] is False and proceso_1["fecha_elaboracion"] and proceso_1["registrado_por"] == "Actor QA Tarjas")
        comprobar("Criterio 1 - kilos pendientes", Decimal(recorrido["tarja"]["kilos_procesados"]) == 627 and Decimal(recorrido["tarja"]["kilos_pendientes"]) == 293)
        comprobar("Criterio 1 - merma provisional", Decimal(recorrido["merma"]) == 293 and recorrido["merma_provisional"] is True)
        # Criterio 2: el historial.
        historial = recorrido["historial"]
        comprobar("Criterio 2 - impresión", evento_con(historial, "Impresión") is not None and evento_con(historial, "Impresión")["cambios"] == [{"campo": "Veces impresa", "antes": "0", "despues": "1"}])
        comprobar("Criterio 2 - entró al proceso", evento_con(historial, f"Entró al proceso {p_1['folio']}: 40 cajas y 400,00 kg") is not None)
        comprobar("Criterio 2 - cambio de estado legible", any(c == {"campo": "Estado", "antes": "Recepcionada", "despues": "Parcial"} for e in historial for c in e["cambios"]))
        comprobar("Criterio 2 - en orden de ocurrencia", historial == sorted(historial, key=lambda e: e["fecha_hora"]) and historial[0]["descripcion"] == "Tarja registrada")

        # Editar: el antes y el después.
        solicitar("PUT", f"{BASE_PROCESOS}/{p_1['id']}", datos["token_proceso"], {"tarjas": [fila(tarja, "38.5")]})
        _, recorrido = solicitar("GET", ruta, datos["token_gerencia"])
        editado = evento_con(recorrido["historial"], f"Cambió en el proceso {p_1['folio']}")
        comprobar("Criterio 2 - edición con antes y después", editado is not None and {"campo": "Cajas", "antes": "40", "despues": "38,5"} in editado["cambios"])
        comprobar("Criterio 2 - los kilos editados cambian", {"campo": "Kilos procesados", "antes": "400,00", "despues": "385,00"} in editado["cambios"])
        comprobar("Criterio 1 - kilos actualizados tras editar", Decimal(recorrido["tarja"]["kilos_pendientes"]) == 308)

        # Rebajar: queda con el motivo y los kilos, y la merma es definitiva.
        solicitar("POST", f"{BASE_PROCESOS}/tarjas/{tarja['id']}/terminar", datos["token_proceso"])
        _, recorrido = solicitar("GET", ruta, datos["token_gerencia"])
        comprobar("Criterio 2 - rebaja a merma con los kilos", evento_con(recorrido["historial"], "308,00 kg rebajado como merma") is not None)
        comprobar("Criterio 1 - merma definitiva", Decimal(recorrido["merma"]) == 308 and recorrido["merma_provisional"] is False and Decimal(recorrido["tarja"]["kilos_pendientes"]) == 0)
        cambios_rebaja = evento_con(recorrido["historial"], "rebajado como merma")["cambios"]
        comprobar("Criterio 2 - cambio legible de la merma", {"campo": "Merma rebajada", "antes": "No", "despues": "Sí"} in cambios_rebaja)
        solicitar("POST", f"{BASE_PROCESOS}/tarjas/{tarja['id']}/reabrir", datos["token_proceso"])

        # Anular un proceso sin que cambie el estado de la tarja: igual aparece.
        solicitar("POST", f"{BASE_PROCESOS}/{p_2['id']}/anular", datos["token_admin"])
        _, recorrido = solicitar("GET", ruta, datos["token_gerencia"])
        comprobar("Criterio 2 - anulación del proceso", evento_con(recorrido["historial"], f"Proceso {p_2['folio']} anulado") is not None)
        comprobar("Criterio 1 - el proceso anulado se ve marcado", [p["anulado"] for p in recorrido["procesos"]] == [False, True])
        comprobar("Criterio 1 - el proceso anulado no cuenta", Decimal(recorrido["tarja"]["kilos_procesados"]) == 385 and Decimal(recorrido["merma"]) == 535 and recorrido["merma_provisional"] is True)
        # El evento de editar un proceso no se duplica con su cabecera.
        comprobar("Criterio 2 - sin eventos duplicados de la cabecera", sum(p_1["folio"] in e["descripcion"] for e in recorrido["historial"]) == 2)

        # Quitar la tarja de un proceso: la fila se borra, pero el recorrido la conserva.
        otra = nueva_tarja(datos)
        _, p_3 = procesar(datos, datos["caja_10"], fila(tarja, 1), fila(otra, 2))
        solicitar("PUT", f"{BASE_PROCESOS}/{p_3['id']}", datos["token_proceso"], {"tarjas": [fila(otra, 2)]})
        _, recorrido = solicitar("GET", ruta, datos["token_gerencia"])
        comprobar("Criterio 2 - salida de un proceso", evento_con(recorrido["historial"], f"Salió del proceso {p_3['folio']}: volvieron 10,00 kg") is not None)
        comprobar("Criterio 1 - ya no figura en ese proceso", p_3["folio"] not in [p["folio"] for p in recorrido["procesos"]])

        # El historial no mezcla otra tarja, aunque su id termine igual o compartan proceso.
        _, de_otra = solicitar("GET", f"{BASE}/{otra['numero_tarja']}", datos["token_gerencia"])
        comprobar("Aislamiento - solo sus eventos", evento_con(de_otra["historial"], f"Salió del proceso {p_3['folio']}") is None and evento_con(de_otra["historial"], f"Entró al proceso {p_3['folio']}: 2 cajas") is not None)
        comprobar("Aislamiento - no ve procesos ajenos", [p["folio"] for p in de_otra["procesos"]] == [p_3["folio"]])
        comprobar("Aislamiento - no ve impresiones ajenas", evento_con(de_otra["historial"], "Impresión") is None)

        # Si solo cambia la marca, no aparece un falso cambio de cajas: "5.00" y "5" son lo mismo.
        marcada = nueva_tarja(datos)
        _, p_m = procesar(datos, datos["caja_10"], fila(marcada, 5))
        solicitar("PUT", f"{BASE_PROCESOS}/{p_m['id']}", datos["token_proceso"], {"tarjas": [fila(marcada, 5, tarja_terminada=True)]})
        _, de_marcada = solicitar("GET", f"{BASE}/{marcada['numero_tarja']}", datos["token_gerencia"])
        comprobar("Criterio 2 - solo cambia lo que cambió", evento_con(de_marcada["historial"], f"Cambió en el proceso {p_m['folio']}")["cambios"] == [{"campo": "Tarja terminada", "antes": "No", "despues": "Sí"}])
        comprobar("Criterio 2 - el motivo de la edición", evento_con(de_marcada["historial"], f"Edición del proceso {p_m['folio']}") is not None)
        # Al entrar al primer proceso, el texto dice lo que pasó.
        comprobar("Criterio 2 - cambio de estado explicado", evento_con(recorrido["historial"], "Cambió el estado de la tarja") is not None)

        # Tarja anulada: se consulta y no tiene merma.
        anulada = nueva_tarja(datos)
        solicitar("POST", f"{BASE_TARJAS}/{anulada['id']}/anular", datos["token_admin"])
        _, de_anulada = solicitar("GET", f"{BASE}/{anulada['numero_tarja']}", datos["token_gerencia"])
        comprobar("Anulada - se consulta y conserva sus datos", de_anulada["tarja"]["estado"] == "ANULADA" and de_anulada["merma"] is None and de_anulada["tarja"]["kilos_netos"] == 920)
        comprobar("Anulada - su historial lo dice", evento_con(de_anulada["historial"], "Tarja anulada") is not None and evento_con(de_anulada["historial"], "Entrada de bandejas anulada") is not None)
        comprobar("Anulada - cambio legible", any(c == {"campo": "Estado", "antes": "Recepcionada", "despues": "Anulada"} for e in de_anulada["historial"] for c in e["cambios"]))

        # Consultar nunca escribe.
        antes = cantidades(db)
        solicitar("GET", ruta, datos["token_gerencia"])
        comprobar("Criterio 3 - sin escrituras al final", cantidades(db) == antes)


# Ejecuta el escenario y entrega el resultado.
def main() -> None:
    # Huellas iniciales en una conexión propia.
    with engine.connect() as conexion:
        inicio = base.huellas(conexion)
    # Guarda las dependencias para restaurarlas.
    overrides_anteriores = dict(app.dependency_overrides)
    # Un error inesperado no debe esconder el informe.
    try:
        # Criterios de HU23.
        probar_trazabilidad()
    # Registra el error sin detener el informe.
    except Exception:
        # Cuenta el error como falla.
        base.fallas += 1
        # Identifica el error en la salida.
        print("FALLA probar_trazabilidad: error inesperado", flush=True)
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
