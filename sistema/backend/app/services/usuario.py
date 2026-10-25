"""Alta, edición y cambio de contraseña de usuarios, con auditoría (HU21).

El router valida permisos y reglas de la petición; este servicio aplica los
cambios, registra la auditoría en la misma transacción y hace commit o rollback.
Las instantáneas de auditoría nunca incluyen password_hash.
"""

# Busca el código de error y el nombre del índice en el mensaje del controlador.
import re
# Anota los valores de la instantánea.
from typing import Any

# Consultas de SQLAlchemy 2.
from sqlalchemy import select
# Error que lanza SQL Server al violar el índice único de nombre_usuario.
from sqlalchemy.exc import IntegrityError
# Sesión que comparten el cambio y su auditoría.
from sqlalchemy.orm import Session

# Hash y verificación de contraseñas.
from app.core.security import hash_password, verify_password
# Acción de auditoría.
from app.models.auditoria import AccionAuditoria
# Modelos de usuario y de su tabla de roles.
from app.models.usuario import Usuario, UsuarioRol
# Datos ya validados por los schemas.
from app.schemas.auth import UsuarioCreate, UsuarioUpdate
# Captura de columnas y registro del evento.
from app.services.auditoria import instantanea, registrar_auditoria


# Nombre de la tabla en la auditoría.
TABLA = "usuarios"
# Columnas que nunca se copian a la auditoría.
EXCLUIR = frozenset({"password_hash"})


class UsuarioDuplicadoError(Exception):
    """El nombre de usuario ya pertenece a otra cuenta."""


class PasswordActualIncorrectaError(Exception):
    """La contraseña actual informada no coincide con la guardada."""


class PasswordRepetidaError(Exception):
    """La contraseña nueva es igual a la actual."""


# Reconoce solo la violación del índice único de nombre_usuario (códigos 2601/2627).
def _es_nombre_duplicado(error: IntegrityError) -> bool:
    mensaje = str(error.orig)
    codigo = re.search(r"(?<!\d)(?:2601|2627)(?!\d)", mensaje)
    indice = re.search(r"\bix_usuarios_nombre_usuario\b", mensaje, re.IGNORECASE)
    return codigo is not None and indice is not None


# Estado del usuario para la auditoría: columnas sin el hash, más la lista de roles.
def instantanea_usuario(usuario: Usuario) -> dict[str, Any]:
    # Los roles viven en otra tabla; se agregan ordenados para comparar fácil.
    return {**instantanea(usuario, excluir=EXCLUIR), "roles": sorted(rol.value for rol in usuario.roles)}


# Busca un usuario por nombre de login.
def buscar_por_nombre(db: Session, nombre_usuario: str) -> Usuario | None:
    return db.scalar(select(Usuario).where(Usuario.nombre_usuario == nombre_usuario))


# Crea la cuenta, sus roles y el evento INSERT en una sola transacción.
def crear_usuario(db: Session, datos: UsuarioCreate, actor: Usuario) -> Usuario:
    try:
        # La consulta previa da el mensaje claro en el caso normal.
        if buscar_por_nombre(db, datos.nombre_usuario) is not None:
            raise UsuarioDuplicadoError("El nombre de usuario ya existe")
        # Solo se guarda el hash; la contraseña original no sale de esta función.
        usuario = Usuario(
            nombre_usuario=datos.nombre_usuario,  # Nombre de login.
            nombre_completo=datos.nombre_completo,  # Nombre visible.
            password_hash=hash_password(datos.password),  # Hash bcrypt.
            roles_asignados=[UsuarioRol(rol=rol) for rol in datos.roles],  # Roles elegidos.
        )  # Finaliza la construcción del usuario.
        db.add(usuario)
        # flush genera el id (UUID) y valida el índice único antes de auditar.
        db.flush()
        # Registra el alta con el estado completo, sin el hash.
        registrar_auditoria(
            db,  # Misma sesión y transacción.
            actor.id,  # Administrador que crea la cuenta.
            TABLA,  # Tabla afectada.
            usuario.id,  # UUID de la cuenta creada.
            AccionAuditoria.INSERT,  # Alta.
            despues=instantanea_usuario(usuario),  # Estado inicial sin password_hash.
        )  # El evento queda pendiente del mismo commit.
        db.commit()
    except IntegrityError as error:
        # Deshace la cuenta, sus roles y la auditoría.
        db.rollback()
        # Dos altas simultáneas con el mismo nombre: la base gana y se responde 409.
        if _es_nombre_duplicado(error):
            raise UsuarioDuplicadoError("El nombre de usuario ya existe") from error
        raise
    except Exception:
        # Cualquier otro fallo tampoco deja datos a medias.
        db.rollback()
        raise
    # Recarga los valores generados por la base.
    db.refresh(usuario)
    return usuario


