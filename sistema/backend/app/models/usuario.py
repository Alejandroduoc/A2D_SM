"""
E1 — Autenticación y control de acceso.

Roles: operador_recepcion, operador_proceso, operador_bodega, supervisor y
administrador. Los tres operadores son especialidades del mismo rango (no
niveles entre sí); supervisor y administrador están por encima de ellos.

Un usuario puede tener más de un rol a la vez, por eso `rol` no es una columna
de `Usuario`: es una tabla de asociación (`UsuarioRol`, N:M). `Usuario.roles`
expone la lista de valores de `RolUsuario` para no navegar `roles_asignados`
cada vez que solo hace falta comparar roles.
"""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class RolUsuario(str, enum.Enum):
    OPERADOR_RECEPCION = "operador_recepcion"
    OPERADOR_PROCESO = "operador_proceso"
    OPERADOR_BODEGA = "operador_bodega"
    SUPERVISOR = "supervisor"
    ADMINISTRADOR = "administrador"

class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    nombre_usuario: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    nombre_completo: Mapped[str] = mapped_column(String(150), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    roles_asignados: Mapped[list["UsuarioRol"]] = relationship(cascade="all, delete-orphan")

    @property
    def roles(self) -> list[RolUsuario]:
        return [ur.rol for ur in self.roles_asignados]


class UsuarioRol(Base):
    """Asociación N:M — un usuario puede tener varios roles a la vez."""
    __tablename__ = "usuario_roles"

    usuario_id: Mapped[str] = mapped_column(String(36), ForeignKey("usuarios.id"), primary_key=True)
    rol: Mapped[RolUsuario] = mapped_column(Enum(RolUsuario), primary_key=True)
