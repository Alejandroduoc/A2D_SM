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
    #Un atributo con type hint (str) y un valor por defecto. Pydantic busca DATABASE_URL en el entorno; si no la encuentra, usa ese string.

    #seguridad 
    secret_key: str="CAMBIAR_EN_.env_NUNCA_USAR_ESTE_VALOR_EN_PRODUCCION"# Un atributo con type hint (str) y un valor por defecto. Pydantic busca SECRET_KEY en el entorno; si no la encuentra, usa ese string.
    algorithm: str="HS256" # Un atributo con type hint (str) y un valor por defecto. Pydantic busca ALGORITHM en el entorno; si no la encuentra, usa ese string.


    #cors
    cors_origins: list[str]=["http://localhost:5173"] # direcciones permitidas
@lru_cache
def get_settings() -> Settings:
    #función que devuelve una instancia de Settings. Al usar lru_cache, la primera vez que se llama, se crea la instancia y se guarda en memoria; las siguientes veces, se devuelve la misma instancia sin recalcularla.
    return Settings()   
settings = get_settings() # se llama a la función y se guarda la instancia en la variable settings. Esta variable se puede importar en otros módulos para acceder a la configuración.   

        