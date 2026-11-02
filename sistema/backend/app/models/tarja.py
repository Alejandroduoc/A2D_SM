"""Tarjas de recepción con pesos, calidad y trazabilidad del registro."""

# Base de los estados de la tarja.
import enum
# Fecha de recepción y momento UTC del registro.
from datetime import date, datetime, timezone
# Pesos exactos, sin los errores de float.
from decimal import Decimal

# Tipos de columna, restricciones y la secuencia del número de tarja.
from sqlalchemy import (
    CheckConstraint,  # Reglas que SQL Server comprueba en cada fila.
    Date,  # Día sin hora.
    DateTime,  # Fecha con hora.
    Enum,  # Estado guardado como texto.
    ForeignKey,  # Relación con otra tabla.
    Integer,  # Identidades, cantidades y kilos netos.
    Numeric,  # Pesos con dos decimales.
    Sequence,  # Numeración correlativa de SQL Server.
    SmallInteger,  # Porcentaje de calidad visual.
    String,  # Identificador del usuario (UUID).
)  # Finaliza las importaciones de SQLAlchemy.
# Declaran atributos tipados con el estilo SQLAlchemy 2 del proyecto.
from sqlalchemy.orm import Mapped, mapped_column

# Registra el modelo en el mismo conjunto de tablas de la aplicación.
from app.core.database import Base

# Secuencia del número de tarja. En la base real la crea la migración 87d3341cb7a7; registrarla
# aquí permite que Base.metadata.create_all (base temporal de probar_catalogos) también la cree.
SEQ_NUMERO_TARJA = Sequence(
    "seq_numero_tarja",  # Mismo nombre que consulta services/tarja.py.
    start=1,  # Mismo inicio que la migración.
    increment=1,  # Correlativo de uno en uno.
    data_type=Integer,  # INT, igual que la columna numero_tarja.
    metadata=Base.metadata,  # La crea create_all antes de las tablas.
)  # Finaliza la declaración de la secuencia.


# Estados previstos para el ciclo completo de una tarja.
class EstadoTarja(str, enum.Enum):
    RECEPCIONADA = "RECEPCIONADA"  # Registrada, sin procesos.
    PARCIAL = "PARCIAL"  # Con procesos, sin marca de terminada (E4).
    PROCESADA = "PROCESADA"  # Algún proceso la marcó como terminada (E4).
    ANULADA = "ANULADA"  # Anulada por el administrador, sin borrarla (HU24).


