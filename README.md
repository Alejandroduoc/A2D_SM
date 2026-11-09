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
| Operador de recepción | Registrar, imprimir, consultar y corregir las tarjas de recepción, y ver el saldo de bandejas de cada productor |
| Operador de proceso | Registrar los procesos de las tarjas (folio, embalaje y cajas), rebajar la merma y consultar el rendimiento |
| Administrador | Gestionar usuarios, productores y catálogos, y anular tarjas y procesos, además de todo lo anterior |
| Gerencia | Consultar la trazabilidad de una tarja y la bitácora de cambios |

### Alcance funcional

El producto mínimo viable (PMV) está **completo al 09/11/2026**, con sus cuatro
épicas:

| Épica | Qué incluye |
| --- | --- |
| E1 · Autenticación y roles | Inicio de sesión con renovación automática, cambio de contraseña, usuarios y menú según el rol (con los grupos desplegables "Recepción" y "Control") |
| E2 · Maestros | Productores, especies y variedades, calidades, sistemas productivos, tipos de bandeja, embalajes y auditoría automática de cada cambio |
| E3 · Recepción de tarjas | Registro de la tarja con numeración automática y kilos netos, impresión, consulta, saldo de bandejas y anulación |
| E4 · Procesamiento y auditoría | Procesos con consumo parcial de tarjas, merma, rendimiento, corrección de tarjas con motivo, trazabilidad, bitácora y anulación de procesos |

Pantallas, roles, migraciones y pruebas de cada épica:
[docs/Como_Levantar_El_Proyecto.md, sección 10](docs/Como_Levantar_El_Proyecto.md#10-qué-hay-construido-pmv-completo-e1-a-e4).

**Fuera del alcance del PMV** (trabajo posterior):

- **La guía de recepción**, que agrupa las tarjas de un productor con los datos
  del transporte. En el sistema legado, la guía es también donde se registran
  las **bandejas que se devuelven al productor**. Por eso, en el PMV el saldo de
  bandejas solo suma las entradas de cada tarja. El modelo de datos ya admite
  movimientos de salida, para cuando se agregue la guía.
- Bodega, despacho y reportes de gestión.
- La migración de los datos del sistema legado.

## Tecnologías utilizadas

| Categoría | Tecnología |
| --- | --- |
| Lenguajes | Python (backend), JavaScript (frontend) |
| Frameworks | FastAPI, SQLAlchemy 2.0 + Alembic, React (Vite) + Tailwind |
| Base de datos | Microsoft SQL Server 2022 |
| Autenticación | JWT (token de acceso de 30 minutos y *refresh token* de 7 días) |
| Infraestructura | Docker + Docker Compose (Node 26 para el frontend; nginx 1.30 en producción) |


## Instrucciones para ejecutar el proyecto localmente

Todo el entorno corre en Docker: no hace falta instalar Python, Node ni SQL Server.
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

3. Desde la carpeta `sistema/`, levantar los contenedores (SQL Server, backend FastAPI y frontend React):

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

### Pruebas

Desde `sistema/`, con los contenedores levantados y **una prueba a la vez**
(comparten la base). Cada prueba del backend trabaja dentro de una transacción
que se revierte, así que no deja datos:

```powershell
docker compose exec backend python -m tests.probar_tarjas
docker compose exec frontend node --test tests/
```

Resultado al 09/11/2026: 12 pruebas del backend con 2.521 comprobaciones y 17
pruebas del frontend, sin fallas. La lista completa de comandos está en
[docs/Como_Levantar_El_Proyecto.md, sección 10.3](docs/Como_Levantar_El_Proyecto.md#103-pruebas-automáticas),
y los resultados por épica en [docs/Pruebas/](docs/Pruebas/).

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
| Autenticación | JWT (token de acceso de 30 minutos y *refresh token* de 7 días) | Sin sesiones server-side acopladas a un solo servidor. Al vencer el token de acceso, el frontend lo renueva en `POST /auth/refresh`, que entrega también un *refresh token* nuevo (rotación); solo si este vence o el usuario fue desactivado se vuelve a iniciar sesión. |
| Infraestructura | Docker + docker-compose | Portable y reproducible entre miembros del equipo. |

**Principio no negociable:** ningún cliente (browser) accede directo a la base
de datos. Todo pasa por la API. Esta es la corrección central del problema de
seguridad del sistema legacy (VB.NET 2008 WinForms + PHP, con SQL injection y
conexión directa cliente-BD verificadas en el código fuente real —
`Backup/socradex/Form4.vb`).

### Arquitectura en capas

Toda petición sigue el mismo camino:

```
Frontend (React)  →  Router (FastAPI)  →  Service (lógica de negocio)  →  Model (SQLAlchemy)  →  Base de datos
```

La única excepción documentada es el inicio de sesión y la renovación de
tokens (router `auth`), que consultan los modelos directamente porque son
operaciones simples de lectura sobre los usuarios. La autorización se consulta siempre
en la base de datos: los roles del token son solo informativos.

### Desarrollo y producción

En desarrollo, el navegador usa el frontend de Vite (puerto 5173) y la API
(puerto 8000). En producción (`docker-compose.prod.yml`), nginx 1.30 entrega el
frontend compilado y reenvía `/api` al backend por la red interna. Solo se
publica el puerto 80: la API y SQL Server quedan dentro de Docker. Antes de
desplegar falta configurar HTTPS, una `SECRET_KEY` propia del servidor y un
usuario de SQL Server distinto de `sa`
([docs/Como_Levantar_El_Proyecto.md, sección 8](docs/Como_Levantar_El_Proyecto.md#8-producción)).

## Estructura del repositorio

```text
A2D_SM/
├── README.md
├── docs/
│   ├── Como_Levantar_El_Proyecto.md  # Guía completa del entorno, producción y lo construido
│   └── Pruebas/                  # Actas de E1 y resultados de seguridad, E2, E3 y E4
├── sistema/
│   ├── .gitignore                # Archivos que no se suben a git (.env, cachés, etc.)
│   ├── .env.example              # Contraseña de SQL Server (copiar como .env)
│   ├── docker-compose.yml        # Entorno de desarrollo
│   ├── docker-compose.prod.yml   # Ajustes para producción (nginx en el puerto 80)
│   ├── backend/                  # API FastAPI (app/, migrations/, tests/)
│   └── frontend/                 # Interfaz React/Vite + Tailwind (src/, tests/, nginx.conf)
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
