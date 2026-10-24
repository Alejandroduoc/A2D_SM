# Base de los schemas, límites de campos y validadores previos a la conversión.
from pydantic import BaseModel, Field, field_validator

# Reutiliza el cálculo de Módulo 11 y la representación común del RUT.
from app.core.validators import normalizar_rut, validar_rut_chileno

# Define los datos admitidos al crear un productor; la base genera id y estado.
class ProductorCreate(BaseModel):
    # El largo se comprueba después de validar y normalizar el RUT recibido.
    rut: str = Field(max_length=12)
    # Exige una razón social de 3 a 150 caracteres.
    razon_social: str = Field(min_length=3, max_length=150)
    # Admite omitir la dirección o enviarla con el largo permitido por el modelo.
    direccion: str | None = Field(default=None, max_length=200)
    # Admite omitir el teléfono o enviarlo con el largo permitido por el modelo.
    telefono: str | None = Field(default=None, max_length=20)

    # Revisa la entrada original antes de aplicar el límite del texto normalizado.
    @field_validator("rut", mode="before")
    # Vincula el validador al schema sin requerir una instancia ya construida.
    @classmethod
    # Acepta cualquier entrada para poder rechazar tipos incorrectos claramente.
    def validar_y_normalizar_rut(cls, valor: object) -> str:
        # Evita pasar números, nulos u otros objetos a las expresiones regulares.
        if not isinstance(valor, str):
            # Pydantic convierte este rechazo en un error de validación del campo.
            raise ValueError("El RUT debe ser texto")
        # Comprueba el dígito verificador antes de modificar la presentación.
        if not validar_rut_chileno(valor):
            # Informa una entrada inválida sin acceder a la base de datos.
            raise ValueError("RUT inválido")
        # Devuelve el valor que se guardará y sobre el que se mide max_length.
        return normalizar_rut(valor)


# Permite cambios parciales, incluida la corrección del RUT sin cambiar el id.
class ProductorUpdate(BaseModel):
    # None significa no modificar el RUT; un texto debe pasar las reglas del alta.
    rut: str | None = Field(default=None, max_length=12)
    # Permite conservar la razón social o reemplazarla dentro de los mismos límites.
    razon_social: str | None = Field(default=None, min_length=3, max_length=150)
    # None conserva la dirección actual; no representa una orden de vaciarla.
    direccion: str | None = Field(default=None, max_length=200)
    # None conserva el teléfono actual.
    telefono: str | None = Field(default=None, max_length=20)
    # False debe conservarse como cambio para permitir la desactivación.
    activo: bool | None = None

    # Aplica validación y normalización antes de comprobar el largo final del RUT.
    @field_validator("rut", mode="before")
    # Vincula este validador a la clase del schema de actualización.
    @classmethod
    # Admite None como señal de que el servicio no debe modificar el campo.
    def validar_y_normalizar_rut(cls, valor: object) -> str | None:
        # Evita intentar normalizar un RUT que el cliente no quiere cambiar.
        if valor is None:
            # El servicio posterior descartará este valor con exclude_none=True.
            return None
        # Rechaza entradas que no sean texto antes de usar expresiones regulares.
        if not isinstance(valor, str):
            # Mantiene el mismo mensaje de tipo que el schema de creación.
            raise ValueError("El RUT debe ser texto")
        # Reutiliza el validador existente para cualquier corrección del RUT.
        if not validar_rut_chileno(valor):
            # Impide aceptar un nuevo RUT con un dígito verificador incorrecto.
            raise ValueError("RUT inválido")
        # Devuelve la misma representación normalizada utilizada en creación.
        return normalizar_rut(valor)


# Expone únicamente los seis campos del diseño de productores.
class ProductorOut(BaseModel):
    # Identidad interna que se mantiene al corregir el RUT o desactivar el registro.
    id: int
    # RUT almacenado con su representación normalizada.
    rut: str
    # Nombre o razón social actual del productor.
    razon_social: str
    # Dirección actual, que puede no estar informada.
    direccion: str | None
    # Teléfono actual, que puede no estar informado.
    telefono: str | None
    # Estado actual que permite conservar productores desactivados.
    activo: bool

    # Permite construir la respuesta leyendo atributos de una instancia ORM.
    model_config = {"from_attributes": True}
