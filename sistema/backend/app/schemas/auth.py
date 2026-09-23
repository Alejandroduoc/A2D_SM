"""
E1 — Contratos de entrada y salida de la API de autenticación.

Un "schema" de Pydantic no es un modelo de base de datos (eso está en
app/models/usuario.py): es la forma que debe tener el JSON que entra o sale de
un endpoint. FastAPI usa estas clases para validar lo que llega, rechazar lo
que no cumple (con un 422 automático) y describir /docs.
"""

# BaseModel: clase base de la que heredan todos los schemas.
# Field: permite agregar reglas extra a un campo (largo mínimo/máximo, etc.),
# además de su tipo y su valor por defecto.
from pydantic import BaseModel, Field

# RolUsuario es el mismo enum que usa la tabla usuario_roles. Se reutiliza acá
# para que un rol inválido (que no sea uno de los 5 definidos) se rechace solo,
# sin tener que validarlo a mano en el router.
from app.models.usuario import RolUsuario


class LoginRequest(BaseModel):
    """Lo que el cliente envía a POST /auth/login."""

    # Con qué usuario se intenta entrar (no es el id interno, es el nombre de login).
    nombre_usuario: str
    # Contraseña en texto plano, tal como la escribe la persona. Nunca se guarda
    # así: el router la compara contra el hash con verify_password().
    password: str


class TokenResponse(BaseModel):
    """Lo que devuelve un login exitoso."""

    # Token de corta duración: se manda en cada request como
    # "Authorization: Bearer <access_token>".
    access_token: str
    # Token de mayor duración, para pedir un access_token nuevo sin volver a
    # escribir la contraseña (el endpoint de refresh no es parte de E1 todavía).
    refresh_token: str
    # Le dice al cliente qué tipo de token es. "bearer" es el estándar OAuth2 y
    # no cambia nunca, por eso tiene un valor por defecto.
    token_type: str = "bearer"


class UsuarioCreate(BaseModel):
    """Lo que un administrador envía a POST /auth/usuarios para crear a alguien."""

    # min_length=3: evita nombres de usuario casi vacíos ("a", "ab").
    # max_length=50: coincide con el largo de la columna nombre_usuario en la BD
    # (ver models/usuario.py) — así el error de "muy largo" lo da la API con un
    # 422 claro, en vez de que lo rechace SQL Server con un error de columna.
    nombre_usuario: str = Field(min_length=3, max_length=50)
    # Mismo criterio, con el largo de la columna nombre_completo.
    nombre_completo: str = Field(min_length=3, max_length=150)
    # La contraseña SÍ viaja en texto plano en este request (por HTTPS, en
    # producción): recién en el router se convierte a hash con hash_password()
    # antes de guardarla. Nunca se guarda ni se loguea tal cual.
    password: str = Field(min_length=8, max_length=100)
    # Lista de roles porque un usuario puede tener más de uno (ver UsuarioRol,
    # tabla N:M). min_length=1 sin valor por defecto: quien crea el usuario
    # SIEMPRE tiene que elegir al menos un rol a propósito, nunca queda un
    # usuario sin ningún rol asignado por olvido.
    roles: list[RolUsuario] = Field(min_length=1)


class UsuarioUpdate(BaseModel):
    """
    Lo que un administrador envía a PUT /auth/usuarios/{id} para editar a
    alguien. Todos los campos son opcionales a propósito: se edita solo lo que
    se envía, el resto del usuario queda tal cual estaba.
    """

    # None = "no tocar este campo". Si se envía un valor, debe cumplir el mismo
    # largo que en la creación.
    nombre_completo: str | None = Field(default=None, min_length=3, max_length=150)
    # None = no tocar los roles actuales. Una lista = reemplaza TODOS los roles
    # del usuario por esa lista (no se suma a los que ya tenía). Si se envía,
    # no puede ser una lista vacía (min_length=1): un usuario no puede quedar
    # sin ningún rol por una edición.
    roles: list[RolUsuario] | None = Field(default=None, min_length=1)
    # None = no tocar el estado. True/False = activar o desactivar el login del
    # usuario sin borrarlo (columna Usuario.activo).
    activo: bool | None = None


class UsuarioOut(BaseModel):
    """
    Lo que la API devuelve al consultar un usuario (login, /me, listar,
    crear, editar). A propósito NO incluye password ni password_hash: lo que
    no está declarado acá nunca puede salir en una respuesta, aunque el
    objeto Usuario internamente sí tenga esos datos.
    """

    id: str
    nombre_usuario: str
    nombre_completo: str
    # Lista de valores de RolUsuario. En el modelo (Usuario.roles) es una
    # @property calculada desde roles_asignados, no una columna; para
    # Pydantic se ve exactamente igual que cualquier otro atributo.
    roles: list[RolUsuario]
    activo: bool

    # from_attributes=True le permite a Pydantic construir este schema leyendo
    # ATRIBUTOS de un objeto (usuario.id, usuario.roles, ...) en vez de exigir
    # un diccionario. Sin esto, UsuarioOut.model_validate(usuario_de_sqlalchemy)
    # fallaría: por defecto Pydantic solo acepta dict-like.
    model_config = {"from_attributes": True}
