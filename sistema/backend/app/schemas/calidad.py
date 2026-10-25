"""Contratos de alta, edición y consulta de calidades."""

from pydantic import BaseModel, Field, field_validator

from app.core.validators import normalizar_nombre_catalogo


class CalidadCreate(BaseModel):
    """Recibe únicamente el nombre de una calidad nueva."""

    model_config = {"extra": "forbid"}
    nombre: str = Field(min_length=1, max_length=50)

    @field_validator("nombre", mode="before")
    @classmethod
    def normalizar_nombre(cls, valor: object) -> str:
        return normalizar_nombre_catalogo(valor)


class CalidadUpdate(BaseModel):
    """Admite cambios parciales sin confundir False con ausencia."""

    model_config = {"extra": "forbid"}
    nombre: str | None = Field(default=None, min_length=1, max_length=50)
    activo: bool | None = None

    @field_validator("nombre", mode="before")
    @classmethod
    def normalizar_nombre(cls, valor: object) -> str | None:
        if valor is None:
            return None
        return normalizar_nombre_catalogo(valor)


class CalidadOut(BaseModel):
    """Expone los campos públicos del catálogo."""

    model_config = {"from_attributes": True}
    id: int
    nombre: str
    activo: bool
