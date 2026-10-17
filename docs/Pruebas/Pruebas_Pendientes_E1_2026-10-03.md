# A2D_SM — Pruebas pendientes de E1 (PUT, roles repetidos y gerencia)

Creado: 2026-10-03 · Responsable propuesto: Angelo (QA) · Duración estimada: 15 minutos

> Completa el acta `Resultados_Pruebas_E1_2026-10-03.md`. Cubre los casos que esa acta no probó: la edición de usuarios (`PUT`) y los cambios hechos hoy en el código.
>
> - Commit `8fcda74`: `exclude_none` en `actualizar_usuario` y bloqueo para que un administrador no se quite su propio rol.
> - Validador en `schemas/auth.py` que elimina los roles repetidos.
> - Cambio de nombre del rol `supervisor` a `gerencia` (migración `5e84fd3d65d7`).

---

## 0. Antes de empezar

Desde `A2D_SM/sistema/`:

```powershell
docker compose up -d
docker compose exec backend alembic upgrade head
docker compose exec backend alembic current
```

`alembic current` debe mostrar `5e84fd3d65d7 (head)`. Si muestra `4e5b5d399259`, falta el `upgrade` y el rol `gerencia` no existirá en tu base.

Necesitas un administrador que ya exista (el `admin` creado con `crear_admin.py`). Las pruebas **no modifican a ese administrador**: los casos donde un administrador se edita a sí mismo se hacen con un administrador temporal (`qa_admin`), para que un fallo no deje al administrador real sin permisos.

Todos los usuarios temporales empiezan con `qa_` y se borran en el paso 8.

---

## 1. Preparar la sesión de PowerShell

Ejecuta los bloques **en orden y en la misma ventana** de PowerShell, porque comparten variables.

```powershell
# URL base de la API.
$base = "http://localhost:8000/api/v1"

# Llama a la API y devuelve el codigo HTTP y el JSON de la respuesta, tambien
# cuando la API responde un error (4xx). Invoke-WebRequest lanza una excepcion
# en los 4xx; el catch recupera el codigo y el cuerpo de esa respuesta
# (en PowerShell 5.1 el cuerpo del error queda en $_.ErrorDetails.Message).
function Llamar($Metodo, $Ruta, $Cuerpo, $Token) {
    $cabeceras = @{}
    if ($Token) { $cabeceras.Authorization = "Bearer $Token" }
    $parametros = @{
        Method          = $Metodo
        Uri             = "$base$Ruta"
        Headers         = $cabeceras
        ContentType     = "application/json"
        UseBasicParsing = $true
    }
    if ($Cuerpo) { $parametros.Body = ($Cuerpo | ConvertTo-Json -Depth 5) }
    try {
        $r = Invoke-WebRequest @parametros
        return [pscustomobject]@{ Estado = [int]$r.StatusCode; Datos = ($r.Content | ConvertFrom-Json) }
    } catch {
        $resp = $_.Exception.Response
        if (-not $resp) { throw }   # sin respuesta: la API no esta levantada
        $datos = if ($_.ErrorDetails.Message) { $_.ErrorDetails.Message | ConvertFrom-Json } else { $null }
        return [pscustomobject]@{ Estado = [int]$resp.StatusCode; Datos = $datos }
    }
}

# Muestra OK o FALLA comparando el codigo obtenido con el esperado.
function Revisar($Nombre, $Respuesta, $Esperado) {
    $marca = if ($Respuesta.Estado -eq $Esperado) { "OK   " } else { "FALLA" }
    Write-Host ("{0} {1,-55} esperado {2}, obtenido {3}" -f $marca, $Nombre, $Esperado, $Respuesta.Estado)
}

# Contrasena comun de los usuarios temporales de QA (se eliminan al terminar).
# Reemplaza el valor por una clave de prueba de al menos 8 caracteres.
$claveQa = "<clave-de-prueba>"
```

## 2. Iniciar sesión como administrador

La contraseña se pide oculta y no queda en el historial de PowerShell.

```powershell
$usuarioAdmin = "admin"
$claveSegura = Read-Host "Contrasena de $usuarioAdmin" -AsSecureString
$claveAdmin = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($claveSegura))

$r = Llamar POST "/auth/login" @{ nombre_usuario = $usuarioAdmin; password = $claveAdmin }
Revisar "P0 login del administrador" $r 200
$tokenAdmin = $r.Datos.access_token
Remove-Variable claveAdmin, claveSegura
```

Si P0 no da `200`, revisa el usuario y la contraseña antes de seguir.

## 3. Roles repetidos al crear (`POST`)

