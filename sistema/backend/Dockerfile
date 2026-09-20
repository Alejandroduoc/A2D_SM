# Dockerfile: receta para construir la imagen del backend (la API FastAPI).
# Una imagen es una "foto" con Python, el driver de SQL Server y nuestro código;
# de ella se crea el contenedor que corre la API.

# Imagen base: Linux Debian 12 ("bookworm") liviano con Python 3.12 ya instalado.
# Se fija bookworm porque el repositorio del driver de Microsoft (más abajo) es
# para Debian 12; con una base más nueva la instalación del driver podría fallar.
FROM python:3.12-slim-bookworm

# Instala el driver ODBC 18 de Microsoft, que pyodbc necesita para hablar con
# SQL Server. Es un solo RUN (una sola capa de la imagen) encadenado con "&&" y
# con "\" para seguir en la línea siguiente. Pasos:
#   1. apt-get update / install: instala herramientas base (curl, gnupg,
#      ca-certificates) y unixodbc-dev (la librería ODBC de Linux).
#   2. curl ... | gpg --dearmor: descarga la clave con la que Microsoft firma
#      sus paquetes y la guarda para poder verificarlos.
#   3. echo "deb ...": registra el repositorio de paquetes de Microsoft.
#   4. apt-get update: vuelve a leer la lista de paquetes, ahora con el repo nuevo.
#   5. ACCEPT_EULA=Y apt-get install msodbcsql18: instala el driver (exige aceptar
#      la licencia de Microsoft con esa variable).
#   6. apt-get clean && rm -rf /var/lib/apt/lists/*: borra archivos temporales
#      para que la imagen pese menos.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl gnupg ca-certificates unixodbc-dev \
    && curl -sSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && echo "deb [arch=amd64,arm64 signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" \
        > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Carpeta de trabajo dentro del contenedor; los comandos siguientes se ejecutan aquí.
WORKDIR /app

# Se copia primero SOLO requirements.txt y se instalan las dependencias. Así Docker
# reutiliza esta capa (caché) mientras requirements.txt no cambie, y no reinstala
# todo cada vez que se modifica el código.
COPY requirements.txt .
# --no-cache-dir evita guardar la caché de pip dentro de la imagen (pesa menos).
RUN pip install --no-cache-dir -r requirements.txt

# Copia todo el backend dentro de la imagen: la carpeta app/ y también alembic.ini
# y migrations/ (las migraciones se ejecutan dentro del contenedor).
# No se copia .env ni .venv (ver .dockerignore): los secretos no van en la imagen.
# En desarrollo esta copia queda tapada por el volumen de docker-compose.yml, que
# comparte tu carpeta con el contenedor; sirve para cuando se despliegue sin volumen.
COPY . .

# Documenta que la API escucha en el puerto 8000. No lo publica al exterior:
# eso lo hace "ports" en docker-compose.yml.
EXPOSE 8000

# Comando por defecto al iniciar el contenedor: arranca uvicorn (el servidor de la
# API). --host 0.0.0.0 es necesario para que se pueda acceder desde fuera del
# contenedor; con 127.0.0.1 solo respondería dentro de él.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
