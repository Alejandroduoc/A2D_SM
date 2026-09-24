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
| Personal de gestión de planta | Consultar trazabilidad e historial de cambios |

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
| Autenticación | JWT (access + refresh) |
| Infraestructura | Docker + Docker Compose |
| Cloud | Por definir |

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

2. Crear los archivos `.env` a partir de los `.env.example` (en la raíz y en
   `sistema/backend/`) y completar las contraseñas.

3. Levantar los contenedores (SQL Server + backend FastAPI):

   ```powershell
   docker compose up -d --build
   ```

4. Solo la primera vez, cuando la base esté "healthy" (`docker compose ps`),
   crear la base de datos:

   ```powershell
   docker exec a2d_sqlserver /opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -P "<tu-contraseña>" -Q "CREATE DATABASE a2d_sm"
   ```

5. Abrir la API en http://localhost:8000/health y la documentación en
   http://localhost:8000/docs

> El frontend (React) todavía no está creado.

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
| Base de datos | **SQL Server** (se mantiene) | Migración de datos motor-a-mismo-motor es más simple; se reutiliza lógica de ~30 stored procedures existentes del sistema legacy en vez de reescribirla de cero. |
| Frontend | **React (Vite) + Tailwind** | SPA desacoplada, consistente con el backend REST. |
| Autenticación | JWT (access + refresh) | Sin sesiones server-side acopladas a un solo servidor. |
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
├── docker-compose.yml
├── docker-compose.prod.yml
├── docs/                         # Documentación técnica
├── sistema/
│   └── backend/                  # API FastAPI (app/, migrations/, tests/)
└── Fase 1/
    ├── Evidencias Grupales/      # Entregables desarrollados por el equipo
    └── Evidencias Individuales/  # Autoevaluaciones y diarios de cada integrante
```
