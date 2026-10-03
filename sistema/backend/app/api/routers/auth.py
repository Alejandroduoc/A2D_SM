"""Endpoints de autenticacion y administracion de usuarios.

La conexion a la base de datos se obtiene desde ``get_db``; 
la validacion del token se obtiene desde ``get_current_user``;
y la autorizacion por rol se obtiene desde ``require_rol``.
"""

# APIRouter agrupa las rutas de autenticacion bajo un mismo prefijo.
# Depends permite que FastAPI entregue automaticamente la sesion y el usuario.
# HTTPException permite responder errores HTTP controlados.
# status contiene constantes legibles para los codigos HTTP.
from fastapi import APIRouter, Depends, HTTPException, status

# Convierte una violacion de unicidad de SQL Server en una respuesta 409.
from sqlalchemy.exc import IntegrityError

# Session representa una sesion activa de SQLAlchemy.
from sqlalchemy.orm import Session

# Dependencias de autenticacion y autorizacion de E1.
from app.api.deps import get_current_user, require_rol

# Dependencia que abre y cierra una sesion por peticion.
from app.core.database import get_db

# Funciones centrales de seguridad para contrasenas y tokens JWT.
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)

# Modelo de usuario, asociacion N:M y enum de roles validos.
from app.models.usuario import RolUsuario, Usuario, UsuarioRol

# Contratos de entrada y salida de los endpoints.
from app.schemas.auth import (
    LoginRequest,
    TokenResponse,
    UsuarioCreate,
    UsuarioOut,
    UsuarioUpdate,
)


# Todas las rutas quedan bajo /auth.
# main.py agrega posteriormente el prefijo general /api/v1.
router = APIRouter(prefix="/auth", tags=["Autenticacion"])


def convertir_usuario_a_salida(usuario: Usuario) -> UsuarioOut:
    """Convierte un modelo SQLAlchemy en la respuesta publica de usuario.

    UsuarioOut solo declara los campos que se pueden devolver. Por eso la
    contrasena original y password_hash quedan fuera de toda respuesta.
    """

    return UsuarioOut.model_validate(usuario)


def buscar_usuario_por_nombre(
    db: Session,
    nombre_usuario: str,
) -> Usuario | None:
    """Busca un usuario por su nombre de inicio de sesion."""

    return (
        db.query(Usuario)
        .filter(Usuario.nombre_usuario == nombre_usuario)
        .first()
    )


@router.post("/login", response_model=TokenResponse)
def iniciar_sesion(
    datos: LoginRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Autentica a un usuario activo y entrega sus tokens.

    La respuesta es 401 cuando el usuario no existe, esta inactivo o la
    contrasena no coincide. El mensaje es el mismo para no revelar si un
    nombre de usuario esta registrado.
    """

    usuario = buscar_usuario_por_nombre(db, datos.nombre_usuario)

    # password_hash solo se usa para comparar; nunca se devuelve al cliente.
    if (
        usuario is None
        or not usuario.activo
        or not verify_password(datos.password, usuario.password_hash)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nombre de usuario o contrasena incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Los roles se incluyen en el token como informacion para el cliente.
    # La autorizacion real vuelve a consultar la base de datos mediante
    # get_current_user, por lo que el JWT no es la fuente de permisos.
    roles = [rol.value for rol in usuario.roles]

    return TokenResponse(
        access_token=create_access_token(usuario.nombre_usuario, roles),
        refresh_token=create_refresh_token(usuario.nombre_usuario),
    )


@router.get("/me", response_model=UsuarioOut)
def obtener_usuario_actual(
    usuario: Usuario = Depends(get_current_user),
) -> UsuarioOut:
    """Devuelve los datos publicos del usuario autenticado."""

    return convertir_usuario_a_salida(usuario)


@router.get("/usuarios", response_model=list[UsuarioOut])
def listar_usuarios(
    db: Session = Depends(get_db),
    usuario_administrador: Usuario = Depends(
        require_rol(RolUsuario.ADMINISTRADOR)
    ),
) -> list[UsuarioOut]:
    """Lista todos los usuarios para un administrador."""

    # La variable activa la dependencia de autorizacion. El objeto no se usa
    # en la consulta porque el permiso ya fue validado antes de entrar aqui.
    _ = usuario_administrador

    usuarios = (
        db.query(Usuario)
        .order_by(Usuario.nombre_usuario)
        .all()
    )
    return [convertir_usuario_a_salida(usuario) for usuario in usuarios]


@router.post(
    "/usuarios",
    response_model=UsuarioOut,
    status_code=status.HTTP_201_CREATED,
)
def crear_usuario(
    datos: UsuarioCreate,
    db: Session = Depends(get_db),
    usuario_administrador: Usuario = Depends(
        require_rol(RolUsuario.ADMINISTRADOR)
    ),
) -> UsuarioOut:
    """Crea un usuario con uno o varios roles validos.

    Solo un administrador puede utilizar esta ruta. La contrasena se convierte
    en hash antes de agregar el objeto a la sesion de SQLAlchemy.
    """

    _ = usuario_administrador

    # La comprobacion previa permite entregar un mensaje claro en el caso
    # normal. La restriccion unique de la base cubre peticiones simultaneas.
    if buscar_usuario_por_nombre(db, datos.nombre_usuario) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El nombre de usuario ya existe",
        )

    usuario = Usuario(
        nombre_usuario=datos.nombre_usuario,
        nombre_completo=datos.nombre_completo,
        password_hash=hash_password(datos.password),
        roles_asignados=[UsuarioRol(rol=rol) for rol in datos.roles],
    )

    db.add(usuario)

    try:
        db.commit()
    except IntegrityError:
        # La transaccion debe volver atras antes de responder el error.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El nombre de usuario ya existe",
        )

    # Recarga los valores generados, como el UUID del usuario.
    db.refresh(usuario)
    return convertir_usuario_a_salida(usuario)


@router.put("/usuarios/{usuario_id}", response_model=UsuarioOut)
def actualizar_usuario(
    usuario_id: str,
    datos: UsuarioUpdate,
    db: Session = Depends(get_db),
    usuario_administrador: Usuario = Depends(
        require_rol(RolUsuario.ADMINISTRADOR)
    ),
) -> UsuarioOut:
    """Actualiza nombre completo, roles o estado de un usuario.

    Todos los campos son opcionales. Si se envia roles, la lista reemplaza
    todos los roles actuales del usuario.
    """

    _ = usuario_administrador

    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado",
        )

    cambios = datos.model_dump(exclude_unset=True, exclude_none=True)

    if (
        cambios.get("activo") is False
        and usuario.id == usuario_administrador.id
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes desactivar tu propio usuario administrador",
        )

    if (
        usuario.id == usuario_administrador.id
        and "roles" in cambios
        and RolUsuario.ADMINISTRADOR not in cambios["roles"]
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes quitarte el rol administrador a ti mismo",
        )

    if "nombre_completo" in cambios:
        usuario.nombre_completo = cambios["nombre_completo"]

    if "activo" in cambios:
        usuario.activo = cambios["activo"]

    if "roles" in cambios:
        usuario.roles_asignados = [
            UsuarioRol(rol=rol)
            for rol in cambios["roles"]
        ]

    db.commit()
    db.refresh(usuario)
    return convertir_usuario_a_salida(usuario)