```powershell
$r = Llamar POST "/auth/usuarios" @{
    nombre_usuario  = "qa_operador"
    nombre_completo = "QA Operador"
    password        = $claveQa
    roles           = @("operador_recepcion", "operador_recepcion", "operador_proceso")
} $tokenAdmin
Revisar "P1 POST con un rol repetido" $r 201
Write-Host "   roles guardados:" ($r.Datos.roles -join ", ")
$idOperador = $r.Datos.id
```

**Esperado:** `201` y roles `operador_recepcion` y `operador_proceso`, cada uno **una sola vez** (el orden en que vuelven puede variar).

## 4. Editar un usuario (`PUT`)

```powershell
# P2: edicion valida de nombre y roles.
$r = Llamar PUT "/auth/usuarios/$idOperador" @{
    nombre_completo = "QA Operador Editado"
    roles           = @("operador_proceso")
} $tokenAdmin
Revisar "P2 PUT valido (nombre y roles)" $r 200
Write-Host "   nombre:" $r.Datos.nombre_completo "| roles:" ($r.Datos.roles -join ", ")

# P3: roles en null no deben borrar los roles actuales.
$r = Llamar PUT "/auth/usuarios/$idOperador" @{ roles = $null } $tokenAdmin
Revisar "P3 PUT con roles null" $r 200
Write-Host "   roles despues de null:" ($r.Datos.roles -join ", ")

# P4: activo en null no debe intentar guardar NULL (antes daba 500).
$r = Llamar PUT "/auth/usuarios/$idOperador" @{ activo = $null } $tokenAdmin
Revisar "P4 PUT con activo null" $r 200
Write-Host "   activo despues de null:" $r.Datos.activo

# P5: roles repetidos al editar.
$r = Llamar PUT "/auth/usuarios/$idOperador" @{ roles = @("gerencia", "gerencia") } $tokenAdmin
Revisar "P5 PUT con un rol repetido" $r 200
Write-Host "   roles guardados:" ($r.Datos.roles -join ", ")

# P6: id que no existe.
$r = Llamar PUT "/auth/usuarios/00000000-0000-0000-0000-000000000000" @{ nombre_completo = "Nadie Nadie" } $tokenAdmin
Revisar "P6 PUT a un id inexistente" $r 404
```

**Esperado:**

| # | Código | Además |
| --- | --- | --- |
| P2 | `200` | Nombre `QA Operador Editado`, roles `operador_proceso` |
| P3 | `200` | Roles siguen siendo `operador_proceso` |
| P4 | `200` | `activo` sigue en `True` |
| P5 | `200` | Roles `gerencia`, una sola vez |
| P6 | `404` | — |

## 5. Un administrador no puede quitarse permisos

Se usa un administrador temporal (`qa_admin`), nunca el real.

```powershell
$r = Llamar POST "/auth/usuarios" @{
    nombre_usuario  = "qa_admin"
    nombre_completo = "QA Administrador"
    password        = $claveQa
    roles           = @("administrador")
} $tokenAdmin
Revisar "P7 crear administrador temporal" $r 201
$idQaAdmin = $r.Datos.id

$tokenQaAdmin = (Llamar POST "/auth/login" @{ nombre_usuario = "qa_admin"; password = $claveQa }).Datos.access_token

# P8: quitarse el rol administrador a si mismo.
$r = Llamar PUT "/auth/usuarios/$idQaAdmin" @{ roles = @("gerencia") } $tokenQaAdmin
Revisar "P8 admin se cambia a gerencia (a si mismo)" $r 400
Write-Host "   mensaje:" $r.Datos.detail

# P9: comprobar que sigue siendo administrador.
$r = Llamar GET "/auth/me" $null $tokenQaAdmin
Revisar "P9 /me despues del rechazo" $r 200
Write-Host "   roles:" ($r.Datos.roles -join ", ")

# P10: si conserva administrador en la lista, si puede editar sus roles.
$r = Llamar PUT "/auth/usuarios/$idQaAdmin" @{ roles = @("administrador", "gerencia") } $tokenQaAdmin
Revisar "P10 admin agrega gerencia y conserva admin" $r 200
Write-Host "   roles:" ($r.Datos.roles -join ", ")

# P11: desactivarse a si mismo (ya probado en el acta; se repite tras el cambio).
$r = Llamar PUT "/auth/usuarios/$idQaAdmin" @{ activo = $false } $tokenQaAdmin
Revisar "P11 admin se desactiva a si mismo" $r 400
```

**Esperado:** P8 `400` con el mensaje "No puedes quitarte el rol administrador a ti mismo"; P9 `200` con `administrador`; P10 `200` con `administrador, gerencia`; P11 `400`.

## 6. Usuario con rol `gerencia`

