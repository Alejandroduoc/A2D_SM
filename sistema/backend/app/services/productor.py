

# Permite identificar códigos completos y el nombre del índice en errores ODBC.
import re

# Construye consultas de productores con el estilo de SQLAlchemy 2.
from sqlalchemy import select

# Distingue las restricciones de integridad de los demás errores de la operación.
from sqlalchemy.exc import IntegrityError

# Anota la sesión existente que comparte el cambio con su auditoría.
from sqlalchemy.orm import Session

# Define las acciones que se guardan en cada evento del historial.
from app.models.auditoria import AccionAuditoria

# Modelo del catálogo que consulta y modifica este servicio.
from app.models.productor import Productor

# Representa al usuario autenticado que el router entrega como responsable.
from app.models.usuario import Usuario

# Contratos que proporcionan campos admitidos y RUT validado y normalizado.
from app.schemas.productor import ProductorCreate, ProductorUpdate

# Captura los estados y agrega auditoría a la misma sesión de negocio.
from app.services.auditoria import instantanea, registrar_auditoria


# Señala un conflicto de RUT que el router convertirá en una respuesta 409.
class ProductorDuplicadoError(Exception):
    """El RUT ya pertenece a otro productor, esté activo o inactivo."""


# Señala que el productor desapareció durante la edición; el router responde 404.
class ProductorNoEncontradoError(Exception):
    """El productor ya no existe al momento de bloquearlo."""


# Clasifica únicamente las violaciones del índice de RUT de productores.
def _es_rut_duplicado(error: IntegrityError) -> bool:
    """Exige un código SQL Server de duplicidad y el índice exacto de RUT."""
    # Inspecciona el error original sin imprimirlo ni exponerlo al cliente.
    mensaje = str(error.orig)
    # Evita confundir los códigos 2601 y 2627 con números que los contengan.
    codigo_duplicado = re.search(r"(?<!\d)(?:2601|2627)(?!\d)", mensaje)
    # No acepta índices con nombres parecidos, prefijos o sufijos adicionales.
    indice_rut = re.search(r"\bix_productores_rut\b", mensaje, re.IGNORECASE)
    # Un SQLSTATE genérico u otra restricción no bastan para clasificar el error.
    return codigo_duplicado is not None and indice_rut is not None


# Consulta el catálogo completo o filtra explícitamente por estado.
def listar_productores(db: Session, activo: bool | None = None) -> list[Productor]:
    """Lista productores por razón social e id, incluidos los inactivos si se pide."""
    # Prepara la consulta sin excluir productores por defecto.
    consulta = select(Productor)
    # Distingue False de la ausencia de filtro.
    if activo is not None:
        # SQL Server traduce la comparación con False a activo = 0.
        consulta = consulta.where(Productor.activo == activo)
    # Garantiza un orden estable aunque dos productores compartan razón social.
    consulta = consulta.order_by(Productor.razon_social, Productor.id)
    # Devuelve los modelos sin confirmar transacciones ni registrar auditoría.
    return list(db.scalars(consulta).all())


# Busca un productor por su identidad interna, independientemente de su estado.
def obtener_productor(db: Session, productor_id: int) -> Productor | None:
    """Devuelve None si no existe; el router resolverá la respuesta 404."""
    # Usa la búsqueda por clave primaria sin modificar el registro ni auditar.
    return db.get(Productor, productor_id)


