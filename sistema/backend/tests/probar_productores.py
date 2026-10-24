"""HU07 — Pruebas reproducibles del servicio, HTTP, permisos y auditoría.

Ejecutar desde sistema/: docker compose exec -T backend python -m tests.probar_productores
Los commits del servicio quedan dentro de una transacción externa que se revierte.
No se ejecutan consultas ni pruebas al importar este módulo.
"""

# Ejecuta las solicitudes ASGI secuencialmente sin instalar un cliente HTTP.
import asyncio
# Calcula huellas sin imprimir el contenido de las filas preexistentes.
import hashlib
# Serializa solicitudes y recupera respuestas e instantáneas de auditoría.
import json
# Devuelve un código de salida que refleja cualquier fallo de la ejecución.
import sys
# Conserva la ubicación de los errores inesperados sin ocultarlos como éxitos.
import traceback
# Genera nombres, ids y RUT ficticios independientes de los datos existentes.
import uuid
# Describe el generador que administra cada escenario aislado.
from collections.abc import Iterator
# Garantiza la liberación de recursos al terminar cada escenario.
from contextlib import contextmanager
# Permite generar un token expirado sin esperar durante las pruebas.
from datetime import timedelta
# Anota los valores heterogéneos de solicitudes y eventos.
from typing import Any
# Sustituye solo límites concretos para provocar errores de negocio controlados.
from unittest.mock import Mock, patch
# Separa el path y el query string al construir una solicitud ASGI.
from urllib.parse import urlsplit

# Construye consultas de estado y de eventos realmente almacenados.
from sqlalchemy import select
# Anota la conexión y la transacción que controla exclusivamente la prueba.
from sqlalchemy.engine import Connection, Transaction
# Identifica errores reales del índice único o de la FK de auditoría.
from sqlalchemy.exc import IntegrityError
# Mantiene los commits de negocio dentro de savepoints de la transacción externa.
from sqlalchemy.orm import Session

# Dependencia única que se sustituye al probar HTTP; los permisos siguen siendo reales.
from app.core.database import engine, get_db
# Genera tokens reales sin imprimirlos ni depender de credenciales de usuarios reales.
from app.core.security import create_access_token, create_refresh_token
# Verifica que los RUT ficticios cumplan el mismo algoritmo usado por los schemas.
from app.core.validators import validar_rut_chileno
# Aplicación completa, incluidos router, validación y dependencias de permisos.
from app.main import app
# Permite inspeccionar los eventos y distinguir INSERT de UPDATE.
from app.models.auditoria import AccionAuditoria, Auditoria
# Modelo del catálogo que ejercitan los endpoints y el servicio.
from app.models.productor import Productor
# Actores temporales con los cuatro perfiles y sus asociaciones reales de roles.
from app.models.usuario import RolUsuario, Usuario, UsuarioRol
# Entradas reales de las pruebas directas del servicio.
from app.schemas.productor import ProductorCreate, ProductorUpdate
# Funciones reales, sin simular las escrituras ni el registro de auditoría.
from app.services import productor as servicio

# Tablas cuyas filas deben quedar exactamente como estaban antes de las pruebas.
TABLAS = (Usuario.__table__, UsuarioRol.__table__, Productor.__table__, Auditoria.__table__)
# Campos públicos que debe devolver cada productor sin información de autenticación.
CAMPOS_PRODUCTOR = {"id", "rut", "razon_social", "direccion", "telefono", "activo"}
# Contador de comprobaciones fallidas, incluido cualquier error inesperado.
fallas = 0
# Contador de comprobaciones ejecutadas para el resumen de la terminal.
comprobaciones = 0


# Distingue un caso ya informado de una excepción inesperada del escenario.
class ComprobacionFallida(AssertionError):
    """Interrumpe un escenario dependiente sin contar dos veces el mismo fallo."""


# Imprime un resultado identificable y actualiza ambos contadores.
def registrar(nombre: str, correcto: bool) -> None:
    global fallas, comprobaciones  # Conserva los totales de toda la ejecución.
    comprobaciones += 1  # Registra también comprobaciones de preparación y limpieza.
    fallas += 0 if correcto else 1  # Incrementa los fallos únicamente ante un rechazo.
    print(("OK    " if correcto else "FALLA ") + nombre, flush=True)  # Facilita seguir una ejecución larga.


# Detiene el escenario cuando un resultado invalida los pasos que dependen de él.
def comprobar(nombre: str, condicion: bool) -> None:
    registrar(nombre, condicion)  # Informa la condición antes de continuar o lanzar.
    if not condicion:  # Evita ejecutar acciones posteriores sobre resultados inválidos.
        raise ComprobacionFallida(nombre)  # Mantiene el caso como fallo de la ejecución.


# Resume las filas mediante conteos y hashes sin mostrar datos sensibles.
def huellas(conexion: Connection) -> dict[str, tuple[int, str]]:
    resultado = {}  # Guarda una huella independiente para cada tabla protegida.
    for tabla in TABLAS:  # Incluye productores, eventos y usuarios con sus roles.
        resumen = hashlib.sha256()  # Usa un orden estable y una huella de todo el contenido.
        cantidad = 0  # Cuenta filas, sin exigir secuencias consecutivas de IDENTITY.
        consulta = select(tabla).order_by(*tabla.primary_key.columns)  # Ordena por la PK completa.
        for fila in conexion.execute(consulta):  # Lee desde la conexión del escenario actual.
            texto = json.dumps(tuple(fila), default=str, ensure_ascii=True)  # Normaliza fechas y enums.
            resumen.update(texto.encode("utf-8") + b"\n")  # No imprime el contenido leído.
            cantidad += 1  # Incorpora la fila al conteo de control.
        resultado[tabla.name] = (cantidad, resumen.hexdigest())  # Conserva solo conteo y huella.
    return resultado  # Permite comparar rechazos y la conservación de filas preexistentes.


