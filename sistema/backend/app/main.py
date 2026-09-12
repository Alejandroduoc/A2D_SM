from fastapi import FastAPI #Creamos la instancia de la aplicación FastAPI
from fastapi.middleware.cors import CORSMiddleware #Agregamos el middleware CORS para permitir solicitudes desde diferentes orígenes

from app.api.routers import auth, users
from app.core.config import settings
from app.core.database import Base, engine
from app.models import usuario


app = FastAPI(
    title=settings.project_name,  # Nombre del proyecto
    version="0.1.0",  # Versión de la API
)

# Configuración de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,  # Permitir todas las solicitudes desde cualquier origen
    allow_credentials=True,
    allow_methods=["*"],  # Permitir todos los métodos HTTP
    allow_headers=["*"],  # Permitir todos los encabezados
)       

app.include_router(auth.router,
                   prefix=settings.api_v1_prefix
                   )  # Incluimos el enrutador de autenticación
app.include_router(users.router, prefix=settings.api_v1_prefix)


@app.on_event("startup")
def create_tables() -> None:
    Base.metadata.create_all(bind=engine)

@app.get("/health", tags=["Health"])  # Definimos la ruta raíz de la API    
def health() -> dict[str, str]: # Definimos la función que se ejecutará al acceder a la ruta raíz
    return {"status": "ok"}  # Retornamos un diccionario con el estado de la API