import uuid
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import Boolean, DateTime, Enum as SqlEnum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class RolUsuario(str, Enum):
	ADMIN = "admin"
	OPERATOR = "operator"


class Usuario(Base):
	__tablename__ = "usuarios"

	id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
	nombre_usuario: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
	nombre_completo: Mapped[str] = mapped_column(String(150), nullable=False)
	password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
	activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
	creado_en: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
	)

	roles_asignados: Mapped[list["UsuarioRol"]] = relationship(
		back_populates="usuario", cascade="all, delete-orphan"
	)

	@property
	def roles(self) -> list[RolUsuario]:
		return [usuario_rol.rol for usuario_rol in self.roles_asignados]

	@property
	def username(self) -> str:
		return self.nombre_usuario

	@property
	def full_name(self) -> str:
		return self.nombre_completo

	@property
	def is_active(self) -> bool:
		return self.activo


class UsuarioRol(Base):
	"""Asociación N:M: un usuario puede tener varios roles a la vez."""

	__tablename__ = "usuario_roles"

	usuario_id: Mapped[str] = mapped_column(
		String(36), ForeignKey("usuarios.id", ondelete="CASCADE"), primary_key=True
	)
	rol: Mapped[RolUsuario] = mapped_column(
		SqlEnum(RolUsuario, name="rol_usuario"), primary_key=True
	)

	usuario: Mapped[Usuario] = relationship(back_populates="roles_asignados")