# Controla una transacción externa que los servicios nunca confirman.
@contextmanager
def aislamiento(nombre: str) -> Iterator[tuple[Session, Connection, Transaction]]:
    with engine.connect() as lectura:  # Esta lectura termina antes de abrir la transacción de prueba.
        inicial = huellas(lectura)  # Conserva el estado previo para verificar la limpieza del escenario.
    conexion = engine.connect()  # Proporciona la única conexión de todas las acciones del escenario.
    externa = None  # Permite limpiar también si falla la preparación de la transacción.
    db = None  # Evita intentar cerrar una sesión que no pudo construirse.
    try:  # Garantiza la reversión aunque fallen solicitudes, consultas o comprobaciones.
        externa = conexion.begin()  # Retiene la decisión final fuera de los servicios de negocio.
        db = Session(bind=conexion, autoflush=False, join_transaction_mode="create_savepoint")  # Aísla commits internos.
        yield db, conexion, externa  # Entrega los recursos al escenario sin compartirlos con otro.
    finally:  # Libera recursos antes de abrir otra conexión para consultar los resultados.
        try:  # Cierra primero la sesión y cualquier savepoint que mantenga abierto.
            if db is not None:  # Cubre una preparación incompleta de la sesión.
                db.close()  # No confirma la transacción externa.
        finally:  # La conexión se libera incluso si falla el cierre de la sesión.
            try:  # Revierte también las operaciones que el servicio confirmó dentro del escenario.
                if externa is not None and externa.is_active:  # No revierte una transacción ya terminada.
                    externa.rollback()  # Nunca se hace commit de esta transacción externa.
            finally:  # Evita dejar una conexión bloqueando otras pruebas.
                conexion.close()  # Finaliza todo acceso de este escenario antes de consultar desde otro.
        with engine.connect() as lectura:  # Ya no quedan escrituras sin confirmar en otra conexión.
            final = huellas(lectura)  # Comprueba tanto ausencia de filas temporales como conservación de las previas.
        comprobar(nombre + " — limpieza y filas preexistentes conservadas", final == inicial)  # No compara IDENTITY.


# Prepara identidades ficticias para verificar autenticación contra la base real.
def crear_actores(db: Session, conexion: Connection, externa: Transaction) -> dict[str, Usuario]:
    perfiles = {  # Incluye cada perfil y los casos de identidad adicionales de la guía.
        "admin": [RolUsuario.ADMINISTRADOR],  # Actor de las operaciones normales del mantenimiento.
        "recepcion": [RolUsuario.OPERADOR_RECEPCION],  # Perfil sin permiso administrativo.
        "proceso": [RolUsuario.OPERADOR_PROCESO],  # Segundo operador, del mismo rango que recepción.
        "gerencia": [RolUsuario.GERENCIA],  # Rango intermedio que tampoco puede administrar productores.
        "inactivo": [RolUsuario.ADMINISTRADOR],  # Un rol suficiente no habilita una cuenta inactiva.
        "multi": [RolUsuario.OPERADOR_PROCESO, RolUsuario.ADMINISTRADOR],  # Varios roles pueden incluir administrador.
    }  # Finaliza la configuración de actores del escenario.
    prefijo = "hu07_" + uuid.uuid4().hex[:16]  # Evita nombres fijos que puedan existir previamente.
    actores = {}  # Conserva los modelos mientras dura esta sesión aislada.
    for clave, roles in perfiles.items():  # Crea cada identidad con UUID explícito.
        actores[clave] = Usuario(  # No utiliza cuentas ni credenciales reales.
            id=str(uuid.uuid4()),  # Permite capturar el actor como escalar antes de un rollback.
            nombre_usuario=prefijo + "_" + clave,  # Respeta el máximo de 50 caracteres.
            nombre_completo="Prueba HU07 " + clave,  # Identifica el propósito temporal de la fila.
            password_hash="valor_ficticio_solo_pruebas_HU07",  # Las pruebas de tokens no requieren iniciar sesión.
            activo=clave != "inactivo",  # Mantiene un administrador deshabilitado para el caso 401.
            roles_asignados=[UsuarioRol(rol=rol) for rol in roles],  # Usa las asociaciones reales de permisos.
        )  # Finaliza la preparación de esta identidad.
    db.add_all(list(actores.values()))  # Agrega usuarios y roles a la misma sesión del escenario.
    db.flush()  # Comprueba la preparación y las restricciones antes de empezar las solicitudes.
    db.commit()  # Confirma solo el savepoint de preparación, sin confirmar la transacción externa.
    comprobar("Aislamiento — preparación conserva transacción externa", externa.is_active and conexion.in_transaction())  # Protege el escenario.
    return actores  # Entrega identidades que seguirán siendo válidas tras rollbacks del servicio.


# Genera un RUT ficticio válido y libre, sin tocar productores preexistentes.
def rut_disponible(db: Session) -> str:
    for _ in range(100):  # Limita los intentos si cambia mucho el catálogo de pruebas.
        cuerpo = str(10_000_000 + uuid.uuid4().int % 80_000_000)  # Utiliza un cuerpo decimal de ocho dígitos.
        suma = sum(int(digito) * (2 + indice % 6) for indice, digito in enumerate(reversed(cuerpo)))  # Calcula Módulo 11.
        resto = 11 - suma % 11  # Obtiene el valor previo a la conversión del DV.
        dv = "0" if resto == 11 else "K" if resto == 10 else str(resto)  # Representa los resultados especiales.
        rut = cuerpo + "-" + dv  # Construye una representación ya canónica.
        if validar_rut_chileno(rut) and db.scalar(select(Productor.id).where(Productor.rut == rut)) is None:  # Exige disponibilidad.
            return rut  # No reutiliza ni modifica registros que existían antes del escenario.
    raise RuntimeError("No se pudo obtener un RUT de prueba disponible")  # Expone la precondición fallida.


# Relee los eventos para comprobar JSON persistido, no solo objetos pendientes en memoria.
def eventos(db: Session, productor_id: int) -> list[Auditoria]:
    db.expire_all()  # Obliga al ORM a recuperar los valores almacenados en SQL Server.
    consulta = select(Auditoria).where(Auditoria.tabla == "productores", Auditoria.registro_id == str(productor_id))  # Aísla el productor.
    return list(db.scalars(consulta.order_by(Auditoria.id)).all())  # No exige ids consecutivos de auditoría.


