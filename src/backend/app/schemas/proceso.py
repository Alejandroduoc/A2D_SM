"""Contratos de alta y consulta de procesos de tarjas (HU18)."""

# Fecha de elaboración y fecha y hora del registro.
from datetime import date, datetime
# Pesos exactos, sin float.
from decimal import Decimal

# Base de los schemas, límites de campos y validadores.
from pydantic import BaseModel, Field, field_validator

# Mayor id posible; un número mayor responde 422 en vez de un error interno.
from app.core.validators import MAX_INT_SQL_SERVER
# Fecha de hoy en la planta, la misma regla de la fecha de recepción.
from app.schemas.tarja import hoy_en_chile
# Misma regla de los pesos de HU10: un booleano no es un número.
from app.schemas.tipo_bandeja import validar_decimal_no_booleano


# Una tarja dentro del proceso que se registra.
class ProcesoTarjaCreate(BaseModel):
    """El folio, los totales y los kilos de un embalaje fijo los pone el sistema."""

    # Rechaza campos no declarados.
    model_config = {"extra": "forbid"}
    # Tarja de recepción que se consume.
    tarja_id: int = Field(gt=0, le=MAX_INT_SQL_SERVER, strict=True)
    # Cajas obtenidas de esta tarja; con decimales si una caja se arma con fruta de dos tarjas.
    cantidad_cajas: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    # Solo a granel: con embalaje fijo el service los calcula y rechaza este campo (criterio 2).
    kilos_procesados: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    # El operador indica que esta tarja no se procesa más (criterio 5).
    tarja_terminada: bool = Field(default=False, strict=True)

    # Revisa las cajas y el peso antes de convertirlos a Decimal.
    @field_validator("cantidad_cajas", "kilos_procesados", mode="before")
    # Vincula el validador a la clase del schema.
    @classmethod
    # Impide que True y False se interpreten como uno y cero.
    def rechazar_numero_booleano(cls, valor: object) -> object:
        # Aplica la regla común para entradas decimales.
        return validar_decimal_no_booleano(valor)


# Cómo debe quedar un proceso ya registrado.
class ProcesoEdicion(BaseModel):
    """Solo las tarjas: el folio, el embalaje y la fecha del proceso no cambian."""

    # Rechaza campos no declarados, como folio o kilos_salida.
    model_config = {"extra": "forbid"}
    # Al menos una tarja.
    tarjas: list[ProcesoTarjaCreate] = Field(min_length=1)

    # Una tarja aparece una sola vez en cada envío.
    @field_validator("tarjas")
    # Vincula el validador a la clase del schema.
    @classmethod
    # Devuelve la lista sin cambios si no hay repetidas.
    def rechazar_tarjas_repetidas(cls, valor: list[ProcesoTarjaCreate]) -> list[ProcesoTarjaCreate]:
        # Reúne los ids recibidos.
        ids = [fila.tarja_id for fila in valor]
        # Un conjunto más corto significa que había repetidas.
        if len(set(ids)) != len(ids):
            # Pydantic lo convierte en un error 422 asociado al campo.
            raise ValueError("Una tarja no se puede repetir dentro del mismo proceso")
        # Conserva el orden que eligió el operador.
        return valor


# Datos que envía el operador al registrar un proceso.
class ProcesoCreate(ProcesoEdicion):
    """Un proceso usa un solo embalaje y consume una o más tarjas."""

    # Embalaje con el que salen todas las cajas del proceso.
    embalaje_id: int = Field(gt=0, le=MAX_INT_SQL_SERVER, strict=True)
    # Día de elaboración; si no llega, el validador pone hoy.
    fecha_elaboracion: date | None = Field(default=None, validate_default=True)

    # Completa la fecha y rechaza las fechas futuras.
    @field_validator("fecha_elaboracion")
    # Vincula el validador a la clase del schema.
    @classmethod
    # Devuelve siempre una fecha, nunca None.
    def validar_fecha_elaboracion(cls, valor: date | None) -> date:
        # Calcula el día actual en la planta una sola vez.
        hoy = hoy_en_chile()
        # Sin fecha, el proceso queda con la de hoy.
        if valor is None:
            # Usa el día actual en Chile como valor por defecto.
            return hoy
        # No se puede declarar elaborada fruta en un día que no ha llegado.
        if valor > hoy:
            # Pydantic lo convierte en un error 422 asociado al campo.
            raise ValueError("La fecha de elaboración no puede ser posterior a hoy")
        # La fecha de hoy o una anterior se conserva tal cual.
        return valor


# Embalaje que se ofrece en el formulario de proceso.
class EmbalajeOpcionOut(BaseModel):
    """El operador de proceso no accede a los mantenedores: recibe solo lo que necesita."""

    # Permite construir la salida leyendo atributos de una instancia ORM.
    model_config = {"from_attributes": True}
    # Identificador del embalaje.
    id: int
    # Nombre visible.
    nombre: str
    # Kilos por caja; nulo a granel.
    kg_por_caja: Decimal | None
    # Indica que los kilos se ingresan a mano.
    es_granel: bool


