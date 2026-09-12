from pydantic import BaseModel, ConfigDict, Field

from app.models.usuario import RolUsuario


class UsuarioCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    full_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=8, max_length=128)
    role: RolUsuario = RolUsuario.OPERATOR


class UsuarioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    full_name: str
    roles: list[RolUsuario]
    is_active: bool


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UsuarioRead