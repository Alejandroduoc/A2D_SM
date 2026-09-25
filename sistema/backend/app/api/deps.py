# Importa Callable para describir el tipo de las funciones de dependencia que se devuelven.
from collections.abc import Callable
# Importa las herramientas de FastAPI para inyectar dependencias y lanzar errores HTTP.
from fastapi import Depends,HTTPException, status
# Importa el esquema OAuth2 que extrae el token Bearer de cada solicitud.
from fastapi.security import OAuth2PasswordBearer
# Importa el tipo de sesión utilizado para consultar la base de datos.
from sqlalchemy.orm import Session
# Importa la dependencia que proporciona una conexión a la base de datos.
from app.core.database import get_db
# Importa la función que valida y decodifica el token JWT.
from app.core.security import decode_token
# Importa el modelo de usuario y el enum con los roles disponibles.
from app.models.usuario import RolUsuario, Usuario 

# Configura OAuth2 indicando la ruta donde los clientes obtienen el token.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

# Jerarquía simple de roles para el PMV (de menor a mayor privilegio). Los tres
# operador_* están al mismo rango — son especialidades, no niveles entre sí; lo
# que los distingue es `require_roles` (membresía exacta), no `require_rol`.
# Define el nivel de privilegio asociado a cada rol.
_JERARQUIA_ROLES = {
    # Los operadores tienen el nivel base de privilegios.
    RolUsuario.OPERADOR_RECEPCION: 1,
    # El operador de proceso tiene el mismo nivel que los demás operadores.
    RolUsuario.OPERADOR_PROCESO: 1,
    # El operador de bodega tiene el mismo nivel que los demás operadores.
    RolUsuario.OPERADOR_BODEGA: 1,
    # El supervisor tiene un nivel intermedio de privilegios.
    RolUsuario.SUPERVISOR: 2,
    # El administrador tiene el nivel más alto de privilegios.
    RolUsuario.ADMINISTRADOR: 3,
}


# Define una dependencia que obtiene y valida al usuario autenticado.
def get_current_user(
    # Recibe el token Bearer enviado por el cliente.
    token: str = Depends(oauth2_scheme),
    # Recibe una sesión de base de datos administrada por FastAPI.
    db: Session = Depends(get_db),
    # Indica que la función devuelve una instancia del modelo Usuario.
) -> Usuario:
    # Prepara el error común para credenciales ausentes, inválidas o expiradas.
    credentials_exception = HTTPException(
        # Indica que la solicitud no está autenticada.
        status_code=status.HTTP_401_UNAUTHORIZED,
        # Define el mensaje que recibirá el cliente.
        detail="Credenciales inválidas o expiradas",
        # Solicita al cliente que use autenticación Bearer.
        headers={"WWW-Authenticate": "Bearer"},
    )
    # Valida el token y obtiene la información almacenada en su payload.
    payload = decode_token(token)
    # Rechaza tokens inválidos o tokens que no sean de tipo access.
    if payload is None or payload.get("type") != "access":
        # Detiene la ejecución y responde con el error de autenticación.
        raise credentials_exception

    # Extrae del token el nombre del usuario autenticado.
    nombre_usuario = payload.get("sub")
    # Rechaza el token si no contiene el identificador del usuario.
    if nombre_usuario is None:
        # Detiene la ejecución y responde con el error de autenticación.
        raise credentials_exception

    # Busca en la base de datos un usuario cuyo nombre coincida con el token.
    usuario = db.query(Usuario).filter(Usuario.nombre_usuario == nombre_usuario).first()
    # Rechaza usuarios inexistentes o que estén desactivados.
    if usuario is None or not usuario.activo:
        # Detiene la ejecución y responde con el error de autenticación.
        raise credentials_exception
    # Devuelve el usuario autenticado para que otras rutas puedan utilizarlo.
    return usuario


# Define una dependencia que exige un rol mínimo según la jerarquía configurada.
def require_rol(rol_minimo: RolUsuario) -> Callable[[Usuario], Usuario]:
    """
    Uso: @router.post(..., dependencies=[Depends(require_rol(RolUsuario.ADMINISTRADOR))])
    Cualquier intento de un rol insuficiente termina en 403 — no en un error
    silencioso ni en datos parcialmente visibles.
    """

    # Crea la función que FastAPI ejecutará como dependencia protegida.
    def dependency(usuario: Usuario = Depends(get_current_user)) -> Usuario:
        # Un usuario puede tener varios roles — se usa el de mayor rango para
        # comparar contra el mínimo exigido (alcanza con que UNO de sus roles cumpla).
        # Calcula el nivel más alto entre todos los roles del usuario.
        rango_usuario = max((_JERARQUIA_ROLES.get(r, 0) for r in usuario.roles), default=0)
        # Comprueba si el nivel del usuario es menor que el nivel requerido.
        if rango_usuario < _JERARQUIA_ROLES.get(rol_minimo, 0):
            # Rechaza la solicitud porque el usuario no tiene permisos suficientes.
            raise HTTPException(
                # Indica que el usuario está autenticado, pero no autorizado.
                status_code=status.HTTP_403_FORBIDDEN,
                # Define el mensaje que recibirá el cliente.
                detail="No tienes permisos suficientes para esta operación",
            )
        # Devuelve el usuario autorizado a la ruta que solicitó la dependencia.
        return usuario

    # Devuelve la dependencia configurada con el rol mínimo recibido.
    return dependency


# Define una dependencia que exige pertenecer a uno de varios roles concretos.
def require_roles(*roles_permitidos: RolUsuario) -> Callable[[Usuario], Usuario]:
    """
    Uso: dependencies=[Depends(require_roles(RolUsuario.OPERADOR_RECEPCION, RolUsuario.ADMINISTRADOR))]
    A diferencia de `require_rol` (jerárquico, "rol mínimo"), exige tener al menos
    uno de los roles de la lista dada. Hace falta para casos como "editar tarja":
    solo operador_recepcion y administrador pueden, aunque supervisor tenga más
    privilegio en la jerarquía — no es un caso de "rol mínimo".
    """

    # Crea la función que FastAPI ejecutará como dependencia protegida.
    def dependency(usuario: Usuario = Depends(get_current_user)) -> Usuario:
        # Comprueba si al menos uno de los roles del usuario está permitido.
        if not any(rol in roles_permitidos for rol in usuario.roles):
            # Rechaza la solicitud porque ninguno de los roles coincide.
            raise HTTPException(
                # Indica que el usuario está autenticado, pero no autorizado.
                status_code=status.HTTP_403_FORBIDDEN,
                # Define el mensaje que recibirá el cliente.
                detail="No tienes permisos suficientes para esta operación",
            )
        # Devuelve el usuario autorizado a la ruta que solicitó la dependencia.
        return usuario

    # Devuelve la dependencia configurada con los roles permitidos.
    return dependency