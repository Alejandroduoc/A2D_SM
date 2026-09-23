# Define los esquemas de entrada y salida relacionados con usuarios.
# Se separan los datos recibidos por la API de la información almacenada en BD.

from datetime import datetime
from pydantic import BaseModel, ConfigDict

from app.models.usuario import RolUsuario


# Representa los datos comunes de un usuario.
class UsuarioBase(BaseModel):
    nombre_usuario: str
    nombre_completo: str
    activo: bool = True


# Representa la información necesaria
# para registrar un nuevo usuario.
class UsuarioCreate(UsuarioBase):
    password: str
    roles: list[RolUsuario]


# Representa la información pública de un usuario
# que puede devolver la API. Permite construir el esquema
# directamente desde un modelo de SQLAlchemy.
class UsuarioResponse(UsuarioBase):
    id: str
    roles: list[RolUsuario]
    creado_en: datetime

    model_config = ConfigDict(from_attributes=True)