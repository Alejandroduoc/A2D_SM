# Cómo levantar el proyecto (backend + SQL Server, todo en Docker)

Guía para dejar funcionando en tu PC lo que hay construido hasta ahora: la API (FastAPI) y la base de datos SQL Server. **Todo corre dentro de Docker**: no necesitas instalar Python, entornos virtuales ni drivers de SQL Server en tu PC.

## 1. Requisitos

| Herramienta | Notas |
| --- | --- |
| Docker Desktop | Debe estar abierto y mostrar "Engine running". |
| Git | Para clonar el repositorio. |

## 2. Arquitectura del entorno

```text
Tu PC (Docker Desktop)
├── contenedor "a2d_sqlserver"  SQL Server 2022, puerto 1433  ← base de datos
└── contenedor "a2d_backend"    API FastAPI, puerto 8000      ← backend (Python + driver ODBC ya incluidos)
```

Son dos contenedores separados. Los datos de la base se guardan en un volumen de Docker; el código del backend (`sistema/backend/`) se comparte con el contenedor, así que lo que edites se aplica al instante. Todo se define en `docker-compose.yml` (raíz); la imagen del backend, en `sistema/backend/Dockerfile`. Ambos archivos están comentados línea por línea.

## 3. Configuración (solo la primera vez)

Hay **dos** archivos `.env`. Ninguno se sube a git; cada integrante crea los suyos copiando los `.env.example`.

**3.1. `A2D_SM/.env`** (raíz):

```env
MSSQL_SA_PASSWORD=<tu-contraseña>
```

**3.2. `sistema/backend/.env`:**

```env
SECRET_KEY=<una-clave-larga-y-aleatoria>
```

Reglas importantes:

- La contraseña de SQL Server exige mínimo 8 caracteres con mayúscula, minúscula, número y símbolo; si no, el contenedor se cae al iniciar.
- Evita `@ : / ? #` en la contraseña: rompen la URL de conexión.
- **No hay que escribir `DATABASE_URL`:** el `docker-compose.yml` la arma solo (servidor `db`, driver 18) usando `MSSQL_SA_PASSWORD`. Así la contraseña se escribe una sola vez. Si quedó una línea `DATABASE_URL` en tu `sistema/backend/.env`, bórrala: no hace daño (el compose tiene prioridad) pero confunde.

> **¿Cómo llega la URL al backend?** `MSSQL_SA_PASSWORD` (`.env` de la raíz) → `docker-compose.yml` arma `DATABASE_URL` (`...@db:1433/a2d_sm...`) y la entrega al contenedor como variable de entorno → `app/core/config.py` la lee en `settings.database_url` → `app/core/database.py` crea la conexión. `db` es el nombre del servicio de SQL Server dentro de la red de Docker (no `localhost`). Para ver qué recibió, sin mostrar la contraseña: `docker compose exec backend python -c "from app.core.config import settings; print(settings.database_url.split('@')[1])"`.
- Si falta `SECRET_KEY` o `MSSQL_SA_PASSWORD`, la API **no arranca** (error `Field required`). Es intencional: no hay valores por defecto.

## 4. Levantar el proyecto

Distinguir tres cosas, porque se hacen en momentos distintos:

| Qué | Cuándo se hace | Cómo |
| --- | --- | --- |
| **Levantar los contenedores** (SQL Server y API) | Cada vez que enciendes Docker | `docker compose up -d` |
| **Crear la base de datos `a2d_sm`** (la "carpeta" vacía dentro del motor) | **Una sola vez**, o de nuevo si se borra el volumen | Sección 4.2 |
| **Crear las tablas** (`usuarios`, etc.) | Al aplicar las migraciones de Alembic | Sección 6 |

> SQL Server, a diferencia de otros motores, **no crea la base de datos por sí solo**: arranca con las bases del sistema (`master`, `tempdb`...) pero no con `a2d_sm`. Sin ese paso, la API falla con `Cannot open database "a2d_sm"`. Las tablas no las crea ese paso; las crean las migraciones.

### 4.1. Levantar los contenedores

Desde la raíz del repositorio (`A2D_SM/`):

```powershell
docker compose up -d --build
docker compose ps
```

- `--build` construye la imagen del backend. La primera vez tarda unos minutos (descarga SQL Server, ~1.5 GB, e instala el driver); después usa la caché.
- Espera a que `a2d_sqlserver` diga `healthy` y `a2d_backend` diga `Up`. El backend espera a que la base esté lista antes de arrancar.
- **No sigas al paso 4.2 hasta que la base diga `healthy`**: si el motor aún está arrancando, el comando falla.

### 4.2. Crear la base `a2d_sm` (solo la primera vez)

```powershell
docker exec a2d_sqlserver /opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -P "<tu-contraseña>" -Q "CREATE DATABASE a2d_sm"
```