# Envía una solicitud directamente a ASGI sin red ni paquetes adicionales.
async def solicitar(metodo: str, ruta: str, token: str | None = None, datos: Any = None) -> tuple[int, Any]:
    partes = urlsplit(ruta)  # Conserva separados path y query string, incluidos los filtros booleanos.
    cuerpo = json.dumps(datos, ensure_ascii=False).encode("utf-8") if datos is not None else b""  # Admite un cuerpo vacío.
    headers = [(b"host", b"pruebas-hu07")]  # Proporciona el host de una solicitud HTTP normal.
    if datos is not None:  # Declara tipo y longitud cuando se envía contenido JSON.
        headers.extend([(b"content-type", b"application/json"), (b"content-length", str(len(cuerpo)).encode("ascii"))])  # Describe el cuerpo.
    if token is not None:  # Usa el extractor Bearer real, sin sustituir la autenticación.
        headers.append((b"authorization", ("Bearer " + token).encode("ascii")))  # Nunca imprime el token.
    scope = {  # Incluye los campos requeridos por la interfaz ASGI HTTP.
        "type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"},  # Describe la interfaz utilizada.
        "http_version": "1.1", "method": metodo, "scheme": "http",  # Mantiene el método solicitado.
        "path": partes.path, "raw_path": partes.path.encode("utf-8"),  # Entrega el path sin query string.
        "query_string": partes.query.encode("utf-8"), "root_path": "",  # Permite que FastAPI valide los filtros.
        "headers": headers, "client": ("127.0.0.1", 12345), "server": ("pruebas-hu07", 80),  # Completa el contexto HTTP.
    }  # Finaliza el contexto de la solicitud de prueba.
    mensajes = []  # Acumula la respuesta emitida por FastAPI.
    entregado = False  # Garantiza que el cuerpo se reciba una sola vez.
    async def receive() -> dict:  # Proporciona los mensajes de entrada sin concurrencia.
        nonlocal entregado  # Comparte el estado de entrega de esta solicitud.
        if entregado:  # No vuelve a entregar un cuerpo que ya fue consumido.
            return {"type": "http.disconnect"}  # Representa el final del lado cliente.
        entregado = True  # Marca la única entrega del cuerpo de entrada.
        return {"type": "http.request", "body": cuerpo, "more_body": False}  # Entrega el JSON completo.
    async def send(mensaje: dict) -> None:  # Recibe los mensajes de salida del servidor ASGI.
        mensajes.append(mensaje)  # Conserva estado, cabeceras y segmentos del cuerpo.
    await app(scope, receive, send)  # Ejercita router, schemas, autenticación, servicio y SQL Server reales.
    estado = next(m["status"] for m in mensajes if m["type"] == "http.response.start")  # Recupera el código HTTP.
    respuesta = b"".join(m.get("body", b"") for m in mensajes if m["type"] == "http.response.body")  # Une el cuerpo completo.
    return estado, json.loads(respuesta) if respuesta else None  # Devuelve JSON público, nunca headers de autenticación.


# Compara código y contenido de la base antes y después de cada rechazo de escritura.
async def rechazar(db: Session, nombre: str, metodo: str, ruta: str, esperado: int, token: str | None, datos: Any) -> None:
    antes = huellas(db.connection()) if metodo in {"POST", "PUT"} else None  # Usa siempre la conexión del escenario.
    estado, _ = await solicitar(metodo, ruta, token, datos)  # No sustituye las funciones del router ni del servicio.
    comprobar(nombre + " — HTTP " + str(esperado), estado == esperado)  # Exige el rechazo previsto.
    if antes is not None:  # Un código HTTP por sí solo no demuestra ausencia de cambios.
        comprobar(nombre + " — sin cambios ni eventos", huellas(db.connection()) == antes)  # Incluye conteos y estados.


# Verifica una escritura HTTP y relee su auditoría desde SQL Server.
async def escribir(
    db: Session, nombre: str, metodo: str, ruta: str, token: str, datos: dict, actor_id: str,
    anterior: dict | None = None,  # Conserva el estado escalar anterior sin depender de objetos expirados.
) -> dict:
    cantidad = len(eventos(db, anterior["id"])) if anterior else 0  # Cuenta el historial anterior del productor temporal.
    estado, salida = await solicitar(metodo, ruta, token, datos)  # Usa el servicio real y su commit dentro del aislamiento.
    comprobar(nombre + " — respuesta HTTP", estado == (201 if metodo == "POST" else 200))  # Comprueba alta o edición.
    comprobar(nombre + " — seis campos públicos", set(salida) == CAMPOS_PRODUCTOR)  # Excluye hashes y campos internos.
    comprobar(nombre + " — identidad interna", isinstance(salida["id"], int) and (anterior is None or salida["id"] == anterior["id"]))  # Conserva el id.
    historial = eventos(db, salida["id"])  # Expira el ORM y lee eventos realmente insertados.
    comprobar(nombre + " — un evento nuevo", len(historial) == cantidad + 1)  # No acepta eventos perdidos ni duplicados.
    evento = historial[-1]  # La PK creciente ordena el historial, sin exigir ids consecutivos.
    accion = AccionAuditoria.INSERT if metodo == "POST" else AccionAuditoria.UPDATE  # Distingue alta de cambio.
    comprobar(nombre + " — acción y actor reales", evento.accion == accion and evento.usuario_id == actor_id)  # No confía en el JSON cliente.
    comprobar(nombre + " — tabla y registro auditados", evento.tabla == "productores" and evento.registro_id == str(salida["id"]))  # Vincula el evento.
    antes = json.loads(evento.valores_antes) if evento.valores_antes is not None else None  # Recupera NULL o la instantánea previa.
    comprobar(nombre + " — instantánea anterior", antes == anterior)  # La creación requiere NULL; la edición conserva el estado previo.
    comprobar(nombre + " — instantánea posterior", json.loads(evento.valores_despues) == salida)  # Verifica las seis columnas persistidas.
    return salida  # Permite que el siguiente cambio utilice el estado escalar ya comprobado.


