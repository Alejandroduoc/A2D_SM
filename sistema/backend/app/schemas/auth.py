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
# field_validator: permite revisar o transformar un campo después de validarlo.
from pydantic import BaseModel, Field, field_validator

# RolUsuario es el mismo enum que usa la tabla usuario_roles. Se reutiliza acá
# para que un rol inválido (que no sea uno de los 4 definidos) se rechace solo,
# sin tener que validarlo a mano en el router.
from app.models.usuario import RolUsuario

# Regla compartida de largo para toda contraseña nueva (8 caracteres a 72 bytes).
from app.core.validators import validar_password_nueva


class LoginRequest(BaseModel):
    """Lo que el cliente envía a POST /auth/login."""

    # Con qué usuario se intenta entrar (no es el id interno, es el nombre de login).
    # max_length=50 coincide con la columna: un nombre más largo no puede existir.
    nombre_usuario: str = Field(min_length=1, max_length=50)
    # Contraseña en texto plano, tal como la escribe la persona. Nunca se guarda
    # así: el router la compara contra el hash con verify_password().
    # max_length=128 evita recibir textos enormes; no se usa 72 bytes aquí para no
    # dejar fuera a una cuenta antigua creada con una contraseña más larga.
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    """Lo que el cliente envía a POST /auth/refresh para renovar la sesión."""

    # Rechaza campos que no sean el token, igual que los catálogos.
    model_config = {"extra": "forbid"}

    # Token de actualización entregado por el login o por el refresh anterior.
    refresh_token: str = Field(min_length=1, max_length=2048)


class CambioPasswordRequest(BaseModel):
    """Lo que envía cada persona a PUT /auth/me/password para cambiar su contraseña."""

    # Rechaza campos inesperados.
    model_config = {"extra": "forbid"}

    # Contraseña vigente: confirma que quien cambia la clave es el dueño de la sesión.
    password_actual: str = Field(min_length=1, max_length=128)
    # Contraseña nueva; se valida con la misma regla que al crear usuarios.
    password_nueva: str

    # Aplica el largo mínimo y el máximo de bcrypt a la contraseña nueva.
    @field_validator("password_nueva")
    @classmethod
    def validar_password(cls, valor: str) -> str:
        return validar_password_nueva(valor)


class TokenResponse(BaseModel):
    """Lo que devuelve un login exitoso o una renovación en POST /auth/refresh."""

    # Token de corta duración: se manda en cada request como
    # "Authorization: Bearer <access_token>".
    access_token: str
    # Token de mayor duración, para pedir un access_token nuevo en
    # POST /auth/refresh sin volver a escribir la contraseña.
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
    # El largo (8 caracteres a 72 bytes) lo revisa validar_password más abajo.
    password: str
    # Lista de roles porque un usuario puede tener más de uno (ver UsuarioRol,
    # tabla N:M). min_length=1 sin valor por defecto: quien crea el usuario
    # SIEMPRE tiene que elegir al menos un rol a propósito, nunca queda un
    # usuario sin ningún rol asignado por olvido.
    roles: list[RolUsuario] = Field(min_length=1)

    # Rechaza campos que no estén declarados (por ejemplo "activo" o "id" en el alta).
    model_config = {"extra": "forbid"}

    # bcrypt ignora lo que pase de 72 bytes: se rechaza en vez de truncarlo en silencio.
    @field_validator("password")
    @classmethod
    def validar_password(cls, valor: str) -> str:
        return validar_password_nueva(valor)

    # Se ejecuta después de validar que cada rol existe en RolUsuario.
    @field_validator("roles")
    @classmethod
    def quitar_roles_repetidos(cls, roles: list[RolUsuario]) -> list[RolUsuario]:
        # usuario_roles tiene clave primaria (usuario_id, rol): un rol repetido
        # haría fallar el INSERT en SQL Server. dict.fromkeys elimina los
        # repetidos y conserva el orden en que se enviaron.
        return list(dict.fromkeys(roles))


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
    # None = no tocar la contraseña. Un valor = el administrador la restablece
    # (por ejemplo, si la persona la olvidó). Se guarda solo su hash.
    password: str | None = None

    # Rechaza campos que no estén declarados.
    model_config = {"extra": "forbid"}

    # Misma regla de largo que en el alta, solo si se envía una contraseña.
    @field_validator("password")
    @classmethod
    def validar_password(cls, valor: str | None) -> str | None:
        if valor is None:
            return None
        return validar_password_nueva(valor)

    # Misma regla que en UsuarioCreate: quita roles repetidos.
    @field_validator("roles")
    @classmethod
    def quitar_roles_repetidos(
        cls, roles: list[RolUsuario] | None
    ) -> list[RolUsuario] | None:
        # Si se envió "roles": null, se devuelve None sin cambios: el router lo
        # descarta con exclude_none y los roles actuales no se tocan.
        if roles is None:
            return None
        return list(dict.fromkeys(roles))


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
