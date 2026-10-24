"""HU21 — Pruebas del servicio de auditoría con datos temporales.

Ejecutar desde sistema/: docker compose exec -T backend python -m tests.probar_auditoria
Cada escenario real utiliza su propia sesión y revierte todos sus cambios.
"""

# Permite recuperar y comparar los valores serializados en el historial.
import json
# Proporciona el código de salida que indica si la ejecución falló.
import sys
# Conserva el detalle de cualquier error inesperado durante las pruebas.
import traceback
# Genera identificadores exclusivos para no depender de usuarios existentes.
import uuid
# Permite comparar fechas usando la convención UTC del proyecto.
from datetime import datetime, timezone
# Representa cantidades decimales que JSON no serializa de forma nativa.
from decimal import Decimal
# Simula una sesión para revisar el contrato antes de insertar datos reales.
from unittest.mock import Mock, call

# Construye consultas que verifican la ausencia de filas tras un rollback.
from sqlalchemy import select
# Identifica la violación de unicidad que debe revertir la transacción.
from sqlalchemy.exc import IntegrityError
# Restringe el simulador a los métodos de una sesión SQLAlchemy.
from sqlalchemy.orm import Session

# Abre sesiones con la configuración real del backend.
from app.core.database import SessionLocal
# Importa Usuario y registra también su tabla relacionada UsuarioRol.
from app.models.usuario import Usuario
# Modelo y acciones de los eventos que deben participar en la transacción.
from app.models.auditoria import AccionAuditoria, Auditoria
# Funciones del servicio que se verifican en este bloque.
from app.services.auditoria import _a_json, instantanea, registrar_auditoria

# Cuenta los casos fallidos para informar el resultado a la terminal.
fallas = 0


# Informa cada caso con el mismo formato general que las pruebas de E1.
def comprobar(nombre: str, condicion: bool) -> bool:
    """Registra el resultado de una comprobación y devuelve si fue correcta."""
    global fallas  # Actualiza el contador compartido por todos los escenarios.
    fallas += 0 if condicion else 1  # Incrementa únicamente cuando el caso falla.
    print(("OK    " if condicion else "FALLA ") + nombre)  # Identifica el caso en la salida.
    return condicion  # Permite detener las inserciones si falla el contrato de sesión.


# Crea un usuario inventado, con nombre único y sin credenciales reales.
def crear_usuario() -> Usuario:
    """Prepara un actor temporal con identificador conocido antes del flush."""
    identificador = str(uuid.uuid4())  # Genera un UUID independiente por usuario.
    return Usuario(  # Devuelve el objeto todavía sin agregarlo a una sesión.
        id=identificador,  # Permite conservar el id como escalar antes del rollback.
        nombre_usuario="hu21_" + identificador.replace("-", ""),  # Respeta el límite de 50 caracteres.
        nombre_completo="Actor temporal HU21",  # Usa un nombre inventado y reconocible.
        password_hash="valor_ficticio_solo_para_pruebas",  # No sirve para iniciar sesión.
        activo=True,  # Permite comprobar el estado en las instantáneas.
    )  # Finaliza la preparación del usuario temporal.


# Consulta únicamente después del rollback y usando la misma sesión del escenario.
def verificar_ausencia(db: Session, ids: tuple[str, ...], registro_id: str) -> None:
    """Exige que no queden usuarios temporales ni su evento de auditoría."""
    usuario = db.scalar(select(Usuario.id).where(Usuario.id.in_(ids)))  # Busca los ids guardados.
    evento = db.scalar(  # Consulta tanto el registro único como los actores temporales.
        select(Auditoria.id).where(  # Recupera solo un identificador si existe un residuo.
            (Auditoria.registro_id == registro_id) | Auditoria.usuario_id.in_(ids)  # Cubre todos los eventos del actor.
        )  # Finaliza el filtro que evita depender de instancias expiradas.
    )  # Ejecuta la consulta después de haber revertido las inserciones.
    if usuario is not None or evento is not None:  # Detecta cualquier fila temporal persistida.
        raise AssertionError("El rollback dejó un usuario temporal o su auditoría")  # Conserva el fallo como error.


