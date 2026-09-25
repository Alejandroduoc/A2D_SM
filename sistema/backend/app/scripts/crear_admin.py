## Para crear el admin ejecutar : docker compose exec backend python -m app.scripts.crear_admin

#Permite solicitar la contraseña sin mostrarla en pantalla.
from getpass import getpass
#Importa los tipos y clases necesarios para trabajar con SQLAlchemy.
from sqlalchemy.orm import Session
#Importa la fabrica que crea sesiones de conexión con la base de datos.
from app.core.database import SessionLocal
#Importa la función que transforma la contraseña  en un hash bcrypt.
from app.core.security import hash_password
#Importa el modelo de usuario, la tabla intermedia y el enum de roles.
from app.models.usuario import RolUsuario, Usuario, UsuarioRol

#Comprueba si ya existe un usuaruio con el nombre "admin" en la base de datos.
def administrador_existe(db: Session) -> bool:
    #Busca una asociación que tenga asignado el rol ADMINISTRADOR.
    administrador = (
        db.query(UsuarioRol)
        .filter(UsuarioRol.rol == RolUsuario.ADMINISTRADOR)
        .first()
    )
    
    #Devuelve True si encontró un administrador, de lo contrario, False
    return administrador is not None

#Solicita los datos y crea el primer del sistema.
def crear_administrador() -> None:
    #Abre una sesión para comunicarse con la base de datos.
    db = SessionLocal()
    
    try:
        #Evita crear más de un administrador inicial por accidente
        if administrador_existe(db):
            print("Ya existe un usuario administrador.")
            return
        
        #Solicita el nombre de usuario y elimina espacios innecesarios.
        nombre_usuario = input("Ingrese el nombre de usuario: ").strip()
        
        #Valida que el nombre de usuarui no esté vacío.
        if not nombre_usuario:
            print("El nombre de usuario no puede estar vacío.")
            return
        
        #Solicita el nombre de usuario y elimina espacios innecesarios.
        nombre_usuario = input("Nombre de usuario: ").strip()
        
        #Valdida que el nombre no esté vacío.
        if not nombre_usuario:
            print("El nombre de usuario no puede estar vacío.")
            return
        
        #Comprueba que no exista otro usuario con el mismo nombre.
        usuario_existente = (
            db.query(Usuario)
            .filter(Usuario.nombre_usuario == nombre_usuario)
            .first()
        )
        
        #Detiene el proceso si el nombre ya está ocupado
        if usuario_existente is not None:
            print("Ya existe un usuario con ese nombre. Intente con otro.")
            return
        
        #Solicita la contraseña sin mostrar los carácteres escritos.
        password = getpass("Contraseña: ")
        
        #Solicita nuevamente la contraseña para confirmar que se escribió correctamente.
        pasword_confirmada = getpass("Confirme la contraseña: ")
        
        #Comprueba que ambas contraseñas coincidan.
        if password != pasword_confirmada:
            print("Las contraseñas no coinciden. Intente nuevamente.")
            return
        
        #Comprueba la longitud mínima definida para las contraseñas.
        if len(password) < 8:
            print("La contraseña debe tener al menos 8 caracteres.")
            return
        
        #Convierte la contreña original en un hash irreversible.
        password_hash = hash_password(password)
        
        # Construye la entidad Usuario que se guardará en la base de datos.
        nuevo_usuario = Usuario(
            nombre_usuario=nombre_usuario,
            nombre_completo=nombre_usuario,
            password_hash=password_hash,
            activo=True,
            roles_asignados=[
                UsuarioRol(rol=RolUsuario.ADMINISTRADOR)
            ],
        )
        
        #Agrega el nuevo usuario a la sesion actual.
        db.add(nuevo_usuario)
        
        #Confirma la trasacción y guarda el ususarui definitivamente.
        db.commit()
        
        #Informa que la operación terminó correctamente.
        print("Administrador creado correctamente.")
    
    except Exception:
        #Deshace los cambios si ocure un error durante la transacción.
        db.rollback()
        
        #Vuelve a lanzar el error para que pueda ser registrado y revisado.
        raise
    finally:
        #Cierra la sesión aunque ocurra un error o se use return para salir de la función.
        db.close()
        
#Ejecuta el proceso solamente cuando este archiv se ejecuta directamente.
if __name__ == "__main__":
    #Inicia la creación del administrador.
    crear_administrador()