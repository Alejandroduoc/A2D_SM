# Resultados de pruebas — Seguridad, E2, E3 y E4

Resumen al 08/11/2026 de las pruebas del producto mínimo viable después de la
Épica 1 (las actas de E1 están en esta misma carpeta). Todas las pruebas se
ejecutaron en Docker, con el entorno descrito en `docs/Como_Levantar_El_Proyecto.md`.
El detalle de cada caso (pasos, valores esperados y obtenidos) está en el
registro interno del equipo.

**Convenciones:** ✅ pasó; ⏳ pendiente. "Verificación independiente" significa
que la repitió el responsable de QA (Angelo Galindo) en su propio equipo.

## 1. Pruebas automáticas (regresión completa, 08/11/2026)

12 suites del backend, ejecutadas una por una: **2.521 comprobaciones, 0 fallas**.
Frontend: 11 pruebas, 0 fallas. Migraciones en `c83e321c741d (head)` y
`alembic check` sin operaciones pendientes. Comandos y cifras por suite en
`docs/Como_Levantar_El_Proyecto.md`, sección 10.3.

## 2. Refuerzo de seguridad (25/10/2026)

Límite de intentos de inicio de sesión (`429`), renovación del token
(`/auth/refresh`), cambio de contraseña, auditoría de usuarios sin la contraseña,
contenedores sin privilegios y nginx de producción.

| Bloque | Casos | Resultado |
| --- | --- | --- |
| Prueba automática y regresión | 15 | ✅ |
| Imagen de producción (nginx) | 6 | ✅ |
| Regresión en el equipo de QA (31/10) | 7 | ✅ |
| Casos manuales, incluido el menú por rol de HU01 y HU02 (31/10) | 21 | ✅ |

## 3. E2 · Maestros core (cerrada el 01/11/2026)

| Historia | Casos | Resultado | Verificación independiente |
| --- | --- | --- | --- |
| HU21 Auditoría automática (migración y servicio) | 18 | ✅ | Sí (migración, 31/10) |
| HU07 Productores | 15 | ✅ | Sí (31/10) |
| HU08 Especies y variedades | 27 | ✅ | Sí (31/10) |
| HU09 Calidades y sistemas productivos | 23 | ✅ | Sí (31/10) |
| HU10 Tipos de bandeja y embalajes | 16 | ✅ | — |
| HU11 Listas de catálogo para recepción | 10 | ✅ | — |

## 4. E3 · Recepción de tarjas

| Historia o bloque | Casos | Resultado |
| --- | --- | --- |
| Migraciones (código del productor, tarjas y movimientos de bandeja) | 4 | ✅ |
| HU12 a HU14: registro, numeración y kilos netos (pantalla y casos de cobertura) | 19 | ✅ |
| Correcciones de la revisión del 02/11 | 12 | ✅ |
| HU17 Consultar tarjas | 10 | ✅ |
| HU16 Imprimir la tarja | 12 | ✅ |
| HU15 Saldo de bandejas | 10 | ✅ |
| HU24 Anular una tarja | 10 | ✅ |

Verificación independiente de E3 y E4: 03/11 al 05/11/2026, 49 casos ✅ (ver
sección 6).

## 5. E4 · Procesamiento y auditoría

| Historia | Casos | Resultado |
| --- | --- | --- |
| HU18 Procesar tarjas (criterios, kilos pendientes, merma, edición, comprobante, efecto sobre E3, seguridad y pantalla) | 57 | ✅ |
| HU19 Rendimiento y merma | 12 | ✅ |
| HU22 Bitácora de auditoría (API y pantalla) | 13 | ✅ |
| HU23 Trazabilidad de una tarja | 9 | ✅ |
| HU25 Anular un proceso | 12 | ✅ |
| HU20 Corregir una tarja | Ver abajo | ✅ / ⏳ |

**HU20 (corregida el 08/11/2026):**

- Pruebas automáticas de la corrección (`probar_tarjas`): incluyen el cambio de tipo de bandeja con su tara, la corrección sin cambios, las fechas, los catálogos desactivados, el largo del motivo y procesos reales que bloquean y luego liberan la tarja. Todas ✅.
- Recorrido automatizado en navegador (Chromium, a 1280 y 390 px): 18 de 18 casos ✅.
- ⏳ Verificación independiente en Edge (casos H20-1 a H20-20) e impresión física en papel de una tarja nueva y de una corregida.

**Cambios de interfaz del 08/11/2026, probados en navegador:**

- Los datos de cada evento de la bitácora se ven en una ventana emergente: 7 de 7 ✅.
- En Mantenedores, los botones ya no se mueven al activar o desactivar: 6 de 6 ✅.
- Hojas impresas con el título "Socradex" y sin el encabezado ni el pie del navegador: título y márgenes ✅; ⏳ confirmación en el diálogo de impresión de Edge.

## 6. Verificación independiente de E3 y E4 (03/11 al 05/11/2026)

49 casos ✅, en el equipo de QA: pruebas automáticas, procesamiento (HU18,
HU19, HU23 y HU25), bitácora (HU22), impresión guardada como PDF y bloque 2 de
E3. ⏳ Un ajuste visual pendiente en Mantenedores ("Ver variedades", R2), en
curso.

## 7. Observaciones aceptadas

| Observación | Decisión |
| --- | --- |
| Quitar una tarja de un proceso en edición borra su fila de detalle | Intencional (decisión del 03/11/2026): la auditoría conserva la fila completa. La regla de no borrar se aplica a las anulaciones |
| Los tokens de sesión se guardan en `localStorage` | Funciona para el PMV. Para producción se recomienda evaluar cookies `HttpOnly` |
| La revocación de tokens al cambiar la contraseña no está implementada | Riesgo aceptado para el PMV (decisión del 31/10/2026) |
| `SECRET_KEY`, HTTPS y un usuario propio de SQL Server | Se configuran antes de desplegar (`docs/Como_Levantar_El_Proyecto.md`, sección 8) |
