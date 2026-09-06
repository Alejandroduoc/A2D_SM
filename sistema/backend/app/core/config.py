from functools import lru_cache 
# importa lru_cache de la librería estándar. Es un decorador que guarda en memoria el resultado de una función para no recalcularlo. Se usa abajo para que Settings() se construya una sola vez.
from pydantic_settings import BaseSettings, SettingsConfigDict
#BaseSettings: clase base que, al heredarla, lee automáticamente las variables de entorno y el .env y las convierte al tipo que declares.
#SettingsConfigDict: objeto para configurar cómo se comporta esa lectura (qué archivo leer, qué hacer con variables de más, etc.).

class Settings(BaseSettings):
#define tu clase de configuración. Al heredar de BaseSettings, cada atributo que declares abajo se puede sobreescribir con una variable de entorno del mismo nombre (en mayúsculas).
    model_config = SettingsConfigDict(
        env_file=".env",  # indica que se debe leer el archivo .env en la raíz del proyecto para obtener las variables de entorno.
        extra="ignore" ) # indica que si hay variables de entorno que no están declaradas en la clase, se ignoren y no generen error.

database_url: str="mssql+pyodbc://sa:CAMBIAR_EN_.env@localhost:1433/socradex?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"