# Aplica solo los cambios efectivos y audita; sin cambios no escribe nada.
def actualizar_usuario(db: Session, usuario: Usuario, datos: UsuarioUpdate, actor: Usuario) -> Usuario:
    try:
        # exclude_none: un null enviado equivale a "no tocar" (roles null no deja sin roles).
        enviados = datos.model_dump(exclude_unset=True, exclude_none=True)
        # Roles actuales y pedidos como conjuntos: el orden no es un cambio.
        roles_actuales = set(usuario.roles)
        roles_nuevos = set(enviados["roles"]) if "roles" in enviados else roles_actuales
        # Detecta qué cambia de verdad.
        cambia_nombre = "nombre_completo" in enviados and enviados["nombre_completo"] != usuario.nombre_completo
        cambia_activo = "activo" in enviados and enviados["activo"] != usuario.activo
        cambia_roles = roles_nuevos != roles_actuales
        cambia_password = "password" in enviados
        # Nada que guardar: no hay commit ni auditoría.
        if not (cambia_nombre or cambia_activo or cambia_roles or cambia_password):
            return usuario
        # Estado anterior, capturado antes de modificar.
        antes = instantanea_usuario(usuario)
        # Aplica cada cambio efectivo.
        if cambia_nombre:
            usuario.nombre_completo = enviados["nombre_completo"]
        if cambia_activo:
            usuario.activo = enviados["activo"]
        if cambia_roles:
            # delete-orphan borra las filas de usuario_roles que ya no están en la lista.
            usuario.roles_asignados = [UsuarioRol(rol=rol) for rol in enviados["roles"]]
        if cambia_password:
            # El restablecimiento guarda solo el hash nuevo.
            usuario.password_hash = hash_password(enviados["password"])
        db.flush()
        # El hash no se audita: el motivo deja constancia del restablecimiento.
        registrar_auditoria(
            db,  # Misma sesión.
            actor.id,  # Administrador responsable.
            TABLA,  # Tabla afectada.
            usuario.id,  # Cuenta editada.
            AccionAuditoria.UPDATE,  # Edición, activación, desactivación o roles.
            antes=antes,  # Estado previo sin hash.
            despues=instantanea_usuario(usuario),  # Estado posterior sin hash.
            motivo="Restablecimiento de contraseña por administrador" if cambia_password else None,
        )  # El evento queda pendiente del mismo commit.
        db.commit()
    except Exception:
        # Deshace el cambio y su auditoría juntos.
        db.rollback()
        raise
    db.refresh(usuario)
    return usuario


# Cambia la contraseña de la propia cuenta después de comprobar la actual.
def cambiar_password_propia(db: Session, usuario: Usuario, password_actual: str, password_nueva: str) -> None:
    # La contraseña actual protege contra alguien que use una sesión abierta ajena.
    if not verify_password(password_actual, usuario.password_hash):
        raise PasswordActualIncorrectaError("La contraseña actual no es correcta")
    # Repetir la misma contraseña no aporta seguridad.
    if verify_password(password_nueva, usuario.password_hash):
        raise PasswordRepetidaError("La contraseña nueva debe ser distinta de la actual")
    try:
        # Estado sin hash: antes y después coinciden; el motivo explica el evento.
        estado = instantanea_usuario(usuario)
        # Guarda solo el hash nuevo.
        usuario.password_hash = hash_password(password_nueva)
        db.flush()
        registrar_auditoria(
            db,  # Misma sesión.
            usuario.id,  # La propia persona es la responsable.
            TABLA,  # Tabla afectada.
            usuario.id,  # Su propia cuenta.
            AccionAuditoria.UPDATE,  # Cambio de un dato existente.
            antes=estado,  # Sin password_hash.
            despues=estado,  # Sin password_hash.
            motivo="Cambio de contraseña propia",  # Deja constancia sin guardar la clave.
        )  # El evento queda pendiente del mismo commit.
        db.commit()
    except Exception:
        db.rollback()
        raise