# Conserva muestras sintéticas para no confundir cualquier IntegrityError con duplicidad.
def probar_clasificacion() -> None:
    muestras = [  # Incluye el formato ODBC y coincidencias numéricas o de índice que deben rechazarse.
        ("[23000] unique index 'ix_productores_rut' (2601)", True),  # Código e índice correctos.
        ("[23000] IX_PRODUCTORES_RUT (2627)", True),  # Admite el otro código de duplicidad y mayúsculas.
        ("[23000] ix_productores_rut", False),  # El SQLSTATE genérico no identifica una duplicidad.
        ("26010 ix_productores_rut", False),  # No acepta el código dentro de un número mayor.
        ("12627 ix_productores_rut", False),  # Rechaza también un prefijo numérico adicional.
        ("2601 ix_productores_rut_copia", False),  # Exige el nombre completo del índice de RUT.
        ("2627 copia_ix_productores_rut", False),  # No confunde otro índice que contenga el nombre.
        ("2601 ix_otra_tabla", False),  # Otra unicidad no corresponde al RUT de productores.
        ("[23000] FOREIGN KEY auditoria.usuario_id (547)", False),  # Una FK inválida conserva su error de integridad.
    ]  # Finaliza las muestras sin datos reales ni credenciales.
    for indice, (mensaje, esperado) in enumerate(muestras, 1):  # Da un identificador estable a cada caso.
        error = IntegrityError("operación sintética", {}, Exception(mensaje))  # Simula únicamente el mensaje del controlador.
        comprobar("Clasificación C" + str(indice), servicio._es_rut_duplicado(error) == esperado)  # Contrasta el contrato del helper.


