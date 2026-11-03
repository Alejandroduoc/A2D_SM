"""Procesos de tarjas con consumo parcial y folio correlativo de E4."""

# Registra el día de elaboración y el instante UTC de cada proceso.
from datetime import date, datetime, timezone
# Conserva los pesos exactos con dos decimales.
from decimal import Decimal

# Declara tipos, claves, restricciones y la secuencia de SQL Server.
from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, Numeric, Sequence, String, UniqueConstraint
# Declara columnas tipadas según el estilo SQLAlchemy 2 del proyecto.
from sqlalchemy.orm import Mapped, mapped_column

# Comparte el registro de metadatos de todas las tablas del sistema.
from app.core.database import Base

# Declara la secuencia que entrega el número del folio P de forma concurrente.
SEQ_NUMERO_PROCESO = Sequence(
    "seq_numero_proceso",  # Nombre que usará el service al consultar NEXT VALUE FOR.
    start=1,  # El primer folio generado será P1.
    increment=1,  # Cada proceso consume exactamente un número consecutivo.
    data_type=Integer,  # La secuencia usa el tipo técnico INT de SQL Server.
    metadata=Base.metadata,  # También queda disponible en bases temporales de pruebas.
)  # Finaliza la declaración de la secuencia.


# Representa la cabecera de un registro de procesamiento de tarjas.
class Proceso(Base):
    # Indica el nombre físico de la tabla de cabeceras de proceso.
    __tablename__ = "procesos"
    # Agrupa las restricciones que también valida directamente SQL Server.
    __table_args__ = (
        # Todo proceso contiene al menos una caja en el total calculado.
        CheckConstraint(
            "cantidad_cajas > 0",
            name="ck_procesos_cantidad_cajas_positiva",
        ),
        # La salida total calculada siempre debe ser un peso positivo.
        CheckConstraint(
            "kilos_salida > 0",
            name="ck_procesos_kilos_salida_positivos",
        ),
        # Nombra la unicidad del folio para conservarla también en la migración.
        UniqueConstraint("folio", name="uq_procesos_folio"),
    )  # Finaliza las reglas estructurales de la cabecera.

    # Guarda la identidad interna asignada por SQL Server.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Conserva el folio operativo P más el número obtenido desde la secuencia.
    folio: Mapped[str] = mapped_column(String(11), nullable=False)
    # Relaciona el proceso con el usuario autenticado que lo registró.
    usuario_id: Mapped[str] = mapped_column(
        String(36),  # Coincide con el UUID usado en usuarios.id.
        ForeignKey("usuarios.id"),  # Evita procesos sin usuario existente.
        index=True,  # Prepara los filtros futuros por usuario de auditoría.
        nullable=False,  # El usuario siempre es obligatorio.
    )  # Finaliza la relación con el usuario.
    # Guarda el embalaje único con el cual se calcula la salida del proceso.
    embalaje_id: Mapped[int] = mapped_column(
        Integer,  # Coincide con embalajes.id.
        ForeignKey("embalajes.id"),  # Exige un embalaje existente.
        index=True,  # Prepara filtros por embalaje.
        nullable=False,  # El embalaje es obligatorio.
    )  # Finaliza la relación con el embalaje.
    # Conserva el día declarado de elaboración de la fruta procesada.
    fecha_elaboracion: Mapped[date] = mapped_column(Date, nullable=False)
    # Guarda el momento UTC en que se registró el proceso en el sistema.
    fecha_hora: Mapped[datetime] = mapped_column(
        DateTime,  # Conserva fecha y hora sin perder precisión.
        default=lambda: datetime.now(timezone.utc),  # Asigna UTC al crear la cabecera.
        nullable=False,  # El momento de registro siempre existe.
    )  # Finaliza la fecha de registro.
    # Conserva la suma calculada de cajas de todas las filas del detalle.
    cantidad_cajas: Mapped[int] = mapped_column(Integer, nullable=False)
    # Conserva la suma calculada de kilos procesados de todas las filas.
    kilos_salida: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    # Permite anular lógicamente sin borrar la trazabilidad del proceso.
    anulado: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


# Representa una tarja incluida dentro de un proceso determinado.
class ProcesoTarja(Base):
    # Indica el nombre físico de la tabla de detalle de procesos.
    __tablename__ = "proceso_tarjas"
    # Agrupa restricciones que se aplican a cada fila del detalle.
    __table_args__ = (
        # Toda fila registra al menos una caja procesada.
        CheckConstraint(
            "cantidad_cajas > 0",
            name="ck_proceso_tarjas_cantidad_cajas_positiva",
        ),
        # Los kilos de una fila siempre son positivos, incluso cuando es granel.
        CheckConstraint(
            "kilos_procesados > 0",
            name="ck_proceso_tarjas_kilos_procesados_positivos",
        ),
    )  # Finaliza las restricciones del detalle.

    # Forma parte de la clave compuesta y relaciona la fila con su cabecera.
    proceso_id: Mapped[int] = mapped_column(
        Integer,  # Coincide con procesos.id.
        ForeignKey("procesos.id"),  # No puede existir un detalle sin proceso.
        primary_key=True,  # Evita repetir la misma combinación proceso-tarja.
        nullable=False,  # La relación siempre es obligatoria.
    )  # Finaliza la relación con el proceso.
    # Forma parte de la clave compuesta y relaciona la fila con una tarja recibida.
    tarja_id: Mapped[int] = mapped_column(
        Integer,  # Coincide con tarjas.id.
        ForeignKey("tarjas.id"),  # No puede procesarse una tarja inexistente.
        primary_key=True,  # Permite la misma tarja en otro proceso, no dos veces en este.
        index=True,  # Acelera saldo, trazabilidad y recálculo de estado por tarja.
        nullable=False,  # Toda fila debe tener una tarja de origen.
    )  # Finaliza la relación con la tarja.
    # Guarda las cajas de esta tarja dentro del proceso.
    cantidad_cajas: Mapped[int] = mapped_column(Integer, nullable=False)
    # Guarda el peso calculado desde cajas o ingresado para embalaje granel.
    kilos_procesados: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    # Marca que esta fila es el último proceso vigente de la tarja.
    tarja_terminada: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
