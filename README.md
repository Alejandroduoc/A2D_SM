# A2D_SM

> Sistema de trazabilidad para una planta procesadora de fruta.

Proyecto APT122 — Duoc UC

---

## Tabla de contenidos

- [Descripción](#descripción)
- [Problema que resuelve](#problema-que-resuelve)
- [Usuarios objetivo](#usuarios-objetivo)
- [Alcance funcional](#alcance-funcional)
- [Tecnologías utilizadas](#tecnologías-utilizadas)
- [Arquitectura de la solución](#arquitectura-de-la-solución)
- [Metodología de trabajo](#metodología-de-trabajo)
- [Instrucciones para ejecutar el proyecto localmente](#instrucciones-para-ejecutar-el-proyecto-localmente)
- [Estructura del repositorio](#estructura-del-repositorio)
- [Integrantes del equipo](#integrantes-del-equipo)

## Descripción

**A2D SM** es un sistema de trazabilidad diseñado para una planta procesadora de
fruta. Su objetivo es modernizar y complementar el sistema legado actual,
permitiendo gestionar el flujo de recepción y procesamiento de tarjas de fruta
de manera más segura, mantenible y auditable.

## Problema que resuelve

La planta depende hoy de un sistema antiguo difícil de mantener. A2D SM entrega
una plataforma moderna que permite controlar la recepción de fruta, el
procesamiento de tarjas, la gestión de catálogos y la auditoría de cambios,
asegurando la disponibilidad y confiabilidad de la información.

## Usuarios objetivo

| Rol | Necesidad principal |
| --- | --- |
| Operador de recepción | Registrar el ingreso de fruta y sus tarjas |
| Operador de proceso | Consultar y actualizar el estado del procesamiento |
| Administrador | Gestionar catálogos, usuarios y parámetros del sistema |
| Personal de gestión de planta | Consultar trazabilidad e historial de cambios |

## Alcance funcional

- Recepción de fruta.
- Procesamiento de tarjas.
- Gestión de catálogos.
- Auditoría de cambios.

## Tecnologías utilizadas

| Capa | Tecnología |
| --- | --- |
| Lenguaje (backend) | Python |
| Framework (backend) | FastAPI |
| Autenticación | JWT (JSON Web Tokens) |
| Frontend | React |
| Base de datos | Microsoft SQL Server |
| Cloud | Por definir |

## Arquitectura de la solución

## 1. Decisiones de arquitectura

| Decisión | Elección | Motivo |
|---|---|---|
| Backend | **Python + FastAPI** | Tipado con Pydantic, docs OpenAPI automáticas. |
| ORM / Migraciones | SQLAlchemy 2.0 + Alembic | Estándar de facto en el ecosistema FastAPI. |
| Base de datos | **SQL Server** (se mantiene) | Migración de datos motor-a-mismo-motor es más simple; se reutiliza lógica de ~30 stored procedures existentes del sistema legacy en vez de reescribirla de cero. |
| Frontend | **React (Vite) + Tailwind** | SPA desacoplada, consistente con el backend REST. |
| Autenticación | JWT (access + refresh) | Sin sesiones server-side acopladas a un solo servidor. |
| Infraestructura | Docker + docker-compose | Portable y reproducible entre miembros del equipo. |

**Principio no negociable:** ningún cliente (browser) accede directo a la base de datos. Todo pasa por la API. Esta es la corrección central del problema de seguridad del sistema legacy (VB.NET 2008 WinForms + PHP, con SQL injection y conexión directa cliente-BD verificadas en el código fuente real — `Backup/socradex/Form4.vb`).

---

## 2. Arquitectura en capas

Toda petición sigue el mismo camino, sin excepciones:

```
Frontend (React)  →  Router (FastAPI)  →  Service (lógica de negocio)  →  Model (SQLAlchemy)  →  Base de datos
```

## Metodología de trabajo

El equipo trabaja con **Scrum**, organizando el desarrollo en sprints con
ceremonias de planificación, revisión y retrospectiva.

## Instrucciones para ejecutar el proyecto localmente

### Opción 1: Docker (recomendada)

1. Asegúrate de tener Docker Desktop activo.
2. Desde la raíz del proyecto ejecuta:

```bash
docker compose up -d --build
```

3. Abre la aplicación en:

- Frontend: http://localhost:8080
- Backend: http://localhost:8000
- Swagger: http://localhost:8000/docs

4. Para detener los servicios:

```bash
docker compose down
```

### Opción 2: Ejecución manual

1. Crear o activar el entorno virtual:

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Instalar dependencias del backend:

```bash
cd sistema/backend
pip install -r requirement.txt
```

3. Levantar la API:

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

4. En otra terminal, sirve el frontend:

```bash
cd sistema/frontend
python -m http.server 8080
```

5. Abre en el navegador: http://localhost:8080

### Variables de entorno

Crea un archivo `.env` en la carpeta `sistema/backend` con valores de ejemplo:

```env
DATABASE_URL=sqlite:///./a2d_sm.db
SECRET_KEY=dev-secret-key-cambiar-en-produccion
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
PROJECT_NAME=A2D_SM
API_V1_PREFIX=/api/v1
```

> En desarrollo local estas variables bastan para levantar el proyecto. Para producción debes usar claves fuertes y un valor real para la base de datos.

## Estructura del repositorio

```text
A2D_SM/
├── README.md
└── Fase_1/
    ├── Evidencias_Grupales/
    └── Evidencias_Individuales/
        ├── Alejandro_Rodriguez/
        ├── Angelo_Galindo/
        └── Diego_Carrillo/
```

- **`Fase_1/Evidencias_Grupales/`** — entregables desarrollados por el equipo.
- **`Fase_1/Evidencias_Individuales/`** — autoevaluaciones, diarios de reflexión
  y evidencias personales de cada integrante.

## Integrantes del equipo

| Integrante | Rol | Carpeta de evidencias |
| --- | --- | --- |
| Alejandro Rodríguez | Project manager | [Alejandro_Rodriguez](Fase_1/Evidencias_Individuales/Alejandro_Rodriguez/) |
| Diego Carrillo | Analista BD | [Diego_Carrillo](Fase_1/Evidencias_Individuales/Diego_Carrillo/) |
| Angelo Galindo | QA | [Angelo_Galindo](Fase_1/Evidencias_Individuales/Angelo_Galindo/) |