# Tarja con sus kilos: por procesar (HU18 criterio 3) o con merma rebajada.
class TarjaDisponibleOut(BaseModel):
    """Datos que el operador necesita, con la diferencia entre kilos netos y procesados."""

    # Identificador con el que se envía al registrar.
    id: int
    # Número correlativo de la tarja.
    numero_tarja: int
    # Día en que se recibió la fruta.
    fecha_recepcion: date
    # Código del productor.
    productor_codigo: int
    # Nombre del productor.
    productor_razon_social: str
    # Sistema productivo: no se mezcla en un proceso.
    sistema_productivo: str
    # Especie: no se mezcla en un proceso.
    especie: str
    # Variedad: sí puede variar dentro de un proceso.
    variedad: str
    # Calidad: no se mezcla en un proceso.
    calidad: str
    # Kilos netos recibidos.
    kilos_netos: int
    # Kilos ya usados en procesos no anulados.
    kilos_procesados: Decimal
    # Kilos netos menos procesados: lo que le queda o, si se rebajó, su merma.
    kilos_pendientes: Decimal
    # RECEPCIONADA o PARCIAL.
    estado: str


# Una tarja dentro de un proceso registrado (HU18 criterio 7).
class ProcesoTarjaOut(BaseModel):
    """Vincula lo procesado con su tarja y su productor."""

    # Tarja de recepción consumida.
    tarja_id: int
    # Número de esa tarja.
    numero_tarja: int
    # Código del productor.
    productor_codigo: int
    # Nombre del productor.
    productor_razon_social: str
    # Sistema productivo: la fruta que se agregue debe coincidir.
    sistema_productivo: str
    # Especie de la fruta.
    especie: str
    # Variedad de la fruta.
    variedad: str
    # Calidad: la fruta que se agregue debe coincidir.
    calidad: str
    # Cajas obtenidas de la tarja en este proceso.
    cantidad_cajas: Decimal
    # Kilos de la tarja en este proceso.
    kilos_procesados: Decimal
    # Lo más que esta fila podría tener al editarla: lo que tiene más lo que le queda a la tarja.
    kilos_disponibles: Decimal
    # El operador la dio por terminada en este proceso.
    tarja_terminada: bool
    # Estado actual de la tarja.
    estado_tarja: str


# Fila del listado de procesos.
class ProcesoResumenOut(BaseModel):
    """Cabecera de un proceso, con los nombres que muestra la pantalla."""

    # Identificador con el que se pide el detalle.
    id: int
    # Folio P más el correlativo.
    folio: str
    # Día de elaboración.
    fecha_elaboracion: date
    # Momento del registro, en UTC.
    fecha_hora: datetime
    # Embalaje del proceso.
    embalaje_id: int
    # Nombre del embalaje.
    embalaje: str
    # Kilos por caja; nulo a granel. Al agregar fruta se usa aunque esté desactivado.
    embalaje_kg_por_caja: Decimal | None
    # Suma de las cajas.
    cantidad_cajas: Decimal
    # Suma de los kilos.
    kilos_salida: Decimal
    # Marca de HU25.
    anulado: bool
    # Nombre del usuario que lo registró; nunca sus credenciales.
    registrado_por: str


# Proceso con sus tarjas.
class ProcesoDetalleOut(ProcesoResumenOut):
    """Agrega a la cabecera el detalle por tarja."""

    # Una fila por cada tarja del proceso.
    tarjas: list[ProcesoTarjaOut]


# Resultado de rebajar como merma el saldo de una tarja.
class TarjaTerminadaOut(BaseModel):
    """Muestra cómo quedó la tarja, para confirmárselo al operador."""

    # Tarja cerrada.
    tarja_id: int
    # Número de esa tarja.
    numero_tarja: int
    # Kilos netos recibidos.
    kilos_netos: int
    # Kilos que salieron en procesos no anulados.
    kilos_procesados: Decimal
    # Kilos netos menos kilos procesados.
    kilos_merma: Decimal
    # Estado resultante.
    estado: str


# Una tarja de recepción con su rendimiento y su merma (HU19 criterio 2).
class RendimientoTarjaOut(BaseModel):
    """Se calcula al consultar: nunca se guarda."""

    # Identificador interno de la tarja.
    tarja_id: int
    # Número de la tarja.
    numero_tarja: int
    # Código del productor.
    productor_codigo: int
    # Nombre del productor.
    productor_razon_social: str
    # Especie de la fruta.
    especie: str
    # Variedad de la fruta.
    variedad: str
    # Calidad de la fruta.
    calidad: str
    # Procesos vigentes de la tarja, también los de folios que no se ingresaron.
    folios: list[str]
    # Kilos netos de la tarja.
    kilos_entrada: Decimal
    # Suma de sus kilos en todos sus procesos no anulados.
    kilos_procesados: Decimal
    # Kilos de entrada menos kilos procesados.
    merma: Decimal
    # Kilos procesados sobre kilos de entrada, en porcentaje con dos decimales.
    rendimiento: Decimal
    # Verdadero mientras la tarja no esté terminada (criterio 4).
    provisional: bool


# Total de las tarjas consultadas (HU19 criterio 3).
class RendimientoTotalOut(BaseModel):
    """Suma las tarjas y calcula el rendimiento sobre esas sumas."""

    # Suma de los kilos de entrada.
    kilos_entrada: Decimal
    # Suma de los kilos procesados.
    kilos_procesados: Decimal
    # Suma de las mermas.
    merma: Decimal
    # Nulo si no hay tarjas: no se divide por cero.
    rendimiento: Decimal | None
    # Verdadero si alguna tarja sigue abierta.
    provisional: bool


# Resultado de la consulta por folios (HU19).
class RendimientoOut(BaseModel):
    """Las tarjas, su total y los folios que no entraron en el cálculo."""

    # Una fila por tarja, aunque aparezca en varios folios.
    tarjas: list[RendimientoTarjaOut]
    # Total de esas tarjas.
    total: RendimientoTotalOut
    # Folios ingresados que no existen.
    folios_no_encontrados: list[str]
    # Folios ingresados que están anulados y no cuentan.
    folios_anulados: list[str]