# Revisa el control de la transacción antes de abrir sesiones reales.
def probar_contrato() -> bool:
    """El registrador solo debe agregar y devolver la misma instancia."""
    db = Mock(spec=Session)  # Impide usar métodos ajenos al contrato de una sesión.
    evento = registrar_auditoria(  # Prepara un evento sin conexión con la base real.
        db, "actor_simulado", "productores", 123, AccionAuditoria.UPDATE,  # Incluye un id numérico.
        antes={"activo": True}, despues={"activo": False},  # Proporciona estados distinguibles.
    )  # Termina la llamada cuyo comportamiento se inspecciona.
    correcto = (  # Comprueba todos los requisitos antes de permitir inserciones reales.
        db.mock_calls == [call.add(evento)]  # Excluye commit, rollback, flush y llamadas adicionales.
        and evento.registro_id == "123"  # El identificador debe convertirse a texto.
        and json.loads(evento.valores_antes) == {"activo": True}  # Comprueba el estado anterior serializado.
        and json.loads(evento.valores_despues) == {"activo": False}  # Comprueba el estado posterior serializado.
    )  # Finaliza la evaluación del contrato de sesión.
    return comprobar("Contrato de sesión: solo add, misma instancia y serialización", correcto)  # Informa el control previo.


# Comprueba los valores especiales de JSON sin necesidad de una transacción.
def probar_json() -> None:
    """Distingue NULL de objeto vacío y convierte tipos no nativos de JSON."""
    comprobar("B1 — NULL y objeto vacío", _a_json(None) is None and json.loads(_a_json({})) == {})  # Evita confundir {} con None.
    fecha = datetime(2026, 10, 24, 12, 30, tzinfo=timezone.utc)  # Fija un dato reproducible en UTC.
    valores = {"fecha": fecha, "cantidad": Decimal("123.45"), "accion": AccionAuditoria.INSERT}  # Incluye tipos heterogéneos.
    esperado = {"fecha": str(fecha), "cantidad": "123.45", "accion": "INSERT"}  # Expresa el contrato de default=str.
    comprobar("B3 — Fecha, Decimal y enum serializados", json.loads(_a_json(valores)) == esperado)  # Verifica el JSON recuperable.