# Ejecuta permisos, validaciones y operaciones reales por la interfaz ASGI.
async def casos_http(db: Session, actores: dict[str, Usuario]) -> None:
    anteriores = dict(app.dependency_overrides)  # Conserva cualquier configuración que tuviera otra herramienta.
    async def proveer_db() -> Any:  # Entrega la sesión sin cerrarla al terminar cada petición.
        yield db  # El escenario controla el ciclo de vida y el rollback externo.
    app.dependency_overrides[get_db] = proveer_db  # No reemplaza autenticación, roles ni servicios.
    try:  # Restaura las dependencias incluso si una comprobación interrumpe el escenario.
        rutas = app.openapi()["paths"]  # Comprueba también las rutas públicas documentadas.
        publicadas = {ruta: set(metodos) for ruta, metodos in rutas.items() if ruta.startswith("/api/v1/productores")}  # Selecciona el módulo.
        esperado = {"/api/v1/productores": {"get", "post"}, "/api/v1/productores/{productor_id}": {"get", "put"}}  # Define las cuatro operaciones.
        comprobar("P14 — cuatro rutas y sin DELETE en OpenAPI", publicadas == esperado)  # Evita omisiones o borrado físico.
        comprobar("Seguridad documentada en las cuatro operaciones", all(rutas[r][m].get("security") for r, metodos in esperado.items() for m in metodos))  # No sustituye las pruebas reales.
        admin_id, multi_id = actores["admin"].id, actores["multi"].id  # Guarda ids escalares antes de provocar rollbacks.
        nombres = {clave: actor.nombre_usuario for clave, actor in actores.items()}  # Evita depender de instancias expiradas para los tokens.
        tokens = {clave: create_access_token(nombre, []) for clave, nombre in nombres.items()}  # La autorización debe leer roles desde la base.
        inexistente = -1  # Utiliza un id que no requiera suponer el estado del contador IDENTITY.
        while db.get(Productor, inexistente) is not None:  # Comprueba la precondición si el entorno contiene ids negativos.
            inexistente -= 1  # Busca otro id ausente sin modificar registros existentes.
        ruta_ausente = "/api/v1/productores/" + str(inexistente)  # Reutiliza el id validado para GET y PUT.
        rut_base = rut_disponible(db)  # Elige un RUT válido que nunca modifique un productor preexistente.
        alta_base = {"rut": rut_base, "razon_social": "Prueba HU07 inicial"}  # Datos ficticios válidos para evaluar permisos.
        operaciones = [("GET", "/api/v1/productores", None), ("GET", ruta_ausente, None), ("POST", "/api/v1/productores", alta_base), ("PUT", ruta_ausente, {})]  # Prueba cada endpoint.
        identidades = {  # Todas deben fallar antes de cualquier escritura.
            "sin token": None,  # Ejercita el extractor Bearer real.
            "token inválido": "token_invalido",  # No contiene una firma JWT válida.
            "token expirado": create_access_token(nombres["admin"], [], timedelta(seconds=-10)),  # Mantiene el usuario pero invalida el tiempo.
            "refresh como acceso": create_refresh_token(nombres["admin"]),  # Exige type=access.
            "administrador inactivo": tokens["inactivo"],  # La base rechaza una identidad deshabilitada.
            "usuario inexistente": create_access_token("hu07_ausente_" + uuid.uuid4().hex[:16], []),  # No depende de cuentas reales.
        }  # Finaliza la matriz de identidades rechazadas.
        for nombre, token in identidades.items():  # Evalúa los casos de autenticación de forma secuencial.
            for metodo, ruta, datos in operaciones:  # Incluye alta y edición con entradas válidas.
                await rechazar(db, "Identidad " + nombre + " " + metodo + " " + ruta, metodo, ruta, 401, token, datos)  # Comprueba también ausencia de cambios.
        for clave in ("recepcion", "proceso", "gerencia"):  # Ninguno de estos perfiles administra productores.
            for metodo, ruta, datos in operaciones:  # No basta con proteger únicamente las escrituras.
                await rechazar(db, "P13 " + clave + " " + metodo + " " + ruta, metodo, ruta, 403, tokens[clave], datos)  # Usa sus roles reales de base.
        obsoleto = create_access_token(nombres["recepcion"], [RolUsuario.ADMINISTRADOR.value])  # Declara un privilegio que la base no concede.
        for metodo, ruta, datos in operaciones:  # Prueba el JWT desactualizado en todas las operaciones.
            await rechazar(db, "Rol JWT obsoleto " + metodo + " " + ruta, metodo, ruta, 403, obsoleto, datos)  # Los permisos deben proceder de la base.
        admin, multi = tokens["admin"], tokens["multi"]  # Sus JWT no declaran roles; los administradores se reconocen desde SQL Server.
        cuerpo, dv = rut_base.split("-")  # Prepara una presentación con puntos para comprobar normalización real.
        presentado = f"{int(cuerpo):,}".replace(",", ".") + "-" + dv.lower()  # Permite también comprobar K minúscula si corresponde.
        primero = await escribir(db, "P1/P2 — alta y auditoría", "POST", "/api/v1/productores", admin, dict(alta_base, rut=presentado), admin_id)  # Inserta usando el servicio real.
        comprobar("P1 — RUT canónico y estado activo", primero["rut"] == rut_base and primero["activo"] is True)  # Revisa valores generados y normalizados.
        ruta_primero = "/api/v1/productores/" + str(primero["id"])  # Conserva solo la identidad interna de prueba.
        dv_invalido = "0" if dv != "0" else "1"  # Garantiza un dígito distinto al correcto.
        rut_invalido = cuerpo + "-" + dv_invalido  # No depende de ejemplos fijos que pudieran existir.
        rut_largo = next("12345678901-" + digito for digito in "0123456789K" if validar_rut_chileno("12345678901-" + digito))  # DV correcto pero largo no permitido.
        invalidas_alta = [  # Conserva los rechazos principales del contrato de creación.
            {"razon_social": "Prueba HU07"},  # El RUT es obligatorio.
            dict(alta_base, rut=None),  # El alta no admite RUT nulo.
            dict(alta_base, rut=123456785),  # Evita errores internos con valores no textuales.
            dict(alta_base, rut=rut_invalido),  # El dígito verificador debe ser correcto.
            dict(alta_base, rut=rut_largo),  # Rechaza un RUT normalizado superior a 12 caracteres.
            dict(alta_base, razon_social="ab"),  # Respeta el mínimo de razón social.
            dict(alta_base, razon_social="a" * 151),  # Respeta el máximo de razón social.
            dict(alta_base, direccion="a" * 201),  # Evita desbordar el largo de dirección.
            dict(alta_base, telefono="1" * 21),  # Evita desbordar el largo de teléfono.
        ]  # Finaliza las entradas inválidas que no deben tocar SQL Server.
        for indice, datos in enumerate(invalidas_alta, 1):  # Identifica cada caso de forma reproducible.
            await rechazar(db, "P3/P6 — alta inválida V" + str(indice), "POST", "/api/v1/productores", 422, admin, datos)  # Compara estado y eventos.
        invalidas_edicion = [{"rut": rut_invalido}, {"rut": rut_largo}, {"rut": 123456785}, {"razon_social": "ab"}, {"razon_social": "a" * 151}, {"direccion": "a" * 201}, {"telefono": "1" * 21}]  # Mantiene límites al editar.
        for indice, datos in enumerate(invalidas_edicion, 1):  # Comprueba que no se altere el productor existente.
            await rechazar(db, "Edición inválida V" + str(indice), "PUT", ruta_primero, 422, admin, datos)  # El 422 no debe dejar auditoría.
        variantes = [rut_base, presentado, rut_base.replace("-", ""), "0" + rut_base, "00" + rut_base]  # Incluye el ajuste de ceros iniciales.
        unicode_cuerpo = "".join(chr(ord(digito) + 0xFEE0) for digito in cuerpo) + "-" + dv  # Usa dígitos Unicode que el validador acepta.
        for indice, variante in enumerate(variantes + [unicode_cuerpo], 1):  # Cada presentación representa el productor ya creado.
            await rechazar(db, "P4 — alta equivalente D" + str(indice), "POST", "/api/v1/productores", 409, admin, dict(alta_base, rut=variante))  # Verifica unicidad canónica.
        segundo_rut = rut_disponible(db)  # Reserva otra identidad que está libre en este escenario.
        segundo = await escribir(db, "P5 — alta opcional con administrador multirrol", "POST", "/api/v1/productores", multi, {"rut": segundo_rut, "razon_social": "Prueba HU07 segundo"}, multi_id)  # Comprueba el actor multirrol real.
        comprobar("P5 — contactos omitidos son NULL", segundo["direccion"] is None and segundo["telefono"] is None)  # Comprueba los campos opcionales.
        ruta_segundo = "/api/v1/productores/" + str(segundo["id"])  # Mantiene el id para consultas y conflictos.
        segundo = await escribir(db, "Edición multirrol", "PUT", ruta_segundo, multi, {"telefono": "123456789"}, multi_id, segundo)  # Audita al actor real de la edición.
        for ruta in ("/api/v1/productores", ruta_segundo):  # El administrador multirrol también puede consultar ambos recursos.
            estado, _ = await solicitar("GET", ruta, multi)  # No sustituye la dependencia require_rol.
            comprobar("Administrador multirrol consulta " + ruta, estado == 200)  # Sus cuatro operaciones quedan ejercitadas.
        primero = await escribir(db, "P7 — cambio de contacto", "PUT", ruta_primero, admin, {"direccion": "Camino de prueba HU07", "telefono": "987654321"}, admin_id, primero)  # Revisa ambos estados completos.
        for indice, datos in enumerate([{}, {"rut": None, "direccion": None, "telefono": None, "activo": None}, {"rut": "00" + rut_base}, {"razon_social": primero["razon_social"]}], 1):  # Define cambios sin efecto.
            antes = huellas(db.connection())  # Conserva el estado persistido del productor y de su historial.
            estado, salida = await solicitar("PUT", ruta_primero, admin, datos)  # No debe confirmar ni agregar eventos.
            comprobar("P8 — edición sin efecto N" + str(indice), estado == 200 and salida == primero and huellas(db.connection()) == antes)  # Nulos no limpian el contacto.
        nuevo_rut = rut_disponible(db)  # Corrige hacia una identidad que no pertenece a otro productor.
        primero = await escribir(db, "Corrección de RUT conserva id e historial", "PUT", ruta_primero, admin, {"rut": "0" + nuevo_rut}, admin_id, primero)  # Valida normalización y auditoría anterior/posterior.
        comprobar("Corrección guarda el nuevo RUT canónico", primero["rut"] == nuevo_rut)  # No confunde la identidad con el id interno.
        await rechazar(db, "Conflicto al corregir RUT", "PUT", ruta_primero, 409, admin, {"rut": segundo_rut})  # Incluye rechazo sin cambio ni evento.
        primero = await escribir(db, "P9 — desactivación conserva registro", "PUT", ruta_primero, admin, {"activo": False}, admin_id, primero)  # No hace DELETE físico.
        estado, detalle = await solicitar("GET", ruta_primero, admin)  # El detalle sigue disponible para mantenimiento.
        comprobar("P9 — detalle conserva productor inactivo", estado == 200 and detalle == primero)  # Conserva la identidad y el historial.
        for filtro, estado_esperado in (("", None), ("?activo=true", True), ("?activo=false", False)):  # No pierde False por una condición de Python.
            estado, lista = await solicitar("GET", "/api/v1/productores" + filtro, admin)  # Usa el filtro HTTP realmente parseado.
            comprobar("Consultas — listado " + (filtro or "general"), estado == 200 and all(set(p) == CAMPOS_PRODUCTOR for p in lista))  # Controla también la salida pública.
            ids = {p["id"] for p in lista}  # Usa identidades, sin depender de cantidades preexistentes.
            if estado_esperado is None:  # El mantenimiento general conserva activos e inactivos.
                comprobar("P9 — listado general incluye ambos estados", {primero["id"], segundo["id"]} <= ids)  # No desaparece el desactivado.
            else:  # Exige que todos los resultados respeten el filtro solicitado.
                comprobar("P10 — filtro " + str(estado_esperado), all(p["activo"] is estado_esperado for p in lista) and (segundo["id"] in ids) is estado_esperado and (primero["id"] in ids) is not estado_esperado)  # Comprueba ambos productores.
        segundo = await escribir(db, "Desactivar productor que reserva su RUT", "PUT", ruta_segundo, admin, {"activo": False}, admin_id, segundo)  # La unicidad incluye inactivos.
        await rechazar(db, "Alta con RUT de inactivo", "POST", "/api/v1/productores", 409, admin, {"rut": segundo_rut, "razon_social": "Prueba duplicada"})  # No reutiliza su identidad.
        await rechazar(db, "Corrección al RUT de inactivo", "PUT", ruta_primero, 409, admin, {"rut": segundo_rut})  # No permite ocupar un RUT reservado.
        primero = await escribir(db, "Reactivación conserva registro e historial", "PUT", ruta_primero, admin, {"activo": True}, admin_id, primero)  # Registra otro UPDATE.
        for metodo, datos in (("GET", None), ("PUT", {"activo": False})):  # Detalle y edición resuelven el mismo recurso inexistente.
            await rechazar(db, "P11 — productor ausente " + metodo, metodo, ruta_ausente, 404, admin, datos)  # No crea datos ni eventos nuevos.
        await rechazar(db, "Id no entero", "GET", "/api/v1/productores/no_entero", 422, admin, None)  # Deja actuar a la validación de FastAPI.
        antes = huellas(db.connection())  # Conserva el estado para comprobar que DELETE no altera la tabla.
        estado, _ = await solicitar("DELETE", ruta_primero, admin)  # No hay operación de borrado publicada.
        comprobar("P14 — DELETE responde 405 sin modificaciones", estado == 405 and huellas(db.connection()) == antes)  # Preserva productores e historial.
    finally:  # Restaura la aplicación aunque falle cualquier petición.
        app.dependency_overrides.clear()  # Retira el proveedor temporal de sesión.
        app.dependency_overrides.update(anteriores)  # Repone exactamente las dependencias que había al empezar.


