# Importa tipos para trabajar con fechas y duraciones de tiempo.
from datetime import datetime, timedelta, timezone

# Importa Any para indicar que el payload puede contener distintos tipos de datos.
from typing import Any

# Biblioteca de hashing de contraseñas; se usa directo (passlib ya no se mantiene).
import bcrypt

# PyJWT firma y verifica los tokens (reemplaza a python-jose).
import jwt

# Importa la configuración general, incluida la clave secreta y los tiempos de expiración.
from app.core.config import settings

# Costo de bcrypt: 12 rondas es el mismo valor que usaba passlib, así los hashes
# existentes siguen siendo válidos y el tiempo de verificación no cambia.
_RONDAS_BCRYPT = 12


# Convierte una contraseña en texto plano en un hash irreversible.
def hash_password(password: str) -> str:
    # bcrypt trabaja con bytes: la contraseña se codifica en UTF-8.
    password_bytes = password.encode("utf-8")
    # gensalt crea una sal aleatoria nueva para cada hash.
    sal = bcrypt.gensalt(rounds=_RONDAS_BCRYPT)
    # Devuelve el hash como texto ($2b$12$...) para guardarlo en la columna password_hash.
    return bcrypt.hashpw(password_bytes, sal).decode("ascii")


# Comprueba si una contraseña coincide con un hash almacenado.
def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        # checkpw recalcula el hash con la sal guardada y compara en tiempo constante.
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("ascii"))
    except ValueError:
        # Un hash con formato inválido nunca autentica, en vez de provocar un error 500.
        return False


# Hash de una contraseña aleatoria que no pertenece a nadie. El login lo compara cuando
# el usuario no existe, para que esa respuesta tarde lo mismo que una contraseña incorrecta.
HASH_FICTICIO = hash_password("usuario-inexistente-" + datetime.now(timezone.utc).isoformat())


# Crea un token JWT de acceso para un usuario.
# subject identifica al usuario y roles contiene sus roles informativos.
# expires_delta permite establecer una duración personalizada para el token.
def create_access_token(subject: str, roles: list[str], expires_delta: timedelta | None = None) -> str:
    # Obtiene la fecha y hora actual en UTC y suma el tiempo de expiración.
    expire = datetime.now(timezone.utc) + (
        # Usa la duración recibida o la duración predeterminada de la configuración.
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    # `roles` va en el payload solo informativamente (ej. para un cliente que
    # quiera leerlo sin pegarle a /auth/me) — la autorización real siempre
    # revalida contra la base de datos en get_current_user, nunca confía en el
    # contenido del token para decidir permisos.
    # type permite distinguir este token de un token de actualización.
    to_encode: dict[str, Any] = {"sub": subject, "roles": roles, "exp": expire, "type": "access"}
    # Firma y devuelve el token usando la clave secreta y el algoritmo configurados.
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


# Crea un token JWT de actualización para obtener nuevos tokens de acceso.
def create_refresh_token(subject: str) -> str:
    # Calcula la fecha de expiración usando el tiempo configurado para refresh tokens.
    expire = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    # Define el usuario, la expiración y el tipo de token.
    to_encode = {"sub": subject, "exp": expire, "type": "refresh"}
    # Firma y devuelve el token de actualización.
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


# Intenta validar y decodificar un token JWT.
def decode_token(token: str) -> dict[str, Any] | None:
    try:
        # Verifica la firma, la expiración y el algoritmo; exige que existan sub, exp y type.
        return jwt.decode(
            token,  # Token recibido del cliente.
            settings.secret_key,  # Misma clave con la que se firmó.
            algorithms=[settings.algorithm],  # Lista fija: no acepta el algoritmo que diga el token.
            options={"require": ["sub", "exp", "type"]},  # Rechaza tokens incompletos.
        )  # Devuelve el payload validado.
    except jwt.PyJWTError:
        # Devuelve None si el token es inválido, está vencido o no puede decodificarse.
        return None
