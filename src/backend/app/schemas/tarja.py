"""Contratos de alta y consulta de tarjas de recepción (HU12, HU13 y HU14)."""

# Fecha de recepción y fecha y hora del registro.
from datetime import date, datetime
# Pesos exactos y redondeo del promedio por bandeja.
from decimal import ROUND_HALF_EVEN, Decimal
# Zona horaria de Chile para saber qué día es "hoy" en la planta.
from zoneinfo import ZoneInfo

# Base de los schemas, límites de campos, validadores y campos calculados.
from pydantic import BaseModel, Field, computed_field, field_validator

# Mayor id posible; un número mayor responde 422 en vez de un error interno.
from app.core.validators import MAX_INT_SQL_SERVER
# Misma regla de los pesos de HU10: un booleano no es un número.
from app.schemas.tipo_bandeja import validar_decimal_no_booleano

# Zona horaria de la planta; la fecha en UTC adelanta un día después de las 21:00.
ZONA_CHILE = ZoneInfo("America/Santiago")


# Devuelve la fecha de hoy en Chile, no la del servidor.
def hoy_en_chile() -> date:
    # Toma la hora actual en Santiago y conserva solo el día.
    return datetime.now(ZONA_CHILE).date()


# Define los datos que el operador envía al registrar una tarja.
class TarjaCreate(BaseModel):
    """El número, los kilos netos, la tara, el estado y el usuario los pone el sistema."""

    # Rechaza campos no declarados (numero_tarja, kilos_netos, estado, etc.).
    model_config = {"extra": "forbid"}
    # Productor que entrega la fruta; strict impide textos y booleanos.
    productor_id: int = Field(gt=0, le=MAX_INT_SQL_SERVER, strict=True)
    # Sistema productivo de la fruta.
    sistema_productivo_id: int = Field(gt=0, le=MAX_INT_SQL_SERVER, strict=True)
    # Variedad de la fruta; la especie se obtiene de ella.
    variedad_id: int = Field(gt=0, le=MAX_INT_SQL_SERVER, strict=True)
    # Calidad de la fruta.
    calidad_id: int = Field(gt=0, le=MAX_INT_SQL_SERVER, strict=True)
    # Tipo de bandeja; el service copia su tara en la tarja.
    tipo_bandeja_id: int = Field(gt=0, le=MAX_INT_SQL_SERVER, strict=True)
    # Cantidad de bandejas: positiva y dentro de la capacidad técnica de INT.
    cantidad_bandejas: int = Field(gt=0, le=MAX_INT_SQL_SERVER, strict=True)
    # Peso del pallet; puede ser cero si la fruta llega sin pallet.
    peso_pallet_kg: Decimal = Field(ge=0, max_digits=8, decimal_places=2)
    # Peso de balanza (brutos), positivo; DECIMAL define su capacidad técnica.
    kilos_brutos: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    # Porcentaje de calidad visual, de 0 a 100 (decisión B).
    porcentaje_calidad: int = Field(ge=0, le=100, strict=True)
    # Fecha de recepción; si no llega, el validador pone hoy (decisión C).
    fecha_recepcion: date | None = Field(default=None, validate_default=True)

    # Revisa los pesos antes de convertirlos a Decimal.
    @field_validator("peso_pallet_kg", "kilos_brutos", mode="before")
    # Vincula el validador a la clase del schema.
    @classmethod
    # Impide que True y False se interpreten como uno y cero.
    def rechazar_peso_booleano(cls, valor: object) -> object:
        # Aplica la regla común para entradas decimales.
        return validar_decimal_no_booleano(valor)

    # Completa la fecha y rechaza las fechas futuras.
    @field_validator("fecha_recepcion")
    # Vincula el validador a la clase del schema.
    @classmethod
    # Devuelve siempre una fecha, nunca None.
    def validar_fecha_recepcion(cls, valor: date | None) -> date:
        # Calcula el día actual en la planta una sola vez.
        hoy = hoy_en_chile()
        # Sin fecha, la tarja queda con la de hoy.
        if valor is None:
            # Usa el día actual en Chile como valor por defecto.
            return hoy
        # Una fecha posterior a hoy no corresponde a una recepción real.
        if valor > hoy:
            # Pydantic lo convierte en un error 422 asociado al campo.
            raise ValueError("La fecha de recepción no puede ser posterior a hoy")
        # La fecha de hoy o una anterior se conserva tal cual.
        return valor


# Define los datos corregibles de una tarja sin permitir alterar sus campos históricos.
class TarjaUpdate(TarjaCreate):
    """Corrige una tarja recepcionada; el número sigue siendo histórico.

    La tara se conserva si el tipo de bandeja no cambia; si cambia, el service
    copia la tara vigente del tipo nuevo (decisión del 2026-11-07).
    """

    # Al corregir, la fecha es obligatoria: sin ella, el validador heredado pondría hoy (B1).
    # Sin valor por defecto, un cuerpo sin la fecha o con null responde 422; la regla de no futura se hereda.
    fecha_recepcion: date
    # Explica por qué se modifica una tarja ya impresa o registrada.
    motivo: str = Field(min_length=1, max_length=255)

    # No acepta motivos formados solo por espacios ni más largos que la columna.
    @field_validator("motivo")
    # Vincula el validador a la clase del schema.
    @classmethod
    # Conserva el motivo limpio para la auditoría.
    def validar_motivo(cls, valor: str) -> str:
        # Quita espacios accidentales al comienzo y al final.
        motivo = valor.strip()
        # Un texto vacío no explica una corrección.
        if not motivo:
            # Pydantic devuelve 422 asociado al campo motivo.
            raise ValueError("El motivo de la corrección es obligatorio")
        # NVARCHAR(255) cuenta unidades UTF-16: un emoji ocupa dos y Python lo cuenta como uno.
        # Sin esta regla, 128 emojis pasan max_length y SQL Server los rechaza con un error 500.
        if len(motivo.encode("utf-16-le")) // 2 > 255:
            # Pydantic devuelve 422 asociado al campo motivo.
            raise ValueError("El motivo supera los 255 caracteres permitidos")
        # Entrega el motivo ya normalizado.
        return motivo