# Agrupa los casos de alta y actualización dentro de una sesión temporal.
def probar_alta_y_cambio() -> None:
    """Verifica columnas, instantáneas, fecha y almacenamiento Unicode real."""
    db = SessionLocal()  # Abre una sesión exclusiva de este escenario.
    try:  # Garantiza la limpieza incluso si una consulta lanza un error.
        usuario = crear_usuario()  # Prepara un actor que no existía antes de la prueba.
        usuario_id = usuario.id  # Guarda el identificador como escalar antes de revertir.
        db.add(usuario)  # Agrega el actor a la transacción temporal.
        db.flush()  # Hace válida su FK sin confirmar los datos.
        posterior = instantanea(usuario, excluir={"password_hash"})  # Excluye explícitamente el hash.
        inicio = datetime.now(timezone.utc)  # Marca el límite inferior para la fecha generada.
        alta = registrar_auditoria(  # Prepara un alta sin valores anteriores ni motivo.
            db, usuario_id, "usuarios", usuario_id, AccionAuditoria.INSERT, despues=posterior,  # Usa la misma sesión.
        )  # Devuelve la instancia pendiente de inserción.
        db.flush()  # Genera el id y la fecha del evento sin hacer commit.
        db.refresh(alta)  # Lee el evento realmente almacenado, incluida su fecha SQL DATETIME.
        comprobar(  # Verifica la identidad y los datos principales del evento insertado.
            "A1 — INSERT con id, actor, tabla, registro y acción",  # Conserva la identificación de la guía.
            alta.id is not None and alta.usuario_id == usuario_id and alta.tabla == "usuarios"  # Revisa id y actor.
            and alta.registro_id == usuario_id and alta.accion == AccionAuditoria.INSERT,  # Revisa objetivo y acción.
        )  # Finaliza la comprobación del alta.
        comprobar("A2 — Alta sin valores anteriores", alta.valores_antes is None)  # Comprueba el NULL recuperado.
        recuperado = json.loads(alta.valores_despues)  # Recupera el estado posterior desde el JSON almacenado.
        esperado = {clave: str(valor) if isinstance(valor, datetime) else valor for clave, valor in posterior.items()}  # Normaliza fechas.
        comprobar("A3 — Valores posteriores completos", recuperado == esperado)  # Compara toda la instantánea del alta.
        comprobar(  # Comprueba exclusión del hash y de relaciones e información interna del ORM.
            "A4 — Sin hash, relaciones ni atributos internos",  # Describe el límite de la captura.
            "password_hash" not in posterior and "password_hash" not in recuperado  # Exige exclusión antes y después del JSON.
            and "roles_asignados" not in posterior and "_sa_instance_state" not in posterior  # Evita copiar relaciones o __dict__.
            and posterior["nombre_usuario"] == usuario.nombre_usuario and posterior["activo"] is True,  # Conserva datos de negocio.
        )  # Finaliza el control del contenido de la instantánea.
        fecha = alta.fecha_hora  # Obtiene el valor de fecha recargado desde SQL Server.
        if fecha is not None and fecha.tzinfo is None:  # SQL DATETIME no conserva información de zona.
            fecha = fecha.replace(tzinfo=timezone.utc)  # Interpreta el dato conforme a la convención UTC del proyecto.
        comprobar(  # Admite el pequeño redondeo de SQL DATETIME sin mezclar fechas con y sin zona.
            "A5 — Fecha persistida cercana a UTC",  # Expresa la convención horaria que debe respetarse.
            fecha is not None and -1 <= (fecha - inicio).total_seconds() <= 10  # Evita aceptar fechas lejanas o locales.
            and abs((datetime.now(timezone.utc) - fecha).total_seconds()) <= 10,  # Contrasta también con el final de la operación.
        )  # Finaliza el control de la fecha almacenada.
        anterior = instantanea(usuario, excluir={"password_hash"})  # Captura antes de modificar al usuario.
        usuario.nombre_completo = "Actor modificado HU21"  # Realiza un cambio real dentro de la transacción.
        posterior = instantanea(usuario, excluir={"password_hash"})  # Captura después del cambio.
        texto_largo = "Edición de piñón y ñandú: " * 40  # Supera 500 caracteres e incluye tildes y ñ.
        posterior["detalle_prueba"] = texto_largo  # Añade contenido extenso al JSON sin exceder una columna de usuario.
        cambio = registrar_auditoria(  # Registra los estados del cambio con motivo opcional.
            db, usuario_id, "usuarios", usuario_id, AccionAuditoria.UPDATE,  # Mantiene el mismo actor y registro.
            antes=anterior, despues=posterior, motivo="Corrección de nombre",  # Proporciona datos comprobables.
        )  # Prepara un segundo evento en la misma transacción.
        db.flush()  # Envía tanto el cambio del usuario como el evento UPDATE.
        db.refresh(cambio)  # Obliga a leer el JSON y el motivo desde SQL Server.
        comprobar(  # Verifica que la instantánea anterior no cambió junto con el objeto.
            "A6 — UPDATE conserva estados anterior y posterior",  # Identifica el escenario de edición.
            cambio.accion == AccionAuditoria.UPDATE  # Confirma la acción recuperada.
            and json.loads(cambio.valores_antes)["nombre_completo"] == "Actor temporal HU21"  # Conserva el nombre inicial.
            and json.loads(cambio.valores_despues)["nombre_completo"] == "Actor modificado HU21",  # Conserva el nombre nuevo.
        )  # Finaliza la comprobación de los dos estados.
        comprobar(  # Revisa el texto completo después de haber recargado desde la base.
            "B2 — Unicode y más de 500 caracteres persistidos",  # Verifica almacenamiento, no solo memoria del ORM.
            len(texto_largo) > 500 and json.loads(cambio.valores_despues)["detalle_prueba"] == texto_largo,  # Descarta truncamiento.
        )  # Finaliza la comprobación del texto extenso.
        comprobar("B4 — Motivo conservado y NULL permitido", cambio.motivo == "Corrección de nombre" and alta.motivo is None)  # Revisa ambos eventos.
        db.rollback()  # Revierte el usuario y los dos eventos antes de consultar su ausencia.
        verificar_ausencia(db, (usuario_id,), usuario_id)  # Detecta residuos sin abrir otra sesión.
    finally:  # Libera recursos aunque falle cualquier inserción o comprobación.
        db.rollback()  # Descarta cambios pendientes y termina las consultas posteriores al rollback.
        db.close()  # Devuelve la conexión al motor.


