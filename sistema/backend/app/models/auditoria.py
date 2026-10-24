# Permite definir el conjunto de acciones de auditoría admitidas.
import enum

# datetime representa la fecha; timezone permite calcularla en UTC.
from datetime import datetime, timezone

# Tipos y restricciones de las columnas de la tabla de auditoría.
from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, String, UnicodeText

# Herramientas de SQLAlchemy 2 para declarar atributos y columnas tipados.
from sqlalchemy.orm import Mapped, mapped_column

# Incorpora el modelo al mismo conjunto de tablas que Usuario.
from app.core.database import Base


# Limita las acciones de auditoría a los tres valores acordados.
class AccionAuditoria(str, enum.Enum):
    # Identifica la creación de un registro.
    INSERT = "INSERT"
    # Incluye ediciones, activaciones, desactivaciones y anulaciones de estado.
    UPDATE = "UPDATE"
    # Se reserva para eliminaciones autorizadas; no habilita borrados físicos.
    DELETE = "DELETE"


# Define la tabla que conserva el historial de las operaciones de negocio.
class Auditoria(Base):
    # Nombre de la tabla en SQL Server.
    __tablename__ = "auditoria"

    # Identifica esta fila de auditoría, no el registro de negocio modificado.
    id: Mapped[int] = mapped_column(
        BigInteger,  # Permite un contador de gran capacidad para el historial.
        primary_key=True,  # Identifica cada evento de forma única.
        autoincrement=True,  # La base genera el identificador al insertar.
    )  

    # Identifica al usuario responsable de la operación.
    usuario_id: Mapped[str] = mapped_column(
        String(36),  # Coincide con el tipo y largo de usuarios.id.
        ForeignKey("usuarios.id"),  # Exige un usuario existente, sin borrado en cascada.
        index=True,  # Facilita consultar el historial por usuario.
        nullable=False,  # Toda auditoría debe identificar al responsable.
    ) 

    # Guarda el nombre de la tabla a la que pertenece el registro afectado.
    tabla: Mapped[str] = mapped_column(
        String(50),  # Limita el nombre de la tabla a 50 caracteres.
        index=True,  # Facilita consultar el historial de una tabla.
        nullable=False,  # Todo evento debe indicar qué tabla afectó.
    )  

    # Guarda como texto tanto identificadores enteros como UUID de negocio.
    registro_id: Mapped[str] = mapped_column(
        String(36),  # Admite el UUID de un usuario o el id convertido a texto.
        nullable=False,  # Todo evento debe identificar el registro afectado.
    ) 

    # Indica qué operación se realizó sobre el registro.
    accion: Mapped[AccionAuditoria] = mapped_column(
        Enum(AccionAuditoria, length=10),  # Usa los nombres del enum como valores.
        nullable=False,  # Todo evento debe indicar una acción.
    ) 

    # Conserva los valores anteriores como JSON serializado por el servicio.
    valores_antes: Mapped[str | None] = mapped_column(
        UnicodeText,  # Guarda texto Unicode extenso para el contenido JSON.
        nullable=True,  # En una creación no existen valores anteriores.
    )
    # Conserva los valores posteriores como JSON serializado por el servicio.
    valores_despues: Mapped[str | None] = mapped_column(
        UnicodeText,  # Guarda texto Unicode extenso para el contenido JSON.
        nullable=True,  # Permite operaciones sin un estado posterior.
    ) 
    # Guarda la justificación cuando la operación de negocio la requiere.
    motivo: Mapped[str | None] = mapped_column(
        String(255),  # Limita la explicación a 255 caracteres.
        nullable=True,  # La exigencia del motivo se aplica desde el negocio.
    )  
    # Registra el instante del evento con la misma convención UTC de Usuario.
    fecha_hora: Mapped[datetime] = mapped_column(
        DateTime,  # Representa la fecha y hora en la base de datos.
        default=lambda: datetime.now(timezone.utc),  # Calcula la fecha al insertar cada fila.
        index=True,  # Facilita consultar el historial por fecha.
        nullable=False,  # Todo evento debe tener una fecha y hora.
    )  