# Confirma el alta del productor junto con el evento INSERT de su historial.
def crear_productor(db: Session, datos: ProductorCreate, usuario: Usuario) -> Productor:
    """Crea un productor activo con RUT único y auditoría del usuario autenticado."""
    # Protege también la consulta previa y la preparación del evento de auditoría.
    try:
        # Busca el RUT normalizado sin excluir productores desactivados.
        existente = db.scalar(select(Productor.id).where(Productor.rut == datos.rut))
        # La comprobación previa permite informar claramente un duplicado conocido.
        if existente is not None:
            # El router recibirá un error de negocio, sin detalles del controlador.
            raise ProductorDuplicadoError("Ya existe un productor con ese RUT")
        # Copia únicamente los campos permitidos por el schema de creación.
        productor = Productor(**datos.model_dump())
        # Agrega el productor a la sesión recibida.
        db.add(productor)
        # Obtiene su id y activo=True antes de preparar la instantánea del alta.
        db.flush()
        # Prepara el evento dentro de la transacción que contiene al productor.
        registrar_auditoria(
            db,  # Comparte la sesión del alta.
            usuario.id,  # Identifica al responsable obtenido por autenticación.
            "productores",  # Indica la tabla afectada.
            productor.id,  # Usa el id generado por el flush previo.
            AccionAuditoria.INSERT,  # Identifica la creación del registro.
            despues=instantanea(productor),  # Conserva las seis columnas del alta.
        )  # El registrador agrega el evento sin confirmar la transacción.
        # Confirma una sola vez el productor y su auditoría.
        db.commit()
    # El índice único cubre también altas simultáneas que superen la consulta previa.
    except IntegrityError as error:
        # Recupera la sesión y revierte tanto el cambio como cualquier evento pendiente.
        db.rollback()
        # Traduce solo los errores que identifican realmente el índice de RUT.
        if _es_rut_duplicado(error):
            # Conserva la causa para diagnóstico sin incluirla en el mensaje de negocio.
            raise ProductorDuplicadoError("Ya existe un productor con ese RUT") from error
        # Propaga intactas las demás restricciones, como una FK de auditoría inválida.
        raise
    # Incluye fallos al serializar, auditar, hacer flush o confirmar la operación.
    except Exception:
        # Descarta la operación completa antes de devolver el error al llamador.
        db.rollback()
        # Mantiene el error original, incluidos los duplicados de la consulta previa.
        raise
    # Recarga después del bloque de escritura: un fallo aquí no revierte el commit.
    db.refresh(productor)
    # Entrega el estado persistido al router que construirá la respuesta.
    return productor