- Usa la contraseña que pusiste en `A2D_SM/.env` (`MSSQL_SA_PASSWORD`).
- Si funciona, **no imprime nada** (es normal).
- Para comprobar que existe:

  ```powershell
  docker exec a2d_sqlserver /opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -P "<tu-contraseña>" -Q "SELECT name FROM sys.databases"
  ```

  En la lista debe aparecer `a2d_sm`.
- Si ejecutas el comando cuando la base ya existe, da un error de "database already exists"; es inofensivo.
- Los datos se guardan en un volumen de Docker, así que **`docker compose stop`, `down` o reiniciar el PC no borran la base**. Solo hay que repetir este paso si borras el volumen (`docker compose down -v`).

### 4.3. Si necesitas cambiar la contraseña de SQL Server

La contraseña de `sa` se fija **solo la primera vez** que arranca un volumen vacío. Editar el `.env` después no la cambia: el contenedor sigue con la anterior y la API da `Login failed for user 'sa'`. Mientras la base no tenga datos que quieras conservar:

1. Actualiza `MSSQL_SA_PASSWORD` en `A2D_SM/.env`.
2. Recrea el volumen (**esto borra todos los datos**):

   ```powershell
   docker compose down -v
   docker compose up -d
   ```
3. Espera `healthy` y repite el paso 4.2 con la contraseña nueva.

## 5. Verificar que todo funciona

- `http://localhost:8000/health` → `{"status": "ok"}`
- `http://localhost:8000/docs` → documentación interactiva de la API.
- Conexión del backend a la base (desde dentro del contenedor):

  ```powershell
  docker exec a2d_backend python -c "from app.core.database import engine; print(engine.connect().exec_driver_sql('SELECT DB_NAME()').scalar())"
  ```

  Debe imprimir `a2d_sm`.

## 6. Tablas de la base de datos (Alembic) y comandos dentro del backend

Como Python vive dentro del contenedor, los comandos se ejecutan ahí con `docker compose exec backend ...` (desde la raíz del repositorio). Los archivos que generen (por ejemplo las migraciones) **quedan guardados en tu carpeta `sistema/backend/`**, porque esa carpeta está compartida con el contenedor.

**Alembic** es la herramienta que crea y modifica las tablas de SQL Server a partir de los modelos de Python (`app/models/`). Cada cambio queda guardado como un archivo de *migración* en `sistema/backend/migrations/versions/`, que se sube a git para que todo el equipo tenga las mismas tablas. **No se usa `Base.metadata.create_all()`** para crear tablas.

Hay que distinguir dos situaciones:

| Situación | Qué hacer |
| --- | --- |
| **Configurar Alembic por primera vez en el proyecto** (lo hace **una sola persona**, una vez) | Sección 6.1 y 6.2 |
| **Ya existe la carpeta `migrations/` en el repositorio** (cualquier integrante que clona o actualiza el proyecto) | Solo la sección 6.3: `alembic upgrade head` |

> Requisito previo: el stack levantado (`docker compose ps` con `a2d_sqlserver` en `healthy` y `a2d_backend` en `Up`) y la base `a2d_sm` ya creada (sección 4.2). Alembic crea las **tablas**, no la base de datos.

### 6.1. Configurar Alembic (solo la primera vez en el proyecto)

**Paso 1 — Crear los `__init__.py`.** Archivos **vacíos**, para que Python trate las carpetas como paquetes:

```text
sistema/backend/app/__init__.py
sistema/backend/app/core/__init__.py
sistema/backend/app/models/__init__.py
```

**Paso 2 — Inicializar Alembic:**

```powershell
docker compose exec backend alembic init migrations
```

*Comprueba* que aparecieron `sistema/backend/alembic.ini` y la carpeta `sistema/backend/migrations/` (con `env.py`, `script.py.mako` y `versions/`).

**Paso 3 — Vaciar la URL de `alembic.ini`.** Abre `sistema/backend/alembic.ini`, busca esta línea:

```ini
sqlalchemy.url = driver://user:pass@localhost/dbname
```

y déjala así (vacía):

```ini
sqlalchemy.url =
```

*Por qué:* la URL real se toma de la configuración de la app (`settings`), que ya la recibe desde el `docker-compose.yml`. Así no hay contraseñas en un archivo que se sube a git.

**Paso 4 — Configurar `sistema/backend/migrations/env.py`.** Haz tres cambios:

1. Debajo de los imports que ya trae el archivo, agrega:

   ```python
   from app.core.config import settings
   from app.core.database import Base
   from app.models import usuario  # noqa: F401  (importarlo registra las tablas en Base.metadata)
   ```

   Cada modelo nuevo que se cree en el futuro debe importarse aquí también; si no, Alembic no lo ve y la migración sale **vacía** sin dar error.
