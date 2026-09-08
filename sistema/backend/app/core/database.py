"""
Motor y sesión de SQLAlchemy.
Este es el ÚNICO módulo que sabe cómo conectarse a la base de datos.
El cliente (frontend) jamás la toca directamente — todo pasa por acá, vía los
routers y services de la API.
"""

# Tipo que permite indicar que una función produce valores uno por uno.
from collections.abc import Generator

# Crea el motor que administra la conexión entre la aplicación y la base de datos.
from sqlalchemy import create_engine

# Clase base para declarar los modelos de la base de datos.
# Representa una sesión activa para ejecutar consultas y transacciones.
# Crea una fábrica reutilizable de sesiones de base de datos.
from sqlalchemy.orm import Declarativebase,Session,sessionmaker

# Importa la configuración de conexión definida para la aplicación.
from app.core.config import settings 

# Crea el motor que administra las conexiones con la base de datos.
# Usa la URL de conexión configurada en settings.
# echo=True muestra en la consola las consultas SQL ejecutadas.
# future=True utiliza el estilo moderno de SQLAlchemy.
engine = create_engine(settings.database_url, echo=True, future=True)

# Crea una fábrica para generar nuevas sesiones de base de datos.
# autocommit=False exige confirmar manualmente las operaciones mediante commit().
# autoflush=False evita enviar cambios automáticamente antes de cada consulta.
# bind=engine conecta las sesiones con el motor configurado.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Declara la clase base que utilizarán los modelos de la aplicación.
class Base(DeclarativeBase):
    # No necesita contenido adicional porque hereda la configuración de SQLAlchemy.
    pass

# Define una función generadora que entrega una sesión a los endpoints.
# Generator indica que produce una sesión y luego finaliza su ciclo de vida.
def get_db() -> Generator[Session, None, None]:
    """
    Devuelve una sesión de base de datos para usar en un endpoint.
    Se usa como dependencia en los routers, y FastAPI se encarga de abrirla y cerrarla automáticamente.
    """
    # Crea una nueva sesión usando la configuración de SessionLocal.
    db = SessionLocal()
    try:
        # Entrega la sesión al endpoint que la necesita.
        yield db
    finally:
        # Cierra la sesión aunque ocurra un error durante la solicitud.
        db.close()