```powershell
$r = Llamar POST "/auth/usuarios" @{
    nombre_usuario  = "qa_gerencia"
    nombre_completo = "QA Gerencia"
    password        = $claveQa
    roles           = @("gerencia")
} $tokenAdmin
Revisar "P12 crear usuario gerencia" $r 201

$r = Llamar POST "/auth/login" @{ nombre_usuario = "qa_gerencia"; password = $claveQa }
Revisar "P13 login de gerencia" $r 200
$tokenGerencia = $r.Datos.access_token

$r = Llamar GET "/auth/me" $null $tokenGerencia
Revisar "P14 /me de gerencia" $r 200
Write-Host "   roles:" ($r.Datos.roles -join ", ")

# Gerencia tiene mas rango que un operador, pero no administra usuarios.
$r = Llamar GET "/auth/usuarios" $null $tokenGerencia
Revisar "P15 gerencia lista usuarios" $r 403

# El nombre anterior del rol ya no es valido.
$r = Llamar POST "/auth/usuarios" @{
    nombre_usuario  = "qa_supervisor"
    nombre_completo = "QA Supervisor"
    password        = $claveQa
    roles           = @("supervisor")
} $tokenAdmin
Revisar "P16 crear con el rol antiguo supervisor" $r 422
```

**Esperado:** P12 `201`, P13 `200`, P14 `200` con `gerencia`, P15 `403`, P16 `422`.

## 7. Revisar la base de datos

Usa la contraseña de `sistema/.env` (`MSSQL_SA_PASSWORD`).

```powershell
docker exec a2d_sqlserver /opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -P "<tu-contraseña>" -d a2d_sm -Q "SELECT u.nombre_usuario, r.rol FROM usuarios u JOIN usuario_roles r ON r.usuario_id = u.id WHERE u.nombre_usuario LIKE 'qa[_]%' ORDER BY 1, 2"
```

**Esperado:** `qa_admin` con `ADMINISTRADOR` y `GERENCIA`; `qa_gerencia` con `GERENCIA`; `qa_operador` con `GERENCIA`. Ninguna fila repetida y ninguna con `SUPERVISOR`.

## 8. Limpiar

No existe un endpoint para borrar usuarios (se desactivan), así que los temporales se borran directo en la base. Primero los roles, por la clave foránea:

```powershell
docker exec a2d_sqlserver /opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -P "<tu-contraseña>" -d a2d_sm -Q "DELETE FROM usuario_roles WHERE usuario_id IN (SELECT id FROM usuarios WHERE nombre_usuario LIKE 'qa[_]%'); DELETE FROM usuarios WHERE nombre_usuario LIKE 'qa[_]%'; SELECT COUNT(*) AS quedan FROM usuarios WHERE nombre_usuario LIKE 'qa[_]%'"
```

**Esperado:** `quedan` = `0`. En `LIKE`, `[_]` significa un guion bajo literal (sin corchetes, `_` es comodín de un carácter).

---

## 9. Registro de resultados

Copiar esta tabla como sección nueva ("Pruebas complementarias") al final de `Resultados_Pruebas_E1_2026-10-03.md`.

| # | Caso | Esperado | Obtenido | Estado |
| --- | --- | --- | --- | --- |
| P0 | Login del administrador | `200` | | ☐ |
| P1 | `POST` con un rol repetido | `201`, cada rol una vez | | ☐ |
| P2 | `PUT` válido (nombre y roles) | `200` | | ☐ |
| P3 | `PUT` con `roles: null` | `200`, roles sin cambios | | ☐ |
| P4 | `PUT` con `activo: null` | `200`, sigue activo | | ☐ |
| P5 | `PUT` con un rol repetido | `200`, un solo rol | | ☐ |
| P6 | `PUT` a un id inexistente | `404` | | ☐ |
| P7 | Crear administrador temporal | `201` | | ☐ |
| P8 | Administrador se quita su rol | `400` | | ☐ |
| P9 | `/me` tras el rechazo | `200`, sigue administrador | | ☐ |
| P10 | Administrador agrega un rol y conserva el suyo | `200` | | ☐ |
| P11 | Administrador se desactiva a sí mismo | `400` | | ☐ |
| P12 | Crear usuario `gerencia` | `201` | | ☐ |
| P13 | Login de `gerencia` | `200` | | ☐ |
| P14 | `/me` de `gerencia` | `200`, rol `gerencia` | | ☐ |
| P15 | `gerencia` lista usuarios | `403` | | ☐ |
| P16 | Crear con el rol antiguo `supervisor` | `422` | | ☐ |
| BD | Revisión en SQL Server | Sin repetidos ni `SUPERVISOR` | | ☐ |
| — | Limpieza | `quedan = 0` | | ☐ |

Fecha de ejecución: ____ · Ejecutado por: ____ · Commit probado: ____ (`git log --oneline -1`)

Si algún caso da **FALLA**: anotar el código y el `detail` obtenidos, revisar `docker compose logs backend` y avisar al responsable del módulo antes de cerrar E1.
