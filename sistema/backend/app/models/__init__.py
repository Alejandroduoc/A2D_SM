"""Importa los modelos para registrarlos en Base.metadata."""

# Importa E4 para que Alembic y las bases temporales descubran sus tablas.
from app.models import proceso  # noqa: F401
