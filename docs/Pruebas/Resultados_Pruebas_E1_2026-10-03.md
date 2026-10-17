# Resultados de pruebas E1 - 2026-10-03

Equipo: Alejandro (backend), Diego (base de datos), Angelo (QA)

## Entorno

| Verificacion | Resultado |
| --- | --- |
| Comando | `docker compose up -d --build` desde `A2D_SM/sistema/` |
| Backend | `a2d_backend` en estado `healthy` |
| SQL Server | `a2d_sqlserver` en estado `healthy` |
| Alembic | `5e84fd3d65d7 (head)` |
| Pruebas de dependencias | 14 de 14 pasaron (ver nota de corrección) |
| Secretos en logs | No se encontraron contrasenas, tokens ni `password_hash` |

## Pruebas de aceptacion HTTP

Las pruebas se ejecutaron contra `http://localhost:8000` usando usuarios
temporales preparados para QA. Los usuarios temporales se eliminaron al
finalizar. La creacion interactiva del administrador mediante
`app.scripts.crear_admin` queda como comprobacion operativa pendiente, porque
requiere la contrasena real del entorno y no debe registrarse en este archivo.

| # | Peticion o caso | Esperado | Obtenido | Estado |
| --- | --- | --- | --- | --- |
| 1 | `GET /health` | `200` | `200` | ✅ |
| 2 | `GET /docs` | `200` y documentacion disponible | `200` | ✅ |
| 3 | Login de administrador activo | `200` con access y refresh token | `200` | ✅ |
| 4 | Login con contrasena incorrecta | `401` | `401` | ✅ |
| 5 | Login de usuario desactivado | Rechazado | `401` | ✅ |
| 6 | `GET /api/v1/auth/me` con token valido | `200` con usuario | `200` | ✅ |
| 7 | `GET /api/v1/auth/me` sin token | `401` | `401` | ✅ |
| 8 | Login de operador | `200` con tokens | `200` | ✅ |
| 9 | Operador consulta `GET /api/v1/auth/usuarios` | `403` | `403` | ✅ |
| 10 | Administrador crea usuario | `201` | `201` | ✅ |
| 11 | Usuario con dos roles | Ambos roles se guardan y devuelven | `operador_proceso, operador_recepcion` | ✅ |
| 12 | Crear usuario repetido | `409` | `409` | ✅ |
| 13 | Administrador intenta desactivarse | `400` | `400` | ✅ |
| 14 | Respuesta de `/me` | No incluye `password_hash` | No incluido | ✅ |
| 15 | Referencias ejecutables a `OPERADOR_BODEGA` | No deben existir | No encontradas en `sistema/backend/` | ✅ |

## Pruebas de dependencias

> **Corrección 2026-10-17:** este acta decía "15 de 15". `tests/probar_deps.py` tiene 14 casos (6 de `get_current_user`, 5 de `require_rol` y 3 de `require_roles`) desde su primera versión (commit `8b6eb5a`); se volvió a ejecutar el 2026-10-17 con resultado 14 OK y 0 FALLA. Las pruebas siempre pasaron; solo estaba mal el conteo.

El comando:

```powershell
docker compose exec backend python -m tests.probar_deps
```

termino con:

```text
RESULTADO: todas las pruebas pasaron
```

## Pruebas complementarias QA

Archivo ejecutado: `Pruebas_Pendientes_E1_2026-10-03.md`.

Se utilizo un administrador temporal `qa_seed_admin`; todos los usuarios
temporales con prefijo `qa_` fueron eliminados al terminar.

| Caso | Esperado | Obtenido | Estado |
| --- | --- | --- | --- |
| P0 Login del administrador | `200` | `200` | ✅ |
| P1 POST con roles repetidos | `201`, roles unicos | `201`, roles unicos | ✅ |
| P2 PUT valido | `200` | `200` | ✅ |
| P3 PUT con `roles: null` | `200`, roles sin cambios | `200`, roles sin cambios | ✅ |
| P4 PUT con `activo: null` | `200`, sigue activo | `200`, sigue activo | ✅ |
| P5 PUT con roles repetidos | `200`, rol unico | `200`, rol unico | ✅ |
| P6 PUT a id inexistente | `404` | `404` | ✅ |
| P7 Crear administrador temporal | `201` | `201` | ✅ |
| P8 Administrador se quita su rol | `400` | `400` | ✅ |
| P9 `/me` despues del rechazo | `200`, sigue administrador | `200`, sigue administrador | ✅ |
| P10 Conserva administrador y agrega gerencia | `200` | `200` | ✅ |
| P11 Administrador se desactiva | `400` | `400` | ✅ |
| P12 Crear usuario gerencia | `201` | `201` | ✅ |
| P13 Login de gerencia | `200` | `200` | ✅ |
| P14 `/me` de gerencia | `200`, rol gerencia | `200`, rol gerencia | ✅ |
| P15 Gerencia lista usuarios | `403` | `403` | ✅ |
| P16 Rol antiguo supervisor | `422` | `422` | ✅ |
| BD | Sin duplicados ni `SUPERVISOR` | Cumplido | ✅ |
| Limpieza | `0` usuarios `qa_` | `0` | ✅ |

Resultado de la bateria: **17 de 17 pruebas P0-P16 pasaron**.

## Resultado final

**E1 funcionalmente aprobada en entorno de desarrollo.**

Antes de iniciar E2 quedan dos tareas documentales:

1. Actualizar `docs/Como_Levantar_El_Proyecto.md` para describir el router,
   los endpoints y la creacion del primer administrador.
2. Registrar este resultado en el historial de avances y realizar el commit
   correspondiente en ambos repositorios.
