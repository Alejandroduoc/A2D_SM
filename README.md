# A2D_SM

**Nombre del proyecto:** A2D SM — Sistema de trazabilidad para planta procesadora de fruta

**Descripción:** Sistema web de trazabilidad que moderniza y complementa el
sistema legado de una planta procesadora de fruta, permitiendo gestionar la
recepción de fruta y el procesamiento de tarjas de forma segura, mantenible y
auditable. Proyecto de Título APT122 — Duoc UC, Ingeniería Informática.

---

## Tabla de contenidos

- [Descripción](#descripción)
- [Tecnologías utilizadas](#tecnologías-utilizadas)
- [Instrucciones para ejecutar el proyecto localmente](#instrucciones-para-ejecutar-el-proyecto-localmente)
- [Integrantes del equipo](#integrantes-del-equipo)
- [Metodología de trabajo](#metodología-de-trabajo)
- [Arquitectura de la solución](#arquitectura-de-la-solución)
- [Estructura del repositorio](#estructura-del-repositorio)

## Descripción

**A2D SM** es un sistema de trazabilidad diseñado para una planta procesadora de
fruta. Su objetivo es modernizar y complementar el sistema legado actual,
permitiendo gestionar el flujo de recepción y procesamiento de tarjas de fruta
de manera más segura, mantenible y auditable.

### Problema que resuelve

La planta depende hoy de un sistema antiguo difícil de mantener. A2D SM entrega
una plataforma moderna que permite controlar la recepción de fruta, el
procesamiento de tarjas, la gestión de catálogos y la auditoría de cambios,
asegurando la disponibilidad y confiabilidad de la información.

### Usuarios objetivo

| Rol | Necesidad principal |
| --- | --- |
| Operador de recepción | Registrar el ingreso de fruta y sus tarjas |
| Operador de proceso | Consultar y actualizar el estado del procesamiento |
| Administrador | Gestionar catálogos, usuarios y parámetros del sistema |
| Gerencia  | Consultar trazabilidad e historial de cambios |

### Alcance funcional

- Recepción de fruta.
- Procesamiento de tarjas.
- Gestión de catálogos.
- Auditoría de cambios.

## Tecnologías utilizadas

| Categoría | Tecnología |
| --- | --- |
| Lenguajes | Python (backend), JavaScript (frontend) |
| Frameworks | FastAPI, SQLAlchemy 2.0 + Alembic, React (Vite) + Tailwind |
| Base de datos | Microsoft SQL Server 2022 |
| Autenticación | JWT (token de acceso de 30 minutos; renovación con *refresh token* planificada) |
| Infraestructura | Docker + Docker Compose |


## Instrucciones para ejecutar el proyecto localmente

Todo el entorno corre en Docker: no hace falta instalar Python ni SQL Server.
Guía completa (variables de entorno, creación de la base, Alembic y errores
frecuentes): [docs/Como_Levantar_El_Proyecto.md](docs/Como_Levantar_El_Proyecto.md).

**Requisitos:** Docker Desktop y Git.

1. Clonar el repositorio y entrar a la carpeta:

   ```powershell
   git clone <url-del-repositorio>
   cd A2D_SM
   ```

2. Crear los archivos `.env` a partir de los `.env.example` (en `sistema/` y en
   `sistema/backend/`) y completar las contraseñas.

3. Desde la carpeta `sistema/`, levantar los contenedores (SQL Server + backend FastAPI):

   ```powershell
   cd sistema
   docker compose up -d --build
   ```

4. Solo la primera vez, cuando la base esté "healthy" (`docker compose ps`),
   crear la base de datos:

   ```powershell
   docker exec a2d_sqlserver /opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -P "<tu-contraseña>" -Q "CREATE DATABASE a2d_sm"
   ```

5. Crear las tablas aplicando las migraciones de Alembic (la primera vez y cada
   vez que lleguen migraciones nuevas):

   ```powershell
   docker compose exec backend alembic upgrade head
   ```

6. Solo la primera vez, crear el primer administrador (el script pide el nombre
   de usuario, el nombre completo y la contraseña por teclado):

   ```powershell
   docker compose exec backend python -m app.scripts.crear_admin
   ```

7. Abrir el frontend en http://localhost:5173 e iniciar sesión con ese
   administrador. La API responde en http://localhost:8000/health y su
   documentación está en http://localhost:8000/docs.

## Integrantes del equipo

| Integrante | Rol |
| --- | --- |
| Alejandro Rodríguez | Project Manager |
| Diego Carrillo | Analista de Base de Datos |
| Angelo Galindo | QA |

## Metodología de trabajo

El equipo trabaja con **Scrum**, organizando el desarrollo en sprints con
ceremonias de planificación, revisión y retrospectiva.

## Arquitectura de la solución

### Decisiones de arquitectura

| Decisión | Elección | Motivo |
|---|---|---|
| Backend | **Python + FastAPI** | Tipado con Pydantic, docs OpenAPI automáticas. |
| ORM / Migraciones | SQLAlchemy 2.0 + Alembic | Estándar de facto en el ecosistema FastAPI. |
| Base de datos | **SQL Server** (se mantiene) | Es el motor que ya usa la planta y que el equipo conoce. La migración de los datos del sistema legado está fuera del alcance del PMV; el modelo nuevo se diseñó desde cero, con claves foráneas y transacciones que el legado no tenía. |
| Frontend | **React (Vite) + Tailwind** | SPA desacoplada, consistente con el backend REST. |
| Autenticación | JWT (token de acceso de 30 minutos) | Sin sesiones server-side acopladas a un solo servidor. La renovación con *refresh token* (`POST /auth/refresh`) queda para una etapa posterior: al vencer el token se vuelve a iniciar sesión. |
| Infraestructura | Docker + docker-compose | Portable y reproducible entre miembros del equipo. |

**Principio no negociable:** ningún cliente (browser) accede directo a la base
de datos. Todo pasa por la API. Esta es la corrección central del problema de
seguridad del sistema legacy (VB.NET 2008 WinForms + PHP, con SQL injection y
conexión directa cliente-BD verificadas en el código fuente real —
`Backup/socradex/Form4.vb`).

### Arquitectura en capas

Toda petición sigue el mismo camino, sin excepciones:

```
Frontend (React)  →  Router (FastAPI)  →  Service (lógica de negocio)  →  Model (SQLAlchemy)  →  Base de datos
```

## Estructura del repositorio

```text
A2D_SM/
├── README.md
├── docs/                         # Documentación técnica
├── sistema/
│   ├── .gitignore                # Archivos que no se suben a git (.env, cachés, etc.)
│   ├── .env.example              # Contraseña de SQL Server (copiar como .env)
│   ├── docker-compose.yml        # Entorno de desarrollo
│   ├── docker-compose.prod.yml   # Ajustes para producción
│   ├── backend/                  # API FastAPI (app/, migrations/, tests/)
│   └── frontend/                 # Interfaz React/Vite + Tailwind
├── Fase 1/
│   ├── Evidencias Grupales/      # Entregables desarrollados por el equipo
│   └── Evidencias Individuales/  # Autoevaluaciones y diarios de cada integrante
└── Fase 2/
    ├── Actas/                    # Actas de control de avance (evidencia de retrospectiva)
    ├── Evidencias Grupales/      # Guía 2.4 (desarrollo) e informe final 2.6
    ├── Evidencias Individuales/  # Diarios de reflexión 2.1 de cada integrante
    └── Evidencias Proyecto (version Agil)/  # Product Vision, Product Backlog, Sprint Backlog,
                                             # Definition of Done y Documento de Diseño
```