# Mantiene toda la matriz HTTP dentro de una única transacción externa reversible.
def probar_http() -> None:
    with aislamiento("HTTP") as (db, conexion, externa):  # No abre otra sesión para leer cambios sin confirmar.
        actores = crear_actores(db, conexion, externa)  # Establece identidades dentro del savepoint de preparación.
        asyncio.run(casos_http(db, actores))  # Espera cada solicitud antes de lanzar la siguiente.
        comprobar("HTTP — commits conservaron la transacción externa", externa.is_active and conexion.in_transaction())  # Protege la limpieza final.


# Conserva el contrato de normalización y de ausencia de cambios sin tocar la base.
def probar_contratos() -> None:
    for rut, esperado in (("12.345.678-5", "12345678-5"), ("0012345678-5", "12345678-5"), ("6.000.000-k", "6000000-K")):  # Cubre variantes canónicas y K.
        alta = ProductorCreate(rut=rut, razon_social="Prueba HU07")  # Valida y normaliza mediante el contrato público.
        edicion = ProductorUpdate(rut=rut)  # La corrección debe usar las mismas reglas.
        comprobar("Schemas — normalización " + rut, alta.rut == edicion.rut == esperado)  # Detecta regresiones del helper compartido.
    modelo = Productor(id=1, rut="12345678-5", razon_social="Prueba HU07", direccion="Camino", telefono=None, activo=True)  # Objeto solo en memoria.
    for indice, datos in enumerate(({}, {"rut": "0012345678-5"}, {"direccion": None}, {"activo": True}), 1):  # Ninguno modifica este objeto.
        db = Mock(spec=Session)  # Hace observable cualquier consulta, commit o auditoría indebidos.
        salida = servicio.actualizar_productor(db, modelo, ProductorUpdate(**datos), Usuario(id="actor_simulado"))  # No requiere conexión real.
        comprobar("Sin cambios S" + str(indice) + " — sin commit ni auditoría", salida is modelo and not db.mock_calls)  # Exige retorno directo.


# Prepara un productor propio para los escenarios directos del servicio.
def crear_temporal(db: Session, actor: Usuario) -> Productor:
    datos = ProductorCreate(rut=rut_disponible(db), razon_social="Prueba HU07 servicio")  # El RUT no pertenece a datos anteriores.
    return servicio.crear_productor(db, datos, actor)  # El commit solo confirma el savepoint de la prueba.