# Demuestra que un rollback explícito revierte filas que ya recibieron un flush.
def probar_rollback() -> None:
    """A7 — El usuario temporal y su auditoría se revierten juntos."""
    db = SessionLocal()  # Usa una sesión independiente del escenario de alta.
    try:  # Protege la limpieza de la transacción temporal.
        usuario = crear_usuario()  # Recrea un actor válido para este escenario.
        usuario_id = usuario.id  # Guarda el id sin depender del objeto después del rollback.
        db.add(usuario)  # Incorpora el usuario temporal a esta transacción.
        db.flush()  # Hace válida la referencia al actor antes de insertar el evento.
        evento = registrar_auditoria(db, usuario_id, "usuarios", usuario_id, AccionAuditoria.INSERT)  # Usa la misma sesión.
        db.flush()  # Envía también el evento antes de revertir.
        insertado = evento.id is not None  # Conserva evidencia escalar de su inserción.
        db.rollback()  # Revierte conjuntamente ambas filas.
        verificar_ausencia(db, (usuario_id,), usuario_id)  # Comprueba que ninguna fila sobrevivió.
        comprobar("A7 — Rollback conjunto después del flush", insertado)  # No acepta un evento nunca insertado.
    finally:  # Garantiza liberación aunque la consulta de ausencia falle.
        db.rollback()  # Termina cualquier transacción pendiente.
        db.close()  # Cierra esta sesión antes del siguiente escenario.


# Provoca únicamente la violación de unicidad prevista por el caso A8.
def probar_integridad() -> None:
    """A8 — Un nombre duplicado obliga a revertir los cambios y su auditoría."""
    db = SessionLocal()  # Aísla el estado de sesión que dejará el IntegrityError.
    try:  # Garantiza que un error inesperado tampoco deje datos pendientes.
        actor = crear_usuario()  # Prepara el primer usuario con nombre exclusivo.
        actor_id = actor.id  # Conserva el id del actor antes de revertir.
        db.add(actor)  # Agrega el usuario que causará la colisión posterior.
        db.flush()  # Inserta el actor temporal sin confirmar la transacción.
        duplicado = crear_usuario()  # Asigna otro UUID explícito al segundo usuario.
        duplicado.nombre_usuario = actor.nombre_usuario  # Duplica solo la clave única de nombre.
        duplicado_id = duplicado.id  # Guarda el objetivo de auditoría como escalar.
        db.add(duplicado)  # Prepara la inserción que debe violar la unicidad.
        registrar_auditoria(db, actor_id, "usuarios", duplicado_id, AccionAuditoria.INSERT)  # Usa un actor existente en la transacción.
        error_esperado = False  # Evita aprobar el caso si el flush no falla.
        try:  # Limita la captura al flush cuya violación de integridad se espera.
            db.flush()  # Intenta guardar el usuario duplicado y el evento.
        except IntegrityError:  # No oculta errores de conexión ni otras excepciones inesperadas.
            error_esperado = True  # Registra que la restricción rechazó la operación.
        db.rollback()  # Recupera la sesión antes de ejecutar cualquier consulta.
        verificar_ausencia(db, (actor_id, duplicado_id), duplicado_id)  # Comprueba ambos usuarios y su auditoría.
        comprobar("A8 — IntegrityError y rollback sin residuos", error_esperado)  # Exige que se haya recibido el error previsto.
    finally:  # Garantiza limpieza incluso si aparece un error distinto al esperado.
        db.rollback()  # Descarta cualquier cambio que siga pendiente.
        db.close()  # Cierra la sesión que recibió el error de integridad.


