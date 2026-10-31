"""Endpoints de autenticacion y administracion de usuarios.

La conexion a la base de datos se obtiene desde ``get_db``;
la validacion del token se obtiene desde ``get_current_user``;
y la autorizacion por rol se obtiene desde ``require_rol``.
Las altas y ediciones de usuarios se auditan en ``app/services/usuario.py``.
"""

# APIRouter agrupa las rutas de autenticacion bajo un mismo prefijo.
# Depends permite que FastAPI entregue automaticamente la sesion y el usuario.
# HTTPException permite responder errores HTTP controlados.
# Request entrega la IP del cliente para el limite de intentos.
# Response permite responder 204 sin cuerpo.
# status contiene constantes legibles para los codigos HTTP.
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
# Formulario OAuth2 (username, password) que envía el botón Authorize de /docs.
from fastapi.security import OAuth2PasswordRequestForm
# Error de validación al convertir el formulario en LoginRequest.
from pydantic import ValidationError

# Session representa una sesion activa de SQLAlchemy.
from sqlalchemy.orm import Session

# Dependencias de autenticacion y autorizacion de E1.
from app.api.deps import get_current_user, require_rol

# Indica si /docs esta publicado (MOSTRAR_DOCS); en produccion no lo esta.
from app.core.config import settings

# Dependencia que abre y cierra una sesion por peticion.
from app.core.database import get_db

# Contador de intentos fallidos de login en memoria.
from app.core.limite_login import limite_login

# Funciones centrales de seguridad para contrasenas y tokens JWT.
from app.core.security import (
    HASH_FICTICIO,  # Se compara cuando el usuario no existe, para igualar el tiempo.
    create_access_token,  # Token de acceso de corta duracion.
    create_refresh_token,  # Token para renovar la sesion.
    decode_token,  # Valida firma, expiracion y campos obligatorios.
    verify_password,  # Compara contra el hash bcrypt.
)  # Finaliza las importaciones de seguridad.

# Modelo de usuario y enum de roles validos.
from app.models.usuario import RolUsuario, Usuario

# Contratos de entrada y salida de los endpoints.
from app.schemas.auth import (
    CambioPasswordRequest,  # Cambio de la propia contrasena.
    LoginRequest,  # Credenciales del login.
    RefreshRequest,  # Token de actualizacion.
    TokenResponse,  # Par de tokens entregado al cliente.
    UsuarioCreate,  # Alta de usuario.
    UsuarioOut,  # Respuesta publica sin password_hash.
    UsuarioUpdate,  # Edicion parcial de usuario.
)  # Finaliza las importaciones de schemas.

# Reglas de negocio y auditoria de usuarios.
from app.services.usuario import (
    PasswordActualIncorrectaError,  # Contrasena actual equivocada -> 400.
    PasswordRepetidaError,  # Nueva igual a la actual -> 400.
    UsuarioDuplicadoError,  # Nombre de usuario ocupado -> 409.
    actualizar_usuario,  # Edita y audita.
    buscar_por_nombre,  # Busca por nombre de login.
    cambiar_password_propia,  # Cambia la propia contrasena y audita.
    crear_usuario,  # Crea y audita.
)  # Finaliza las importaciones del servicio.


# Todas las rutas quedan bajo /auth.
# main.py agrega posteriormente el prefijo general /api/v1.
router = APIRouter(prefix="/auth", tags=["Autenticacion"])

# Mensaje unico del login fallido: no revela si el usuario existe o esta inactivo.
MENSAJE_LOGIN_FALLIDO = "Nombre de usuario o contraseña incorrectos"


def convertir_usuario_a_salida(usuario: Usuario) -> UsuarioOut:
    """Convierte un modelo SQLAlchemy en la respuesta publica de usuario.

    UsuarioOut solo declara los campos que se pueden devolver. Por eso la
    contrasena original y password_hash quedan fuera de toda respuesta.
    """

    return UsuarioOut.model_validate(usuario)


