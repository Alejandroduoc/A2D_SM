from fastapi import FastAPI #Creamos la instancia de la aplicación FastAPI
from fastapi.middleware.cors import CORSMiddleware #Agregamos el middleware CORS para permitir solicitudes desde diferentes orígenes

from app.api.routers import auth, productores # Importamos autenticación y mantenimiento de productores.
from app.core.config import settings # Importamos la configuración


app = FastAPI(
    title=settings.project_name,  # Nombre del proyecto
    version="0.1.0",  # Versión de la API
)

# Configuración de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,  # Solo los orígenes de CORS_ORIGINS (el frontend, http://localhost:5173 en desarrollo)
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],  # Métodos usados por la aplicación
    allow_headers=["Authorization", "Content-Type"],  # Token y cuerpos JSON
)       

app.include_router(
    auth.router,
    prefix=settings.api_v1_prefix,
)  # Incluimos el enrutador de autenticación

# Publica el mantenimiento de productores bajo el prefijo general de la API.
app.include_router(
    productores.router,  # Incorpora las cuatro operaciones protegidas del módulo.
    prefix=settings.api_v1_prefix,  # Conserva /api/v1 como prefijo común.
)  # Finaliza el registro del router de productores.

@app.get("/health", tags=["Health"])  # Definimos la ruta raíz de la API    
def health() -> dict[str, str]: # Definimos la función que se ejecutará al acceder a la ruta raíz
    return {"status": "ok"}  # Retornamos un diccionario con el estado de la API
