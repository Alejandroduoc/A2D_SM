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

# Librería estándar para crear el enum de roles (RolUsuario).
import enum

# Genera identificadores únicos (UUID) para usarlos como id de cada usuario,
# en vez de un contador de base de datos que revela cuántos usuarios existen.
import uuid

# datetime: para registrar cuándo se creó un usuario.
# timezone: para guardar esa fecha en UTC y no en la hora local del servidor.
from datetime import datetime, timezone

# Tipos de columna de SQLAlchemy: Boolean (activo/inactivo), DateTime (fecha),
# Enum (guarda un valor de un enum de Python como texto restringido),
# ForeignKey (clave foránea, para enlazar usuario_roles con usuarios),
# String (texto de largo variable, con un máximo).
from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String

# Mapped / mapped_column: forma moderna (SQLAlchemy 2.0) de declarar una
# columna con su tipo de Python y de base de datos a la vez.
# relationship: declara un vínculo entre dos modelos (acá, Usuario ↔ UsuarioRol)
# para poder navegarlo en Python sin escribir el JOIN a mano.
from sqlalchemy.orm import Mapped, mapped_column, relationship

# Clase base de la que heredan todos los modelos (definida en database.py).
# SQLAlchemy usa sus subclases para saber qué tablas debe crear.
from app.core.database import Base


# str + enum.Enum: cada rol se comporta como texto (se guarda como texto en la
# base y se serializa como texto en JSON), pero solo puede valer uno de los
# 5 nombres definidos acá abajo — cualquier otro valor lo rechaza Python solo.
class RolUsuario(str, enum.Enum):
    OPERADOR_RECEPCION = "operador_recepcion"
    OPERADOR_PROCESO = "operador_proceso"
    OPERADOR_BODEGA = "operador_bodega"
    SUPERVISOR = "supervisor"
    ADMINISTRADOR = "administrador"


# Hereda de Base: esto le dice a SQLAlchemy "esta clase es una tabla real".
class Usuario(Base):
    # Nombre de la tabla en SQL Server.
    __tablename__ = "usuarios"

    # Clave primaria como texto (UUID), no un entero autoincremental. default=
    # recibe una función (lambda), no un valor fijo: se ejecuta una vez POR
    # usuario nuevo, así que cada uno recibe un id distinto.
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    # Nombre con el que se inicia sesión. unique=True: SQL Server rechaza un
    # segundo usuario con el mismo nombre. index=True: esa columna queda
    # indexada, porque el login la busca en cada petición.
    nombre_usuario: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    # Nombre para mostrar en pantalla (no se usa para iniciar sesión).
    nombre_completo: Mapped[str] = mapped_column(String(150), nullable=False)
    # Solo el HASH de la contraseña (lo genera hash_password, en core/security.py).
    # Nunca se guarda ni se lee la contraseña en texto plano.
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # Permite deshabilitar el login de alguien sin borrar su historial ni sus
    # registros relacionados. default=True: un usuario nuevo nace habilitado.
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Fecha de creación, calculada sola al insertar la fila (igual que id: es
    # una función, se evalúa una vez por usuario, con la hora de ese momento).
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Un Usuario tiene VARIAS filas de UsuarioRol asociadas (uno por cada rol
    # que se le asignó). cascade="all, delete-orphan": si se borra el usuario,
    # SQLAlchemy borra solas sus filas de usuario_roles (no quedan huérfanas).
    roles_asignados: Mapped[list["UsuarioRol"]] = relationship(cascade="all, delete-orphan")

    # No es una columna de la base: es una propiedad calculada en Python.
    # Traduce roles_asignados (lista de objetos UsuarioRol) a una lista simple
    # de valores RolUsuario, para no tener que escribir "ur.rol for ur in ..."
    # cada vez que el resto del código (deps.py, routers, etc.) necesita
    # comparar o mostrar los roles de un usuario.
    @property
    def roles(self) -> list[RolUsuario]:
        return [ur.rol for ur in self.roles_asignados]


# Tabla de asociación N:M entre Usuario y RolUsuario: una fila = "este usuario
# tiene este rol". Un usuario con 2 roles ocupa 2 filas acá, no 1.
class UsuarioRol(Base):
    """Asociación N:M — un usuario puede tener varios roles a la vez."""

    __tablename__ = "usuario_roles"

    # Apunta al id de usuarios. Es parte de la clave primaria (ver abajo).
    usuario_id: Mapped[str] = mapped_column(String(36), ForeignKey("usuarios.id"), primary_key=True)
    # Enum(RolUsuario): SQLAlchemy guarda el NOMBRE del rol como texto
    # (ej. "ADMINISTRADOR"), y solo permite los 5 valores del enum.
    rol: Mapped[RolUsuario] = mapped_column(Enum(RolUsuario), primary_key=True)
    # usuario_id + rol como clave primaria COMPUESTA (las dos columnas tienen
    # primary_key=True): impide repetir el mismo rol dos veces para el mismo
    # usuario, sin necesitar una columna "id" extra en esta tabla.