def emitir_tokens(usuario: Usuario) -> TokenResponse:
    """Entrega un par nuevo de tokens para un usuario ya validado."""

    # Los roles se incluyen en el token como informacion para el cliente.
    # La autorizacion real vuelve a consultar la base de datos mediante
    # get_current_user, por lo que el JWT no es la fuente de permisos.
    roles = [rol.value for rol in usuario.roles]
    return TokenResponse(
        access_token=create_access_token(usuario.nombre_usuario, roles),
        refresh_token=create_refresh_token(usuario.nombre_usuario),
    )


@router.post("/login", response_model=TokenResponse)
def iniciar_sesion(
    datos: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Autentica a un usuario activo y entrega sus tokens.

    La respuesta es 401 cuando el usuario no existe, esta inactivo o la
    contrasena no coincide. El mensaje es el mismo para no revelar si un
    nombre de usuario esta registrado. Tras varios fallos seguidos responde
    429 hasta que termine el bloqueo.
    """

    # Toda la logica esta en autenticar(), compartida con /auth/token.
    return autenticar(datos, request, db)


@router.post("/token", response_model=TokenResponse, include_in_schema=False)
def iniciar_sesion_docs(
    request: Request,
    formulario: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Login en formato de formulario, solo para el boton Authorize de /docs.

    Usa exactamente las mismas reglas que /auth/login (401 unico, bcrypt
    siempre y 429 tras varios fallos). No aparece en /docs y responde 404
    cuando /docs no esta publicado (produccion).
    """

    # Sin /docs publicado esta ruta no tiene uso: no se expone en produccion.
    if not settings.mostrar_docs:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    # Aplica los mismos limites de largo que el login en JSON.
    try:
        datos = LoginRequest(nombre_usuario=formulario.username, password=formulario.password)
    # Un largo invalido se rechaza igual que en /auth/login, sin comparar la contrasena.
    except ValidationError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Datos de inicio de sesión inválidos") from error
    # Comparte la logica de autenticacion con /auth/login.
    return autenticar(datos, request, db)


def autenticar(datos: LoginRequest, request: Request, db: Session) -> TokenResponse:
    """Valida las credenciales y entrega los tokens (usado por /login y /token)."""

    # IP del cliente (sin proxy delante es la IP real).
    ip = request.client.host if request.client else "desconocida"

    # Un usuario o una IP bloqueados no llegan a comparar la contrasena.
    espera = limite_login.segundos_bloqueo(datos.nombre_usuario, ip)
    if espera > 0:
        minutos = (espera + 59) // 60
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Demasiados intentos fallidos. Intenta nuevamente en {minutos} minuto(s).",
            headers={"Retry-After": str(espera)},
        )

    usuario = buscar_por_nombre(db, datos.nombre_usuario)

    # Siempre se ejecuta bcrypt, exista o no el usuario: asi el tiempo de
    # respuesta no delata que nombres de usuario estan registrados.
    hash_a_comparar = usuario.password_hash if usuario is not None else HASH_FICTICIO
    password_correcta = verify_password(datos.password, hash_a_comparar)

    # password_hash solo se usa para comparar; nunca se devuelve al cliente.
    if usuario is None or not usuario.activo or not password_correcta:
        # Cuenta el fallo tambien para usuarios inexistentes (no revela nada).
        limite_login.registrar_fallo(datos.nombre_usuario, ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=MENSAJE_LOGIN_FALLIDO,
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Un login correcto borra los fallos acumulados de ese usuario.
    limite_login.registrar_exito(datos.nombre_usuario, ip)
    return emitir_tokens(usuario)


@router.post("/refresh", response_model=TokenResponse)
def renovar_sesion(
    datos: RefreshRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Entrega tokens nuevos a partir de un refresh token vigente.

    Vuelve a consultar la base: un usuario desactivado o eliminado ya no
    puede renovar su sesion. Un access token no sirve aqui (type distinto).
    """

    # Error unico para cualquier token que no sirva.
    error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Sesión expirada. Inicia sesión nuevamente.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_token(datos.refresh_token)
    # Solo se aceptan tokens de tipo refresh.
    if payload is None or payload.get("type") != "refresh":
        raise error
    usuario = buscar_por_nombre(db, payload["sub"])
    # El estado real se lee de la base, no del token.
    if usuario is None or not usuario.activo:
        raise error
    # Rotacion: cada renovacion entrega tambien un refresh token nuevo.
    return emitir_tokens(usuario)


@router.get("/me", response_model=UsuarioOut)
def obtener_usuario_actual(
    usuario: Usuario = Depends(get_current_user),
) -> UsuarioOut:
    """Devuelve los datos publicos del usuario autenticado."""

    return convertir_usuario_a_salida(usuario)


@router.put("/me/password", status_code=status.HTTP_204_NO_CONTENT)
def cambiar_mi_password(
    datos: CambioPasswordRequest,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> Response:
    """Cambia la contrasena de la propia cuenta (cualquier rol).

    Exige la contrasena actual. Responde 204 sin cuerpo y deja el cambio
    auditado sin guardar ninguna contrasena ni hash en la auditoria.
    """

    try:
        cambiar_password_propia(db, usuario, datos.password_actual, datos.password_nueva)
    except (PasswordActualIncorrectaError, PasswordRepetidaError) as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
def crear_usuario_endpoint(
    datos: UsuarioCreate,
    db: Session = Depends(get_db),
    usuario_administrador: Usuario = Depends(
        require_rol(RolUsuario.ADMINISTRADOR)
    ),
) -> UsuarioOut:
    """Crea un usuario con uno o varios roles validos.

    Solo un administrador puede utilizar esta ruta. El servicio guarda el
    hash de la contrasena y audita el alta con el administrador responsable.
    """

    try:
        usuario = crear_usuario(db, datos, usuario_administrador)
    except UsuarioDuplicadoError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El nombre de usuario ya existe",
        ) from error
    return convertir_usuario_a_salida(usuario)


@router.put("/usuarios/{usuario_id}", response_model=UsuarioOut)
def actualizar_usuario_endpoint(
    usuario_id: str,
    datos: UsuarioUpdate,
    db: Session = Depends(get_db),
    usuario_administrador: Usuario = Depends(
        require_rol(RolUsuario.ADMINISTRADOR)
    ),
) -> UsuarioOut:
    """Actualiza nombre completo, roles, estado o contrasena de un usuario.

    Todos los campos son opcionales. Si se envia roles, la lista reemplaza
    todos los roles actuales del usuario. Solo se auditan cambios efectivos.
    """

    # Busca por clave primaria; si el id no existe responde 404.
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado",
        )

    # exclude_unset deja solo los campos que vinieron en el JSON, para
    # distinguir "no enviado" de "enviado con False" y poder desactivar.
    # exclude_none descarta los enviados como null: sin esto, "roles": null
    # dejaria al usuario sin roles y "activo": null intentaria guardar NULL.
    cambios = datos.model_dump(exclude_unset=True, exclude_none=True)

    # Un administrador no puede desactivarse a si mismo: podria quedar el
    # sistema sin nadie que administre usuarios.
    if (
        cambios.get("activo") is False
        and usuario.id == usuario_administrador.id
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes desactivar tu propio usuario administrador",
        )

    # Por el mismo motivo, tampoco puede quitarse el rol administrador al
    # reemplazar su propia lista de roles.
    if (
        usuario.id == usuario_administrador.id
        and "roles" in cambios
        and RolUsuario.ADMINISTRADOR not in cambios["roles"]
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes quitarte el rol administrador a ti mismo",
        )

    # Su propia contrasena se cambia en /auth/me/password, que exige la actual.
    if usuario.id == usuario_administrador.id and "password" in cambios:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Para cambiar tu propia contraseña usa la opción Cambiar contraseña",
        )

    # El servicio aplica solo lo que cambia, audita y confirma.
    usuario = actualizar_usuario(db, usuario, datos, usuario_administrador)
    return convertir_usuario_a_salida(usuario)