2. Justo después de la línea `config = context.config`, agrega:

   ```python
   config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
   ```

   (El `replace` evita que un `%` dentro de la contraseña rompa el archivo de configuración.)
3. Busca `target_metadata = None` y cámbialo por:

   ```python
   target_metadata = Base.metadata
   ```

*Comprueba* que Alembic arranca sin errores:

```powershell
docker compose exec backend alembic current
```

(No imprime versiones todavía; lo importante es que no muestre un error.)

### 6.2. Crear y aplicar la primera migración

**Paso 5 — Generar la migración.** Alembic compara los modelos con la base y escribe lo que falta:

```powershell
docker compose exec backend alembic revision --autogenerate -m "esquema inicial"
```

Se crea un archivo nuevo en `sistema/backend/migrations/versions/` (con un nombre tipo `abc123_esquema_inicial.py`).

**Paso 6 — Revisarla antes de aplicarla.** Ábrela. En la función `upgrade()` debe haber:

- `op.create_table('usuarios', ...)` con las columnas `id`, `nombre_usuario`, `nombre_completo`, `password_hash`, `activo` y `creado_en`;
- `op.create_table('usuario_roles', ...)` con clave primaria compuesta `(usuario_id, rol)` y clave foránea a `usuarios.id`;
- un índice único sobre `nombre_usuario`.

Si `upgrade()` solo contiene `pass`, la migración está vacía: falta el import del modelo en `env.py` (paso 4). Borra el archivo generado y repite el paso 5.

**Paso 7 — Aplicarla:**

```powershell
docker compose exec backend alembic upgrade head
```

**Paso 8 — Comprobar que las tablas existen** (usa la contraseña de `A2D_SM/.env`):

```powershell
docker exec a2d_sqlserver /opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -P "<tu-contraseña>" -d a2d_sm -Q "SELECT name FROM sys.tables"
```

Deben aparecer `usuarios`, `usuario_roles` y `alembic_version` (esta última la crea Alembic para saber qué migración está aplicada).

**Paso 9 — (Opcional) Probar que la migración es reversible:**

```powershell
docker compose exec backend alembic downgrade base    # borra las tablas
docker compose exec backend alembic upgrade head      # las vuelve a crear
```

**Paso 10 — Subir a git** `alembic.ini`, `migrations/env.py`, `migrations/script.py.mako` y el archivo de `migrations/versions/`. Así el resto del equipo no repite los pasos 1 a 6.

### 6.3. Trabajo diario con migraciones

**Si te bajas el proyecto (o alguien subió una migración nueva):** solo aplicas lo que falte. No se ejecuta `alembic init` ni `revision`:

```powershell
docker compose exec backend alembic upgrade head
```

**Si cambias un modelo** (una columna nueva, una tabla nueva):

```powershell
docker compose exec backend alembic revision --autogenerate -m "descripcion corta del cambio"
# revisar el archivo generado en migrations/versions/
docker compose exec backend alembic upgrade head
```

Comandos útiles:

| Comando | Para qué |
| --- | --- |
| `docker compose exec backend alembic current` | Ver qué migración tiene aplicada la base |
| `docker compose exec backend alembic history` | Ver la lista de migraciones |
| `docker compose exec backend alembic downgrade -1` | Deshacer la última migración |
| `docker compose exec backend alembic upgrade head` | Aplicar todas las pendientes |

> Nunca edites una migración que ya subiste a git y aplicaron otros: crea una nueva.

### 6.4. Otros comandos dentro del contenedor

```powershell
docker compose exec backend python -m app.scripts.crear_admin    # ejemplo: script del primer administrador
docker compose exec backend bash                                 # terminal dentro del contenedor
```

## 7. Uso diario

Una vez creada la base (sección 4.2), el día a día es solo abrir Docker Desktop y, desde la raíz:

```powershell
docker compose up -d
```

**No hay que volver a crear la base de datos.** Si al actualizar el proyecto llegaron migraciones nuevas, aplícalas con `docker compose exec backend alembic upgrade head` (sección 6.3). El código se recarga solo al guardar. Solo hay que reconstruir la imagen (`docker compose up -d --build backend`) si cambias `requirements.txt` o el `Dockerfile`.

| Acción | Comando (desde la raíz) |
| --- | --- |
| Ver estado de los contenedores | `docker compose ps` |
| Ver logs del backend en vivo (Ctrl+C para salir) | `docker compose logs -f backend` |
| Ver logs de SQL Server | `docker compose logs db` |
| Apagar solo el backend | `docker compose stop backend` |
| Apagar todo sin perder datos | `docker compose stop` |
| Encender de nuevo | `docker compose start` |
| Reconstruir el backend tras cambiar `requirements.txt` o el `Dockerfile` | `docker compose up -d --build backend` |
| Eliminar los contenedores (conserva los datos) | `docker compose down` |
| Borrar contenedores **y todos los datos** | `docker compose down -v` |