# Fuerza la restricción real después de omitir exclusivamente la consulta previa.
def probar_indice_real() -> None:
    for operacion in ("alta", "edición"):  # Conserva ambos caminos de conflicto en SQL Server.
        with aislamiento("Índice real " + operacion) as (db, conexion, externa):  # Revierte toda la preparación al terminar.
            actores = crear_actores(db, conexion, externa)  # Establece un actor válido dentro de la transacción externa.
            reservado = crear_temporal(db, actores["admin"])  # Este RUT debe seguir reservado aunque quede inactivo.
            reservado = servicio.actualizar_productor(db, reservado, ProductorUpdate(activo=False), actores["admin"])  # Confirma el estado del titular.
            rut = reservado.rut  # Guarda el valor escalar antes del rollback esperado por la violación.
            destino = crear_temporal(db, actores["admin"]) if operacion == "edición" else None  # Nunca usa un productor preexistente.
            antes = huellas(db.connection())  # Incluye las auditorías correctas de la preparación.
            recibido = None  # Evita aprobar el escenario si la escritura no encuentra la restricción.
            with patch.object(db, "scalar", return_value=None) as preconsulta:  # Omite solo la búsqueda previa del servicio.
                try:  # La violación debe provenir del flush contra el índice único real.
                    if operacion == "alta":  # Intenta crear otra fila con el RUT reservado.
                        servicio.crear_productor(db, ProductorCreate(rut=rut, razon_social="Prueba duplicada"), actores["admin"])  # Usa la base real.
                    else:  # Corrige un productor propio hacia el RUT del otro inactivo.
                        servicio.actualizar_productor(db, destino, ProductorUpdate(rut=rut), actores["admin"])  # Conserva los ids internos.
                except servicio.ProductorDuplicadoError as error:  # Es la traducción esperada del código nativo de duplicidad.
                    recibido = error  # Conserva la causa únicamente en memoria para comprobar su origen.
            comprobar("Índice SQL Server " + operacion + " — preconsulta omitida", preconsulta.call_count == 1)  # No simula el flush ni el índice.
            causa = recibido.__cause__ if recibido is not None else None  # Inspecciona la cadena sin imprimir SQL ni parámetros.
            comprobar("Índice SQL Server " + operacion + " — duplicidad real clasificada", isinstance(causa, IntegrityError) and servicio._es_rut_duplicado(causa))  # Exige el error del controlador.
            comprobar("Índice SQL Server " + operacion + " — rollback conserva estado", huellas(db.connection()) == antes)  # No deja cambios ni eventos nuevos.
            comprobar("Índice SQL Server " + operacion + " — externa activa", externa.is_active and conexion.in_transaction())  # Permite la limpieza global.


# Provoca una FK inválida de auditoría y exige conservar el error original.
def probar_fk_auditoria() -> None:
    for operacion in ("alta", "edición"):  # Una FK errónea no puede convertirse en duplicidad de RUT en ningún camino.
        with aislamiento("FK de auditoría " + operacion) as (db, conexion, externa):  # Aísla el rollback de cada caso.
            actores = crear_actores(db, conexion, externa)  # Los datos válidos de preparación sobreviven al rollback del servicio.
            destino = crear_temporal(db, actores["admin"]) if operacion == "edición" else None  # Prepara un registro propio si se edita.
            actor_id = str(uuid.uuid4())  # Usa un identificador que no corresponda a un usuario real.
            comprobar("FK " + operacion + " — actor ausente", db.get(Usuario, actor_id) is None)  # Verifica la precondición antes de escribir.
            ausente = Usuario(id=actor_id)  # No agrega este objeto a la sesión: la FK debe rechazar su identificador.
            rut = rut_disponible(db)  # Evita que una duplicidad de RUT interfiera con la prueba de FK.
            antes = huellas(db.connection())  # Guarda los datos de preparación sin abrir otra sesión.
            recibido = None  # Distingue un error esperado de una operación indebidamente aceptada.
            with patch.object(db, "rollback", wraps=db.rollback) as revertir:  # Observa el rollback real sin sustituirlo.
                try:  # El error aparece al insertar el evento durante el commit del servicio.
                    if operacion == "alta":  # El productor debe revertirse aunque su propio flush haya sido correcto.
                        servicio.crear_productor(db, ProductorCreate(rut=rut, razon_social="Prueba FK"), ausente)  # Usa un actor inexistente.
                    else:  # La edición debe volver al estado anterior junto a su auditoría rechazada.
                        servicio.actualizar_productor(db, destino, ProductorUpdate(direccion="Cambio que debe revertirse"), ausente)  # Provoca la FK al auditar.
                except IntegrityError as error:  # No captura ProductorDuplicadoError como resultado correcto.
                    recibido = error  # Conserva la excepción original para comprobar la clasificación.
            comprobar("FK " + operacion + " — IntegrityError ajeno al RUT", recibido is not None and not servicio._es_rut_duplicado(recibido))  # No acepta un 409 falso.
            comprobar("FK " + operacion + " — rollback ejecutado", revertir.call_count == 1)  # Verifica el manejo transaccional del servicio.
            comprobar("FK " + operacion + " — sin escritura ni evento", huellas(db.connection()) == antes)  # Incluye contenido y conteos.
            comprobar("FK " + operacion + " — externa activa", externa.is_active and conexion.in_transaction())  # Mantiene el aislamiento tras la excepción.


