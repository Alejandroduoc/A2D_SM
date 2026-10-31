"""HU10 — Pruebas reproducibles de tipos de bandeja y embalajes.

Ejecutar desde sistema/ con:
docker compose exec backend python -m tests.probar_bandejas_embalajes

Las escrituras usan una transacción externa. Los commit de los servicios quedan
como savepoints y todo se revierte al terminar, incluida la auditoría.
"""

# Genera nombres irrepetibles para no depender de los datos existentes.
import uuid
# Simula un fallo de auditoría para comprobar atomicidad.
from unittest.mock import patch

# Permite contar registros sin cargar todas sus columnas.
from sqlalchemy import func, select

# Motor y modelos usados para verificar ausencia de residuos.
from app.core.database import engine
from app.models.auditoria import AccionAuditoria, Auditoria
from app.models.embalaje import Embalaje
from app.models.tipo_bandeja import TipoBandeja
from app.models.usuario import RolUsuario
# Reutiliza el transporte ASGI y el aislamiento ya probados por HU09.
from tests.probar_calidades_sistemas import (
    aislado,
    api_con_sesion,
    crear_actor,
    eventos,
    solicitar,
    total_auditoria,
)


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


# Obtiene cantidades iniciales o finales desde una conexión independiente.
def cantidades() -> tuple[int, int, int]:
    # Abre una conexión únicamente para lecturas confirmadas.
    with engine.connect() as conexion:
        # Cuenta ambas tablas de HU10 y la auditoría completa.
        return (
            conexion.scalar(select(func.count()).select_from(TipoBandeja)),
            conexion.scalar(select(func.count()).select_from(Embalaje)),
            conexion.scalar(select(func.count()).select_from(Auditoria)),
        )


# Conserva el estado confirmado antes de iniciar escenarios temporales.
cantidades_iniciales = cantidades()


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


# La salida del contexto revierte usuarios, catálogos y auditorías temporales.
cantidades_finales = cantidades()
# Compara el estado confirmado antes y después de toda la prueba.
comprobar("Final — sin residuos", cantidades_finales == cantidades_iniciales)

# Informa un resumen compacto para integración y revisión humana.
print(f"RESULTADO HU10: {comprobaciones - fallas} correctas, {fallas} fallidas")
# Devuelve un código de error cuando existe alguna falla.
if fallas:
    # SystemExit distinto de cero permite detectar el fallo desde Docker o CI.
    raise SystemExit(1)
