from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select

from app.api.dependencies import CurrentUser, DbSession, get_current_admin
from app.core.security import hash_password
from app.models.usuario import RolUsuario, Usuario, UsuarioRol
from app.schemas.usuario import UsuarioCreate, UsuarioRead


router = APIRouter(prefix="/users", tags=["Usuarios"])


def build_user(data: UsuarioCreate) -> Usuario:
    return Usuario(
        nombre_usuario=data.username,
        nombre_completo=data.full_name,
        password_hash=hash_password(data.password),
        roles_asignados=[UsuarioRol(rol=data.role)],
    )


def ensure_unique_user(db: DbSession, data: UsuarioCreate) -> None:
    existing = db.scalar(
        select(Usuario).where(
            Usuario.nombre_usuario == data.username
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El usuario o correo ya existe",
        )


@router.post("/bootstrap", response_model=UsuarioRead, status_code=status.HTTP_201_CREATED)
def bootstrap_admin(data: UsuarioCreate, db: DbSession) -> Usuario:
    if db.scalar(select(func.count(Usuario.id))) != 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El administrador inicial ya fue creado",
        )
    data.role = RolUsuario.ADMIN
    user = build_user(data)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("", response_model=UsuarioRead, status_code=status.HTTP_201_CREATED)
def create_user(
    data: UsuarioCreate,
    db: DbSession,
    _: Usuario = Depends(get_current_admin),
) -> Usuario:
    ensure_unique_user(db, data)
    user = build_user(data)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("", response_model=list[UsuarioRead])
def list_users(
    db: DbSession,
    _: Usuario = Depends(get_current_admin),
) -> list[Usuario]:
    return list(db.scalars(select(Usuario).order_by(Usuario.id)))