## 8. Producción

Todo lo anterior es el entorno de **desarrollo**. Para producción existe `docker-compose.prod.yml`, que se combina con el compose base y solo cambia lo necesario: quita la carpeta compartida (corre el código de la imagen), quita `--reload`, deja de publicar el puerto de SQL Server y reinicia los contenedores si se caen.

```powershell
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.prod.yml config   # ver el resultado sin levantar nada
```

**Aún no está listo para desplegar**: faltan el proxy con HTTPS, un usuario de SQL Server distinto de `sa`, respaldos, contraseñas privadas, restringir CORS y apagar `echo=True` en `database.py`. La lista completa, con responsables propuestos, está en `Avances_para_el_equipo_2026-09-19.md`, sección 8. **No uses este archivo en un servidor real hasta resolverlas.**

## 9. Problemas frecuentes

| Síntoma | Causa | Solución |
| --- | --- | --- |
| `error during connect ... dockerDesktopLinuxEngine` | Docker Desktop apagado | Abrirlo y esperar "Engine running" |
| `Field required` en los logs del backend | Falta `sistema/backend/.env` o `SECRET_KEY`, o falta `MSSQL_SA_PASSWORD` en el `.env` de la raíz | Crearlos desde los `.env.example` |
| `Login failed for user 'sa'` + `Cannot open database "a2d_sm"` | La base aún no existe | Ejecutar el `CREATE DATABASE` de la sección 4.2 |
| `Login failed for user 'sa'` con la base creada | El volumen se creó con otra contraseña | Sección 4.3 (`docker compose down -v`; borra los datos) |
| `a2d_backend` se reinicia o falla al conectar | La base no existe o la contraseña no es la del volumen | `docker compose logs backend`; revisar secciones 4.2 y 4.3 |
| `Conflict. The container name "/a2d_sqlserver" is already in use` | Hay un contenedor viejo con ese nombre | `docker rm -f a2d_sqlserver` y `docker compose up -d` |
| `No such container: a2d_sqlserver` (o `a2d_backend`) | Los contenedores no están creados | `docker compose up -d` desde la raíz |
| `port is already allocated` (1433) | Otro SQL Server usa el puerto | Detener el otro servicio o cambiar el puerto en `docker-compose.yml` |
| `port is already allocated` (8000) | Otro programa usa el puerto 8000 | Cerrarlo o cambiar el puerto en `docker-compose.yml` |
| Cambié `requirements.txt` y no se ve el paquete nuevo | La imagen no se reconstruyó | `docker compose up -d --build backend` |
| El contenedor de SQL Server se cae al iniciar | Contraseña que no cumple la complejidad | Usar una más fuerte y recrear (`docker compose down -v`) |
| `alembic revision` genera una migración vacía (solo `pass`) | El modelo no está importado en `migrations/env.py` | Agregar `from app.models import usuario` (sección 6.1, paso 4), borrar la migración vacía y repetir |
| `ModuleNotFoundError: No module named 'app'` al correr Alembic | Faltan los `__init__.py` o se ejecutó fuera del contenedor | Crear los `__init__.py` (sección 6.1, paso 1) y usar `docker compose exec backend alembic ...` |
| `Target database is not up to date` | Hay migraciones sin aplicar | `docker compose exec backend alembic upgrade head` |
| `Can't locate revision ...` | La base tiene una versión que no existe en `migrations/versions/` (por ejemplo tras borrar migraciones o cambiar de rama) | Recrear la base (sección 4.3) o pedir la migración faltante al equipo |
| `There is already an object named 'usuarios'` al aplicar | Las tablas ya existían (creadas fuera de Alembic) | Borrar las tablas o recrear la base (sección 4.3) y volver a aplicar |
| El editor marca imports en rojo (sqlalchemy, fastapi...) | Tu PC no tiene esos paquetes instalados (solo están en el contenedor) | No afecta la ejecución; es solo el resaltado del editor |

## 10. Qué hay construido hasta ahora

- API base con `GET /health`.
- Configuración por variables de entorno (`app/core/config.py`).
- Conexión a SQL Server con SQLAlchemy (`app/core/database.py`).
- Utilidades de seguridad: hash de contraseñas y JWT (`app/core/security.py`) y validación de RUT (`app/core/validators.py`).
- Modelo de usuarios y roles (`app/models/usuario.py`).

En construcción: Épica 1 (autenticación, usuarios y roles). Las tablas aún no se crean en la base: falta configurar Alembic. El router de autenticación está desactivado en `main.py` hasta que exista.