# Conserva los datos históricos usados para calcular los kilos recibidos.
class Tarja(Base):
    # Nombre de la tabla en SQL Server.
    __tablename__ = "tarjas"
    # Reglas que la base garantiza aunque falle la validación de la API.
    __table_args__ = (
        # Toda tarja trae al menos una bandeja.
        CheckConstraint(
            "cantidad_bandejas > 0",
            name="ck_tarjas_cantidad_bandejas_positiva",
        ),
        # El peso de balanza siempre es positivo.
        CheckConstraint(
            "kilos_brutos > 0",
            name="ck_tarjas_kilos_brutos_positivos",
        ),
        # El pallet puede ser cero si la fruta llega sin pallet.
        CheckConstraint(
            "peso_pallet_kg >= 0",
            name="ck_tarjas_peso_pallet_kg_no_negativo",
        ),
        # La tara copiada sigue la regla del catálogo.
        CheckConstraint(
            "tara_kg > 0",
            name="ck_tarjas_tara_kg_positiva",
        ),
        # HU14 criterio 2: los kilos netos no pueden ser negativos ni cero.
        CheckConstraint(
            "kilos_netos > 0",
            name="ck_tarjas_kilos_netos_positivos",
        ),
        # Decisión B: calidad visual de 0 a 100.
        CheckConstraint(
            "porcentaje_calidad BETWEEN 0 AND 100",
            name="ck_tarjas_porcentaje_calidad_rango",
        ),
        # Contador de impresiones de HU16.
        CheckConstraint(
            "veces_impresa >= 0",
            name="ck_tarjas_veces_impresa_no_negativa",
        ),
    )  # Finaliza las restricciones de la tabla.

    # Identidad interna generada por la base.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Número operativo que asigna el service con la secuencia (HU13).
    numero_tarja: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    # Productor que entrega la fruta; sin tabla RECEPCIONES (decisión del 04/10).
    productor_id: Mapped[int] = mapped_column(
        Integer,  # Mismo tipo que productores.id.
        ForeignKey("productores.id"),  # No puede existir una tarja sin productor.
        index=True,  # Prepara los acumulados y el saldo por productor.
        nullable=False,  # Dato obligatorio.
    )  # Finaliza la declaración del productor.
    # Usuario que registró la tarja, leído de la sesión y no del JSON.
    usuario_id: Mapped[str] = mapped_column(
        String(36),  # Mismo tipo que usuarios.id.
        ForeignKey("usuarios.id"),  # Debe ser un usuario existente.
        nullable=False,  # Dato obligatorio.
    )  # Finaliza la declaración del usuario.
    # Sistema productivo elegido.
    sistema_productivo_id: Mapped[int] = mapped_column(
        Integer,  # Mismo tipo que el catálogo.
        ForeignKey("sistemas_productivos.id"),  # Debe existir en el catálogo.
        nullable=False,  # Dato obligatorio.
    )  # Finaliza la declaración del sistema productivo.
    # Variedad elegida; la especie se obtiene de ella.
    variedad_id: Mapped[int] = mapped_column(
        Integer,  # Mismo tipo que el catálogo.
        ForeignKey("variedades.id"),  # Debe existir en el catálogo.
        nullable=False,  # Dato obligatorio.
    )  # Finaliza la declaración de la variedad.
    # Calidad elegida.
    calidad_id: Mapped[int] = mapped_column(
        Integer,  # Mismo tipo que el catálogo.
        ForeignKey("calidades.id"),  # Debe existir en el catálogo.
        nullable=False,  # Dato obligatorio.
    )  # Finaliza la declaración de la calidad.
    # Tipo de bandeja elegido.
    tipo_bandeja_id: Mapped[int] = mapped_column(
        Integer,  # Mismo tipo que el catálogo.
        ForeignKey("tipos_bandeja.id"),  # Debe existir en el catálogo.
        nullable=False,  # Dato obligatorio.
    )  # Finaliza la declaración del tipo de bandeja.
    # Cantidad de bandejas recibidas.
    cantidad_bandejas: Mapped[int] = mapped_column(Integer, nullable=False)
    # Copia de la tara al registrar; un cambio en el catálogo no la altera (HU14 criterio 4).
    tara_kg: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    # Peso del pallet.
    peso_pallet_kg: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    # Peso de balanza.
    kilos_brutos: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    # Kilos netos calculados por el service, redondeados a entero.
    kilos_netos: Mapped[int] = mapped_column(Integer, nullable=False)
    # Porcentaje de calidad visual (decisión B).
    porcentaje_calidad: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    # Día en que llegó la fruta (decisión C).
    fecha_recepcion: Mapped[date] = mapped_column(Date, nullable=False)
    # Estado del flujo de la tarja.
    estado: Mapped[EstadoTarja] = mapped_column(
        Enum(EstadoTarja, length=20),  # Se guarda como texto.
        default=EstadoTarja.RECEPCIONADA,  # Toda tarja nueva parte recepcionada.
        nullable=False,  # Dato obligatorio.
    )  # Finaliza la declaración del estado.
    # Momento UTC del registro, que no se edita.
    fecha_hora: Mapped[datetime] = mapped_column(
        DateTime,  # Fecha con hora.
        default=lambda: datetime.now(timezone.utc),  # Se calcula al insertar.
        nullable=False,  # Dato obligatorio.
    )  # Finaliza la declaración de la fecha de registro.
    # Veces que se imprimió la tarja (HU16).
    veces_impresa: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Última impresión, si la hubo (HU16).
    impresa_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
