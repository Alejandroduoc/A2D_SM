"""Límite de intentos fallidos de inicio de sesión (protección contra fuerza bruta).

Guarda los intentos en la memoria del proceso: no necesita tablas nuevas y se
reinicia al reiniciar el backend. Sirve mientras la API corra en un solo proceso
de uvicorn (como hoy en desarrollo y producción). Con varios procesos o
servidores habría que moverlo a la base de datos o a Redis.

Detrás de un proxy (nginx), la IP que ve la API es la del proxy; por eso el
límite principal es por nombre de usuario y el de IP es mucho más alto.
"""

# Bloqueo para que dos peticiones simultáneas no corrompan los contadores.
import threading
# Reloj monotónico: no retrocede si se cambia la hora del servidor.
import time
# Lista con extracción eficiente por la izquierda para descartar intentos viejos.
from collections import deque

# Límites configurables desde variables de entorno.
from app.core.config import settings


# Lleva la cuenta de fallos por clave (usuario o IP) y los bloqueos vigentes.
class LimiteIntentos:
    # Prepara los diccionarios vacíos y el candado compartido.
    def __init__(self) -> None:
        # clave -> instantes (segundos monotónicos) de los fallos recientes.
        self._fallos: dict[str, deque[float]] = {}
        # clave -> instante en que termina el bloqueo.
        self._bloqueado_hasta: dict[str, float] = {}
        # Las rutas síncronas de FastAPI corren en varios hilos a la vez.
        self._candado = threading.Lock()

    # Arma las claves de usuario e IP; el usuario va en minúsculas porque SQL Server
    # compara sin distinguir mayúsculas y "Admin" y "admin" son la misma cuenta.
    @staticmethod
    def _claves(nombre_usuario: str, ip: str) -> tuple[str, str]:
        return "usuario:" + nombre_usuario.strip().lower(), "ip:" + ip

    # Devuelve los segundos de bloqueo que quedan (0 si puede intentar).
    def segundos_bloqueo(self, nombre_usuario: str, ip: str) -> int:
        # Instante actual para comparar con los vencimientos.
        ahora = time.monotonic()
        with self._candado:
            # Revisa ambas claves y se queda con el bloqueo más largo.
            restante = 0.0
            for clave in self._claves(nombre_usuario, ip):
                hasta = self._bloqueado_hasta.get(clave)
                # Un bloqueo vencido se borra para no acumular memoria.
                if hasta is not None and hasta <= ahora:
                    del self._bloqueado_hasta[clave]
                elif hasta is not None:
                    restante = max(restante, hasta - ahora)
        # Redondea hacia arriba para no informar 0 segundos si aún queda una fracción.
        return int(restante) + (1 if restante % 1 else 0)

    # Anota un fallo y bloquea la clave que superó su límite.
    def registrar_fallo(self, nombre_usuario: str, ip: str) -> None:
        # Instante del fallo.
        ahora = time.monotonic()
        # Solo cuentan los fallos dentro de la ventana configurada.
        ventana = settings.login_ventana_minutos * 60
        # Límite distinto para usuario e IP.
        clave_usuario, clave_ip = self._claves(nombre_usuario, ip)
        limites = {clave_usuario: settings.login_max_intentos, clave_ip: settings.login_max_intentos_ip}
        with self._candado:
            for clave, limite in limites.items():
                # Crea la lista de fallos la primera vez que aparece la clave.
                fallos = self._fallos.setdefault(clave, deque())
                fallos.append(ahora)
                # Descarta los fallos más antiguos que la ventana.
                while fallos and fallos[0] <= ahora - ventana:
                    fallos.popleft()
                # Al alcanzar el límite, bloquea y reinicia el contador de esa clave.
                if len(fallos) >= limite:
                    self._bloqueado_hasta[clave] = ahora + settings.login_bloqueo_minutos * 60
                    del self._fallos[clave]

    # Un login correcto borra los fallos acumulados del usuario (no los de la IP).
    def registrar_exito(self, nombre_usuario: str, ip: str) -> None:
        clave_usuario, _ = self._claves(nombre_usuario, ip)
        with self._candado:
            self._fallos.pop(clave_usuario, None)

    # Vacía todo; lo usan las pruebas para empezar cada escenario desde cero.
    def reiniciar(self) -> None:
        with self._candado:
            self._fallos.clear()
            self._bloqueado_hasta.clear()


# Instancia única que comparte todo el proceso.
limite_login = LimiteIntentos()
