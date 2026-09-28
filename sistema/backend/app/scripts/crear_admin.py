"""
Crea el primer usuario ADMINISTRADOR del sistema.

Sin este script no hay forma de iniciar sesión: la API solo deja crear usuarios
a un administrador, y en una base recién creada no existe ninguno.

Se ejecuta desde la carpeta sistema/ (necesita una terminal interactiva):

    docker compose exec backend python -m app.scripts.crear_admin
"""

import sys                      # sys.exit() para terminar el script con un código de error
from getpass import getpass     # pide la contraseña sin mostrarla en pantalla

# Fábrica de sesiones: aquí no hay FastAPI, así que la sesión se abre y se cierra a mano.
from app.core.database import SessionLocal
# Convierte la contraseña en un hash bcrypt; en la base nunca se guarda en texto plano.
from app.core.security import hash_password
# Modelos: el usuario, su tabla de roles y el enum con los roles válidos.
from app.models.usuario import RolUsuario, Usuario, UsuarioRol


# Pide los datos por consola, los valida y los devuelve como una tupla.
def pedir_datos() -> tuple[str, str, str]:
    # .strip() quita los espacios que se escriban de más al inicio o al final.
    nombre_usuario = input("Nombre de usuario: ").strip()
    nombre_completo = input("Nombre completo: ").strip()
    # getpass no muestra lo que se escribe, para que la contraseña no quede en pantalla.
    password = getpass("Contraseña: ")
    # Se pide dos veces para evitar crear el administrador con una contraseña mal escrita.
    confirmacion = getpass("Repite la contraseña: ")

    # Los límites son los mismos de UsuarioCreate (schemas/auth.py) y de las columnas
    # del modelo: así el error se ve aquí, claro, y no como un error de SQL Server.
    if not 3 <= len(nombre_usuario) <= 50:
        print("Error: el nombre de usuario debe tener entre 3 y 50 caracteres.")
        sys.exit(1)  # 1 = terminó con error (0 sería éxito)
    if not 3 <= len(nombre_completo) <= 150:
        print("Error: el nombre completo debe tener entre 3 y 150 caracteres.")
        sys.exit(1)
    # Política actual de contraseñas: mínimo 8 caracteres (igual que UsuarioCreate).
    if len(password) < 8:
        print("Error: la contraseña debe tener al menos 8 caracteres.")
        sys.exit(1)
    if password != confirmacion:
        print("Error: las contraseñas no coinciden.")
        sys.exit(1)

    # Todo válido: se devuelven los tres datos en este orden.
    return nombre_usuario, nombre_completo, password


# Crea el administrador en la base de datos con los datos pedidos.
def crear_admin() -> None:
    # Desempaqueta la tupla que devuelve pedir_datos() en tres variables.
    nombre_usuario, nombre_completo, password = pedir_datos()

    # Abre una sesión (conexión + transacción) con la base de datos.
    db = SessionLocal()
    try:
        # Busca un usuario con ese nombre (mismo estilo de consulta que deps.py).
        # .first() devuelve el usuario o None si no existe.
        existente = db.query(Usuario).filter(Usuario.nombre_usuario == nombre_usuario).first()
        # Si ya existe, no se crea otro: se avisa y se termina sin tocar la base.
        if existente:
            print(f"Error: el usuario '{nombre_usuario}' ya existe.")
            sys.exit(1)  # el finally de abajo igual cierra la sesión

        # Crea el objeto Usuario en memoria (todavía no está en la base).
        # id, activo y creado_en no se escriben: los rellena el default del modelo.
        usuario = Usuario(
            nombre_usuario=nombre_usuario,
            nombre_completo=nombre_completo,
            # Se guarda solo el hash; la contraseña original no sale de esta función.
            password_hash=hash_password(password),
        )

        # Le asigna el rol ADMINISTRADOR. No hace falta poner usuario_id:
        # SQLAlchemy lo completa al guardar, porque el rol está dentro de roles_asignados.
        usuario.roles_asignados.append(UsuarioRol(rol=RolUsuario.ADMINISTRADOR))

        # Agrega el usuario (y su rol, por la relación) a la sesión.
        db.add(usuario)
        # Confirma la transacción: recién aquí se escriben las filas en SQL Server.
        db.commit()
        print(f"Administrador '{nombre_usuario}' creado correctamente.")
    except Exception:
        # Si algo falló, deshace lo pendiente para no dejar un usuario sin rol.
        db.rollback()
        # Vuelve a lanzar el error para ver el detalle completo en la consola.
        raise
    finally:
        # Cierra la sesión siempre, haya salido bien o mal.
        db.close()


# Solo se ejecuta al correr el archivo como script, no cuando otro módulo lo importa.
if __name__ == "__main__":
    crear_admin()