# Edita campos, corrige RUT o cambia el estado conservando la identidad y el historial.
def actualizar_productor(
    db: Session,  # Sesión que comparte la edición con su evento de auditoría.
    productor: Productor,  # Registro existente que el router obtuvo previamente.
    datos: ProductorUpdate,  # Cambios validados y RUT normalizado por el schema.
    usuario: Usuario,  # Responsable autenticado, ajeno al JSON de la petición.
) -> Productor:
    """Audita y confirma solo cambios efectivos; False permite desactivar sin borrar."""
    # Protege las comprobaciones y toda la escritura previa al commit.
    try:
        # Omite campos ausentes o nulos, conservando explícitamente valores False.
        enviados = datos.model_dump(exclude_unset=True, exclude_none=True)
        # Dirección o teléfono vacíos quitan el dato: se guardan como NULL (decisión D3 del 2026-10-31).
        for campo in ("direccion", "telefono"):
            # El schema solo deja "" en estos dos campos opcionales.
            if enviados.get(campo) == "":
                enviados[campo] = None
        # Prepara únicamente diferencias respecto del estado actual del productor.
        cambios = {
            campo: valor  # Conserva el nuevo valor de cada campo admitido por el schema.
            for campo, valor in enviados.items()  # Recorre solo los campos enviados.
            if getattr(productor, campo) != valor  # Omite valores idénticos al estado actual.
        }  # Finaliza la selección de cambios efectivos.
        # No genera eventos ni confirma una edición que no modifica el registro.
        if not cambios:
            # Incluye un RUT equivalente con puntos o ceros iniciales ya normalizado.
            return productor
        # Bloquea la fila hasta el commit (como HU08 y HU09): si dos administradores
        # editan a la vez, el segundo espera y compara contra el estado ya guardado.
        # Usa execute (no scalar) para que el bloqueo sea independiente de la consulta de duplicados.
        vigente = db.execute(
            select(Productor)  # Relee el productor completo.
            .where(Productor.id == productor.id)  # Solo la fila que se edita.
            .with_hint(Productor, "WITH (UPDLOCK, HOLDLOCK)", dialect_name="mssql")  # Bloqueo de actualización.
            .execution_options(populate_existing=True)  # Reemplaza los valores antiguos en memoria.
        ).scalars().first()  # populate_existing actualiza el mismo objeto que recibió el servicio.
        # El registro pudo desaparecer entre la búsqueda del router y el bloqueo.
        if vigente is None:
            raise ProductorNoEncontradoError("Productor no encontrado")
        # Recalcula los cambios contra el estado bloqueado.
        productor = vigente
        cambios = {campo: valor for campo, valor in enviados.items() if getattr(productor, campo) != valor}
        # Otro administrador ya dejó exactamente estos valores: no hay nada que auditar.
        if not cambios:
            db.rollback()
            return productor
        # Consulta duplicados solo si el RUT realmente va a cambiar.
        if "rut" in cambios:
            # Busca cualquier otro productor con el RUT solicitado, incluso inactivo.
            existente = db.scalar(
                select(Productor.id).where(
                    Productor.rut == cambios["rut"],  # Compara el valor ya normalizado.
                    Productor.id != productor.id,  # Excluye la identidad del propio registro.
                )  # Finaliza los filtros de unicidad en edición.
            )  # Ejecuta la comprobación sin modificar el productor.
            # Impide asignar al registro el RUT que pertenece a otro productor.
            if existente is not None:
                # El router traducirá este conflicto de negocio a HTTP 409.
                raise ProductorDuplicadoError("Ya existe un productor con ese RUT")
        # Captura las seis columnas antes de aplicar cualquier modificación.
        antes = instantanea(productor)
        # Aplica únicamente los cambios efectivos permitidos por el schema.
        for campo, valor in cambios.items():
            # Conserva el id interno y permite cambiar RUT, contacto, nombre o estado.
            setattr(productor, campo, valor)
        # Comprueba restricciones, incluida la unicidad de RUT, antes de auditar.
        db.flush()
        # Agrega el evento UPDATE a la misma transacción de la edición.
        registrar_auditoria(
            db,  # Comparte la sesión que ya contiene la modificación.
            usuario.id,  # Conserva la identidad del usuario autenticado responsable.
            "productores",  # Indica la tabla afectada.
            productor.id,  # Conserva la identidad interna incluso al corregir el RUT.
            AccionAuditoria.UPDATE,  # Incluye corrección, desactivación y reactivación.
            antes=antes,  # Conserva el estado anterior completo.
            despues=instantanea(productor),  # Conserva el estado posterior completo.
        )  # El registro de auditoría queda pendiente del mismo commit.
        # Confirma una sola vez el cambio y su evento de historial.
        db.commit()
    # Cubre también correcciones simultáneas que choquen con el índice único.
    except IntegrityError as error:
        # Revierte conjuntamente el productor y su auditoría antes de clasificar el error.
        db.rollback()
        # Solo el código de duplicidad junto al índice de RUT justifica el conflicto.
        if _es_rut_duplicado(error):
            # Conserva el error original como causa sin exponerlo al cliente.
            raise ProductorDuplicadoError("Ya existe un productor con ese RUT") from error
        # No transforma errores de otras restricciones en un duplicado de RUT.
        raise
    # Incluye fallos de consulta, captura de estados, serialización y confirmación.
    except Exception:
        # Deja que el llamador reciba el error después de revertir la operación.
        db.rollback()
        # Conserva la excepción original para su tratamiento en la capa superior.
        raise
    # Mantiene la recarga fuera del bloque que confirmó la escritura.
    db.refresh(productor)
    # Devuelve el productor persistido, sin eliminarlo al desactivar.
    return productor
