from fastapi import FastAPI #Creamos la instancia de la aplicación FastAPI
from fastapi.middleware.cors import CORSMiddleware #Agregamos el middleware CORS para permitir solicitudes desde diferentes orígenes

from app.api.routers import auth, embalajes, especies, opciones, productores, tipos_bandeja, variedades # Importamos autenticación, los mantenimientos y las opciones de formularios.
from app.api.routers.calidades import router as calidades_router
from app.api.routers.sistemas_productivos import router as sistemas_productivos_router
from app.core.config import settings # Importamos la configuración


app = FastAPI(
    title=settings.project_name,  # Nombre del proyecto
    version="0.1.0",  # Versión de la API
    # Con MOSTRAR_DOCS=false (producción) no se publican /docs, /redoc ni /openapi.json.
    docs_url="/docs" if settings.mostrar_docs else None,
    redoc_url="/redoc" if settings.mostrar_docs else None,
    openapi_url="/openapi.json" if settings.mostrar_docs else None,
)

# Configuración de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,  # Solo los orígenes de CORS_ORIGINS (el frontend, http://localhost:5173 en desarrollo)
    # El token viaja en el header Authorization, no en cookies: no hace falta enviar credenciales.
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT"],  # Métodos usados por la aplicación (no hay DELETE: nada se borra)
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

# Publica las cuatro operaciones administrativas de especies.
app.include_router(
    especies.router,  # Conserva las dependencias y contratos del nuevo catálogo.
    prefix=settings.api_v1_prefix,  # Comparte el prefijo /api/v1 existente.
)  # No modifica las rutas de autenticación o productores.

# Publica las cuatro operaciones de variedades con su asociación a especie.
app.include_router(
    variedades.router,  # Incluye listado, detalle, creación y actualización.
    prefix=settings.api_v1_prefix,  # El router no repite este prefijo general.
)  # Finaliza el registro del mantenimiento de variedades.

# Publica los dos mantenimientos administrativos independientes de HU09.
app.include_router(calidades_router, prefix=settings.api_v1_prefix)
app.include_router(sistemas_productivos_router, prefix=settings.api_v1_prefix)

# Publica los mantenimientos administrativos de tipos de bandeja y embalajes (HU10).
app.include_router(tipos_bandeja.router, prefix=settings.api_v1_prefix)
app.include_router(embalajes.router, prefix=settings.api_v1_prefix)

# Publica las cinco listas de solo lectura para los formularios de recepción (HU11).
app.include_router(opciones.router, prefix=settings.api_v1_prefix)

@app.get("/health", tags=["Health"])  # Definimos la ruta raíz de la API    
def health() -> dict[str, str]: # Definimos la función que se ejecutará al acceder a la ruta raíz
    return {"status": "ok"}  # Retornamos un diccionario con el estado de la API