# Expone los datos de una tarja registrada.
class TarjaOut(BaseModel):
    """Representa una tarja devuelta por la API, sin el usuario que la registró."""

    # Permite construir la salida leyendo atributos de una instancia ORM.
    model_config = {"from_attributes": True}
    # Identificador interno de la tarja.
    id: int
    # Número correlativo asignado por la secuencia (HU13).
    numero_tarja: int
    # Productor que entregó la fruta.
    productor_id: int
    # Sistema productivo registrado.
    sistema_productivo_id: int
    # Variedad registrada.
    variedad_id: int
    # Calidad registrada.
    calidad_id: int
    # Tipo de bandeja usado.
    tipo_bandeja_id: int
    # Cantidad de bandejas recibidas.
    cantidad_bandejas: int
    # Tara copiada del tipo de bandeja al registrar (HU14 criterio 4).
    tara_kg: Decimal
    # Peso del pallet.
    peso_pallet_kg: Decimal
    # Peso de balanza.
    kilos_brutos: Decimal
    # Kilos netos calculados por el service (HU14 criterio 1).
    kilos_netos: int
    # Porcentaje de calidad visual.
    porcentaje_calidad: int
    # Día en que se recibió la fruta.
    fecha_recepcion: date
    # Estado de la tarja; el enum EstadoTarja se entrega como texto.
    estado: str
    # Fecha y hora en que se registró en el sistema.
    fecha_hora: datetime
    # Veces que se imprimió (HU16).
    veces_impresa: int
    # Última impresión, si la hubo (HU16).
    impresa_en: datetime | None
    # Sus kilos pendientes se rebajaron como merma.
    merma_rebajada: bool

    # Se agrega a la respuesta aunque no sea una columna (HU14 criterio 3).
    @computed_field
    # Se calcula al leerlo, a partir de los kilos netos y las bandejas.
    @property
    # Kilos netos por bandeja con dos decimales.
    def kg_promedio_bandeja(self) -> Decimal:
        # Divide en Decimal para no arrastrar errores de float.
        promedio = Decimal(self.kilos_netos) / Decimal(self.cantidad_bandejas)
        # Redondea a dos decimales con el mismo criterio bancario de los kilos netos.
        return promedio.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)


# Fila del listado de tarjas (HU17 criterio 1).
class TarjaResumenOut(BaseModel):
    """Datos de una tarja en el listado, con los nombres de sus catálogos."""

    # Identificador con el que se pide el detalle.
    id: int
    # Número correlativo de la tarja.
    numero_tarja: int
    # Día en que se recibió la fruta.
    fecha_recepcion: date
    # Código del productor.
    productor_codigo: int
    # Nombre del productor.
    productor_razon_social: str
    # Especie, obtenida de la variedad.
    especie: str
    # Variedad de la fruta.
    variedad: str
    # Cantidad de bandejas recibidas.
    cantidad_bandejas: int
    # Kilos netos de la tarja.
    kilos_netos: int
    # Estado de la tarja, como texto.
    estado: str
    # Veces impresa: decide si el listado ofrece Imprimir o Reimprimir (HU16).
    veces_impresa: int


# Detalle completo de una tarja (HU17 criterio 2).
class TarjaDetalleOut(TarjaOut):
    """Agrega a la tarja los nombres de sus catálogos, el responsable y sus kilos."""

    # Código del productor.
    productor_codigo: int
    # RUT del productor.
    productor_rut: str
    # Nombre del productor.
    productor_razon_social: str
    # Nombre del sistema productivo.
    sistema_productivo: str
    # Id de la especie, obtenido de la variedad: la corrección la elige por id aunque esté inactiva.
    especie_id: int
    # Especie, obtenida de la variedad.
    especie: str
    # Nombre de la variedad.
    variedad: str
    # Nombre de la calidad.
    calidad: str
    # Nombre del tipo de bandeja.
    tipo_bandeja: str
    # Nombre del usuario que la registró; nunca sus credenciales.
    registrada_por: str
    # Kilos ya usados en procesos no anulados.
    kilos_procesados: Decimal
    # Kilos que quedan por procesar.
    kilos_pendientes: Decimal


# Saldo de bandejas de un productor en un tipo de bandeja (HU15 criterio 3).
class SaldoBandejaOut(BaseModel):
    """Entradas, salidas y saldo; el saldo puede ser negativo."""

    # Tipo de bandeja del saldo.
    tipo_bandeja_id: int
    # Nombre del tipo de bandeja.
    tipo_bandeja: str
    # Bandejas recibidas, sin las de tarjas anuladas.
    entradas: int
    # Bandejas devueltas; en el PMV siempre 0, porque llegan con la guía.
    salidas: int
    # Entradas menos salidas.
    saldo: int


# Acumulados del productor que ve el operador al elegirlo (decisión D).
class PendientesProductorOut(BaseModel):
    """Tarjas y kilos del productor que todavía no se procesan."""

    # Productor consultado.
    productor_id: int
    # Tarjas en estado RECEPCIONADA o PARCIAL.
    tarjas_sin_procesar: int
    # Sus kilos netos menos lo procesado; con decimales desde HU18, porque las cajas pueden pesar 11,35 kg.
    kilos_sin_procesar: Decimal
