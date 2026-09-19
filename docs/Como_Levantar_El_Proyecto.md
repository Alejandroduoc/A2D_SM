# Cómo levantar el proyecto (backend + SQL Server)

Guía para dejar funcionando en tu PC lo que hay construido hasta ahora: la API (FastAPI) y la base de datos SQL Server en Docker.

## 1. Requisitos

| Herramienta | Notas |
| --- | --- |
| Python 3.12 | En Windows, si `python` abre la Microsoft Store, desactiva el alias en *Configuración → Aplicaciones → Configuración avanzada de aplicaciones → Alias de ejecución de aplicaciones* (`python.exe` y `python3.exe`). |
| Docker Desktop | Debe estar abierto y mostrar "Engine running". |
| ODBC Driver for SQL Server | Versión 17 o 18. Ver cuál tienes en PowerShell: `Get-OdbcDriver \| Where-Object Name -like "*SQL Server*"` |
| Git | Para clonar el repositorio. |

## 2. Arquitectura del entorno

```text
Tu PC
├── Docker: contenedor "a2d_sqlserver" (SQL Server 2022, puerto 1433)  ← base de datos
└── Python (.venv): uvicorn + FastAPI (puerto 8000)                      ← API
```

La base de datos vive en su propio contenedor y sus datos se guardan en un volumen de Docker. La API se ejecuta directamente en tu PC durante el desarrollo.

## 3. Configuración (solo la primera vez)

Hay **dos** archivos `.env`. Ninguno se sube a git; cada integrante crea los suyos a partir de los `.env.example`.

**3.1. `A2D_SM/.env`** (raíz, lo lee Docker):

```env
MSSQL_SA_PASSWORD=<tu-contraseña>
```

**3.2. `sistema/backend/.env`** (lo lee la API):

```env
DATABASE_URL=mssql+pyodbc://sa:<tu-contraseña>@localhost:1433/a2d_sm?driver=ODBC+Driver+17+for+SQL+Server&TrustServerCertificate=yes
SECRET_KEY=<una-clave-larga-y-aleatoria>
```

Reglas importantes:

- La contraseña debe ser **la misma** en ambos archivos.
- SQL Server exige mínimo 8 caracteres con mayúscula, minúscula, número y símbolo; si no, el contenedor se cae al iniciar.
- Evita `@ : / ? #` en la contraseña: rompen la URL de conexión.
- Si tienes el driver 18, cambia `ODBC+Driver+17` por `ODBC+Driver+18`.
- Si falta `DATABASE_URL` o `SECRET_KEY`, la API **no arranca** (error `Field required`). Es intencional: no hay valores por defecto.

## 4. Levantar la base de datos

Desde la raíz del repositorio (`A2D_SM/`):

```powershell
docker compose up -d
docker compose ps
```

Espera a que el estado diga `healthy` (puede tardar unos segundos; la primera vez descarga la imagen, ~1.5 GB).

**Crear la base `a2d_sm`** (solo la primera vez o si se pierde el volumen; SQL Server no la crea solo):

```powershell
docker exec a2d_sqlserver /opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -P "<tu-contraseña>" -Q "CREATE DATABASE a2d_sm"
```

## 5. Levantar el backend

```powershell
cd sistema\backend
python -m venv .venv          # solo la primera vez
.venv\Scripts\activate        # debe aparecer (.venv) en el prompt
pip install -r requirements.txt   # solo la primera vez o si cambian las dependencias
uvicorn app.main:app --reload
```

## 6. Verificar que todo funciona

- `http://localhost:8000/health` → `{"status": "ok"}`
- `http://localhost:8000/docs` → documentación interactiva de la API.
- Conexión a la base (con el `.venv` activo, en `sistema/backend`):

  ```powershell
  python -c "from app.core.database import engine; print(engine.connect())"
  ```

  Debe imprimir `<sqlalchemy.engine.base.Connection object ...>`.

## 7. Uso diario

```powershell
# 1. Abrir Docker Desktop
# 2. Desde la raíz:
docker compose up -d
# 3. Desde sistema\backend:
.venv\Scripts\activate
uvicorn app.main:app --reload
```

| Acción | Comando (desde la raíz) |
| --- | --- |
| Ver estado de la base | `docker compose ps` |
| Ver logs de SQL Server | `docker compose logs db` |
| Apagar sin perder datos | `docker compose stop` |
| Encender de nuevo | `docker compose start` |
| Eliminar el contenedor (conserva los datos) | `docker compose down` |
| Borrar contenedor **y todos los datos** | `docker compose down -v` |

## 8. Problemas frecuentes

| Síntoma | Causa | Solución |
| --- | --- | --- |
| `no se encontró Python` | Alias de Microsoft Store | Desactivar el alias (ver sección 1) o usar `py` |
| `No module named 'sqlalchemy'` | `.venv` no activado | `.venv\Scripts\activate` |
| `Field required` al arrancar | Falta `sistema/backend/.env` o una variable | Crearlo desde `.env.example` |
| `error during connect ... dockerDesktopLinuxEngine` | Docker Desktop apagado | Abrirlo y esperar "Engine running" |
| `Login failed for user 'sa'` + `Cannot open database "a2d_sm"` | La base aún no existe | Ejecutar el `CREATE DATABASE` de la sección 4 |
| `Login failed for user 'sa'` con la base creada | Las contraseñas no coinciden, o el volumen se creó con otra contraseña | Igualar ambos `.env`; si el volumen tiene otra, `docker compose down -v` y repetir la sección 4 (borra los datos) |
| `Conflict. The container name "/a2d_sqlserver" is already in use` | Hay un contenedor viejo con ese nombre | `docker rm -f a2d_sqlserver` y `docker compose up -d` |
| `No such container: a2d_sqlserver` | El contenedor no está creado | `docker compose up -d` desde la raíz |
| `port is already allocated` (1433) | Otro SQL Server usa el puerto | Detener el otro servicio o cambiar el puerto en `docker-compose.yml` |
| El contenedor se cae al iniciar | Contraseña que no cumple la complejidad | Usar una más fuerte y recrear (`docker compose down -v`) |

> La contraseña de `sa` se fija solo la **primera vez** que arranca un volumen vacío. Cambiar el `.env` después no la modifica.

## 9. Qué hay construido hasta ahora

- API base con `GET /health`.
- Configuración por variables de entorno (`app/core/config.py`).
- Conexión a SQL Server con SQLAlchemy (`app/core/database.py`).
- Utilidades de seguridad: hash de contraseñas y JWT (`app/core/security.py`) y validación de RUT (`app/core/validators.py`).

En construcción: Épica 1 (autenticación, usuarios y roles). El router de autenticación está desactivado en `main.py` hasta que exista.
