"""
Prueba de api/deps.py sin router: llama a las dependencias directamente con
tokens reales. Crea usuarios de prueba dentro de una transacción y al final
hace ROLLBACK, así que no deja nada en la base de datos.

Ejecutar (desde la raíz del repo):
    docker compose exec -e PYTHONPATH=/app backend python tests/probar_deps.py
"""
from datetime import timedelta

from fastapi import HTTPException

from app.api.deps import get_current_user, require_rol, require_roles
from app.core.database import SessionLocal
from app.core.security import create_access_token, create_refresh_token, hash_password
from app.models.usuario import RolUsuario, Usuario, UsuarioRol

db = SessionLocal()
fallas = 0


def probar(nombre, llamada, esperado):
    """Ejecuta `llamada` y compara el código HTTP obtenido (200 si no lanzó error)."""
    global fallas
    try:
        llamada()
        obtenido = 200
    except HTTPException as e:
        obtenido = e.status_code
    ok = obtenido == esperado
    fallas += 0 if ok else 1
    print(("OK    " if ok else "FALLA ") + f"{nombre:<58} esperado {esperado}, obtenido {obtenido}")


def crear(nombre, roles, activo=True):
    return Usuario(nombre_usuario=nombre, nombre_completo=nombre.upper(), password_hash=hash_password("Clave1234!"),
                   activo=activo, roles_asignados=[UsuarioRol(rol=r) for r in roles])


try:
    admin = crear("t_admin", [RolUsuario.ADMINISTRADOR])
    sup = crear("t_super", [RolUsuario.SUPERVISOR])
    op_bod = crear("t_bodega", [RolUsuario.OPERADOR_BODEGA])
    op_dos = crear("t_dos_roles", [RolUsuario.OPERADOR_RECEPCION, RolUsuario.OPERADOR_BODEGA])
    inactivo = crear("t_inactivo", [RolUsuario.ADMINISTRADOR], activo=False)
    db.add_all([admin, sup, op_bod, op_dos, inactivo])
    db.flush()  # los envía a la base dentro de la transacción, sin confirmarlos

    def tok(u):
        return create_access_token(u.nombre_usuario, [r.value for r in u.roles])

    print("--- get_current_user")
    probar("token válido de un usuario activo", lambda: get_current_user(tok(admin), db), 200)
    probar("token basura", lambda: get_current_user("esto-no-es-un-jwt", db), 401)
    probar("token vencido", lambda: get_current_user(create_access_token("t_admin", [], timedelta(seconds=-5)), db), 401)
    probar("refresh token usado como acceso", lambda: get_current_user(create_refresh_token("t_admin"), db), 401)
    probar("token de un usuario que no existe", lambda: get_current_user(create_access_token("fantasma", []), db), 401)
    probar("token de un usuario desactivado", lambda: get_current_user(tok(inactivo), db), 401)

    print("--- require_rol (jerárquico)")
    exige_admin = require_rol(RolUsuario.ADMINISTRADOR)
    exige_super = require_rol(RolUsuario.SUPERVISOR)
    probar("administrador pasa require_rol(ADMINISTRADOR)", lambda: exige_admin(admin), 200)
    probar("supervisor NO pasa require_rol(ADMINISTRADOR)", lambda: exige_admin(sup), 403)
    probar("operador NO pasa require_rol(ADMINISTRADOR)", lambda: exige_admin(op_bod), 403)
    probar("administrador pasa require_rol(SUPERVISOR)", lambda: exige_super(admin), 200)
    probar("operador NO pasa require_rol(SUPERVISOR)", lambda: exige_super(op_bod), 403)

    print("--- require_roles (lista exacta)")
    recepcion_o_admin = require_roles(RolUsuario.OPERADOR_RECEPCION, RolUsuario.ADMINISTRADOR)
    probar("operador_bodega NO está en la lista", lambda: recepcion_o_admin(op_bod), 403)
    probar("usuario con 2 roles: uno está en la lista", lambda: recepcion_o_admin(op_dos), 200)
    probar("supervisor NO está en la lista (aunque tenga más rango)", lambda: recepcion_o_admin(sup), 403)
finally:
    db.rollback()  # no queda ningún usuario de prueba en la base
    db.close()

print("\nRESULTADO:", "todas las pruebas pasaron" if fallas == 0 else f"{fallas} prueba(s) fallaron")