# Simula un fallo de negocio después de insertar correctamente usuario y evento.
def probar_error_posterior() -> None:
    """B5 — Un error posterior al flush también revierte ambas filas."""
    db = SessionLocal()  # Abre una transacción independiente del error de unicidad.
    try:  # Asegura el cierre aunque no se complete la simulación.
        usuario = crear_usuario()  # Prepara un actor que todavía no existe en la base.
        usuario_id = usuario.id  # Guarda su id antes de la reversión.
        db.add(usuario)  # Agrega el cambio de negocio temporal.
        db.flush()  # Hace disponible el actor para la FK de auditoría.
        evento = registrar_auditoria(db, usuario_id, "usuarios", usuario_id, AccionAuditoria.INSERT)  # Prepara su evento.
        db.flush()  # Inserta correctamente ambas filas antes del error simulado.
        insertado = evento.id is not None  # Guarda evidencia de la inserción de auditoría.
        try:  # Representa una operación de negocio posterior al flush.
            raise RuntimeError("Fallo de negocio simulado después del flush")  # Provoca el error intencional.
        except RuntimeError:  # Captura solo el error generado dentro de este bloque.
            db.rollback()  # El servicio de negocio revierte su transacción completa.
        verificar_ausencia(db, (usuario_id,), usuario_id)  # Consulta la ausencia de ambos registros tras revertir.
        comprobar("B5 — Error posterior al flush sin datos persistidos", insertado)  # Exige que el evento sí haya sido insertado.
    finally:  # Protege la liberación de recursos frente a errores inesperados.
        db.rollback()  # Termina las consultas o cambios pendientes de la sesión.
        db.close()  # Devuelve la conexión al motor.


# Organiza la ejecución y conserva como fallos las excepciones inesperadas.
def main() -> int:
    """Ejecuta el contrato primero y solo después los escenarios reales."""
    global fallas  # Incluye errores de ejecución en el resultado global.
    if not probar_contrato():  # Un contrato incorrecto podría confirmar datos de prueba.
        print("RESULTADO: contrato de sesión fallido; no se ejecutaron inserciones")  # Explica por qué se detiene la prueba.
        return 1  # Informa el fallo sin tocar la base de datos.
    for escenario in (probar_json, probar_alta_y_cambio, probar_rollback, probar_integridad, probar_error_posterior):  # Aísla los escenarios.
        try:  # Permite continuar con otra sesión si falla un escenario independiente.
            escenario()  # Ejecuta comprobaciones y limpieza del escenario actual.
        except Exception:  # Informa cualquier error inesperado como fallo, sin convertirlo en aprobado.
            fallas += 1  # Hace que el proceso termine con código distinto de cero.
            print("FALLA " + escenario.__name__ + ": error inesperado")  # Identifica el escenario interrumpido.
            traceback.print_exc()  # Conserva la excepción y su ubicación para investigar.
    print("\nRESULTADO:", "todas las pruebas pasaron" if fallas == 0 else f"{fallas} prueba(s) fallaron")  # Resume los resultados reales.
    return 1 if fallas else 0  # Propaga los fallos a la terminal o a la integración continua.


# Evita insertar datos al importar este módulo desde otra herramienta.
if __name__ == "__main__":
    sys.exit(main())  # Finaliza con el código correspondiente a las comprobaciones ejecutadas.
