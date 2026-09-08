from fastapi import FastAPI #Creamos la instancia de la aplicación FastAPI
from fastapi.middleware.cors import CORSMiddleware #Agregamos el middleware CORS para permitir solicitudes desde diferentes orígenes

from app.api.routers import auth # Importamos el enrutador de autenticación
from app.core.cofing import settings # Importamos la configuración


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
