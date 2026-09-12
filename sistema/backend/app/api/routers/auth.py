from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select

from app.api.dependencies import CurrentUser, DbSession
from app.core.security import create_access_token, create_refresh_token, verify_password
from app.models.usuario import Usuario
from app.schemas.usuario import TokenResponse, UsuarioRead


router = APIRouter(prefix="/auth", tags=["Autenticación"])


@router.post("/login", response_model=TokenResponse)
def login(db: DbSession, form_data: OAuth2PasswordRequestForm = Depends()):
    user = db.scalar(select(Usuario).where(Usuario.nombre_usuario == form_data.username))
    if user is None or not user.activo or not verify_password(
        form_data.password, user.password_hash
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return TokenResponse(
        access_token=create_access_token(
            user.nombre_usuario, [role.value for role in user.roles]
        ),
        refresh_token=create_refresh_token(user.nombre_usuario),
        user=user,
    )


@router.get("/me", response_model=UsuarioRead)
def read_current_user(current_user: CurrentUser) -> Usuario:
    return current_user