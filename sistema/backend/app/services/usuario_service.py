# Contiene la lógica de negocio relacionada con usuarios.
# Los routers solamente reciben solicitudes y delegan el procesamiento a este módulo.

from sqlalchemy.orm import Session

from app.models.usuario import Usuario, UsuarioRol
from app.schemas.usuario import UsuarioCreate
from app.core.security import hash_password


# Busca un usuario utilizando su nombre de usuario único.
def obtener_usuario_por_nombre(
    db: Session,
    nombre_usuario: str
) -> Usuario | None:
    # Consulta la base de datos para encontrar un usuario existente.
    return (
        db.query(Usuario)
        .filter(Usuario.nombre_usuario == nombre_usuario)
        .first()
    )


# Crea un nuevo usuario utilizando la información recibida desde la API.
def crear_usuario(
    db: Session,
    datos_usuario: UsuarioCreate
) -> Usuario:

    # Convierte la contraseña recibida en un hash seguro
    # antes de almacenarla en la base de datos.
    password_hash = hash_password(datos_usuario.password)

    # Construye la entidad Usuario que será almacenada.
    nuevo_usuario = Usuario(
        nombre_usuario=datos_usuario.nombre_usuario,
        nombre_completo=datos_usuario.nombre_completo,
        password_hash=password_hash,
        activo=datos_usuario.activo
    )

    # Asigna los roles seleccionados al nuevo usuario.
    for rol in datos_usuario.roles:
        nuevo_usuario.roles_asignados.append(
            UsuarioRol(rol=rol)
        )

    # Guarda el usuario dentro de la sesión actual.
    db.add(nuevo_usuario)

    # Confirma la transacción en la base de datos.
    db.commit()

    # Recarga el usuario para obtener los datos generados
    # durante la persistencia en la base de datos.
    db.refresh(nuevo_usuario)

    return nuevo_usuario