"""Contratos de alta, edición y consulta de sistemas productivos."""

from pydantic import BaseModel, Field, field_validator

from app.core.validators import normalizar_nombre_catalogo


class SistemaProductivoCreate(BaseModel):
    """Recibe únicamente el nombre de un sistema productivo nuevo."""

    model_config = {"extra": "forbid"}
    nombre: str = Field(min_length=1, max_length=50)

    @field_validator("nombre", mode="before")
    @classmethod
    def normalizar_nombre(cls, valor: object) -> str:
        return normalizar_nombre_catalogo(valor)


class SistemaProductivoUpdate(BaseModel):
    """Admite cambios parciales de nombre y estado."""

    model_config = {"extra": "forbid"}
    nombre: str | None = Field(default=None, min_length=1, max_length=50)
    activo: bool | None = None

    @field_validator("nombre", mode="before")
    @classmethod
    def normalizar_nombre(cls, valor: object) -> str | None:
        if valor is None:
            return None
        return normalizar_nombre_catalogo(valor)


class SistemaProductivoOut(BaseModel):
    """Expone los campos públicos del catálogo."""

    model_config = {"from_attributes": True}
    id: int
    nombre: str
    activo: bool
