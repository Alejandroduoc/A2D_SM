from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_token, is_access_token
from app.models.usuario import RolUsuario, Usuario


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(token: Annotated[str, Depends(oauth2_scheme)], db: DbSession) -> Usuario:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token inválido o expirado",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_token(token)
    if not is_access_token(payload):
        raise credentials_error

    username = payload["sub"]
    user = db.scalar(select(Usuario).where(Usuario.nombre_usuario == username))
    if user is None or not user.activo:
        raise credentials_error
    return user


CurrentUser = Annotated[Usuario, Depends(get_current_user)]


def get_current_admin(user: CurrentUser) -> Usuario:
    if RolUsuario.ADMIN not in user.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requiere el rol administrador",
        )
    return user