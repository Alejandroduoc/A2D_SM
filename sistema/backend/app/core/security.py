# Importa tipos para trabajar con fechas y duraciones de tiempo.
from datetime import datetime, timedelta, timezone

# Importa Any para indicar que el payload puede contener distintos tipos de datos.
from typing import Any

# Importa el error de JWT y las funciones para codificar y decodificar tokens.
from jose import JWTError, jwt

# Importa la herramienta que administra el hashing y la verificación de contraseñas.
from passlib.context import CryptContext

# Importa la configuración general, incluida la clave secreta y los tiempos de expiración.
from app.core.config import settings

# Configura bcrypt como algoritmo para proteger las contraseñas.
# deprecated="auto" permite identificar esquemas antiguos que deban actualizarse.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# Convierte una contraseña en texto plano en un hash irreversible.
def hash_password(password: str) -> str:
    # Genera y devuelve el hash de la contraseña usando bcrypt.
    return pwd_context.hash(password)


# Comprueba si una contraseña coincide con un hash almacenado.
def verify_password(plain_password: str, hashed_password: str) -> bool:
    # Devuelve True si la contraseña es válida y False si no coincide.
    return pwd_context.verify(plain_password, hashed_password)


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
    # Construye el contenido del token con el usuario, sus roles y la fecha de expiración.
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
        # Verifica la firma, la expiración y el algoritmo del token.
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        # Devuelve None si el token es inválido, está vencido o no puede decodificarse.
        return None