# Simula un error solo después de insertar correctamente cambio y auditoría.
def probar_error_posterior() -> None:
    for operacion in ("alta", "edición"):  # Comprueba reversión de un registro nuevo y de una modificación.
        with aislamiento("Fallo posterior al flush " + operacion) as (db, conexion, externa):  # No comparte una sesión fallida con otro caso.
            actores = crear_actores(db, conexion, externa)  # Confirma la preparación únicamente dentro de la externa.
            destino = crear_temporal(db, actores["admin"]) if operacion == "edición" else None  # Conserva la fila anterior en la edición.
            rut = rut_disponible(db)  # Prepara una identidad propia para el alta fallida.
            antes = huellas(db.connection())  # Estado que debe recuperarse después del fallo simulado.
            captura = {}  # Guarda evidencia escalar antes de que los objetos expiren por el rollback.
            fallo = RuntimeError("Fallo intencional después del flush de productor y auditoría")  # Se distingue por identidad.
            def fallar_commit() -> None:  # Sustituye solo el límite de confirmación, manteniendo SQL y auditoría reales.
                evento = next(objeto for objeto in db.new if isinstance(objeto, Auditoria))  # Obtiene el evento todavía pendiente.
                db.flush()  # Inserta realmente el evento antes de provocar el error de negocio.
                captura["evento_id"] = evento.id  # Guarda el id generado, sin leerlo después del rollback.
                captura["productor_id"] = int(evento.registro_id)  # El registrador guarda el id de negocio como texto.
                captura["evento_insertado"] = db.scalar(select(Auditoria.id).where(Auditoria.id == evento.id)) == evento.id  # Consulta la fila real.
                captura["productor_insertado"] = db.scalar(select(Productor.id).where(Productor.id == captura["productor_id"])) == captura["productor_id"]  # Confirma presencia real.
                raise fallo  # El servicio debe ejecutar rollback antes de propagar este mismo error.
            recibido = None  # No aprueba el caso si la excepción no se propaga.
            with patch.object(db, "commit", side_effect=fallar_commit), patch.object(db, "rollback", wraps=db.rollback) as revertir:  # Restaura ambos métodos al salir.
                try:  # Realiza el cambio completo hasta el punto de confirmación simulado.
                    if operacion == "alta":  # Inserta un productor propio antes de la auditoría.
                        servicio.crear_productor(db, ProductorCreate(rut=rut, razon_social="Prueba fallo posterior"), actores["admin"])  # Conserva el actor válido.
                    else:  # Modifica un productor que ya estaba preparado en la transacción externa.
                        servicio.actualizar_productor(db, destino, ProductorUpdate(direccion="Cambio posterior al flush"), actores["admin"])  # Audita el estado anterior.
                except RuntimeError as error:  # Exige después la misma excepción que se provocó deliberadamente.
                    recibido = error  # No oculta otras excepciones como casos aprobados.
            comprobar("Fallo posterior " + operacion + " — ambas filas pasaron flush", captura.get("evento_insertado") is True and captura.get("productor_insertado") is True)  # No prueba solo memoria.
            comprobar("Fallo posterior " + operacion + " — error y rollback reales", recibido is fallo and revertir.call_count == 1)  # Conserva la causa de negocio.
            comprobar("Fallo posterior " + operacion + " — estado restaurado", huellas(db.connection()) == antes)  # Verifica datos anteriores y ausencia de filas nuevas.
            comprobar("Fallo posterior " + operacion + " — evento ausente", db.get(Auditoria, captura["evento_id"]) is None)  # Consulta por el id escalar guardado.
            comprobar("Fallo posterior " + operacion + " — externa activa", externa.is_active and conexion.in_transaction())  # Permite revertir la preparación final.


# Ejecuta todos los escenarios de uno en uno y preserva errores como fallos.
def main() -> int:
    global fallas, comprobaciones  # Reinicia los contadores si otra herramienta llama a main de nuevo.
    fallas, comprobaciones = 0, 0  # La importación no ejecuta esta preparación.
    dependencias = dict(app.dependency_overrides)  # Permite comprobar también la limpieza de la aplicación.
    try:  # Una precondición de entorno fallida debe terminar con código distinto de cero.
        with engine.connect() as conexion:  # Termina la lectura inicial antes de abrir escenarios de escritura.
            inicial = huellas(conexion)  # Conserva filas preexistentes sin imprimirlas.
        print("CONTEOS_INICIALES:", json.dumps({tabla: valor[0] for tabla, valor in inicial.items()}, sort_keys=True))  # Evidencia sin datos personales.
    except Exception:  # Informa errores de conexión o esquema sin ejecutar escrituras.
        registrar("Entorno — lectura inicial", False)  # Marca la ejecución como fallida.
        traceback.print_exc()  # Conserva la causa para corregir el entorno.
        print("RESULTADO: no se pudieron preparar las pruebas")  # No declara resultados no ejecutados.
        return 1  # Permite detectar el fallo desde la terminal.
    for escenario in (probar_clasificacion, probar_contratos, probar_http, probar_indice_real, probar_fk_auditoria, probar_error_posterior):  # Evita concurrencia entre conexiones.
        try:  # El contexto de cada escenario limpia sus recursos antes del siguiente.
            escenario()  # Ejecuta las pruebas reales o los contratos puros correspondientes.
        except ComprobacionFallida:  # El caso ya quedó registrado por comprobar.
            pass  # Continúa con otro escenario aislado sin duplicar el contador de fallos.
        except Exception:  # Un error inesperado nunca se convierte en un escenario aprobado.
            registrar(escenario.__name__ + " — excepción inesperada", False)  # Hace fallar el proceso.
            traceback.print_exc()  # Conserva la excepción original para investigarla.
    try:  # Comprueba la limpieza global incluso cuando hubo escenarios fallidos.
        with engine.connect() as conexion:  # Todas las transacciones externas anteriores ya terminaron.
            final = huellas(conexion)  # Lee desde otra conexión solo después de los rollback externos.
        print("CONTEOS_FINALES:", json.dumps({tabla: valor[0] for tabla, valor in final.items()}, sort_keys=True))  # Registra la ausencia de residuos.
        comprobar("Final — filas temporales ausentes y preexistentes intactas", final == inicial)  # Compara todas las columnas, incluidos estados y eventos.
        comprobar("Final — dependencias restauradas", app.dependency_overrides == dependencias)  # No deja un modo de prueba instalado.
    except ComprobacionFallida:  # El fallo global ya fue informado con su nombre.
        pass  # Conserva el resultado fallido para el código de salida.
    except Exception:  # Una lectura final fallida impide declarar el bloque correcto.
        registrar("Final — excepción al verificar limpieza", False)  # Incluye el fallo en el resumen.
        traceback.print_exc()  # Conserva la ubicación del error sin ocultarlo.
    print("COMPROBACIONES:", comprobaciones, "FALLAS:", fallas)  # Facilita registrar el conteo real en el acta.
    print("RESULTADO:", "todas las pruebas pasaron" if fallas == 0 else f"{fallas} comprobación(es) fallaron")  # Resume únicamente lo ejecutado.
    return 1 if fallas else 0  # Propaga fallos de comprobación y excepciones a la terminal.


# Permite importar helpers sin conectar a la base ni ejecutar pruebas.
if __name__ == "__main__":
    sys.exit(main())  # Informa un código distinto de cero ante cualquier fallo.
