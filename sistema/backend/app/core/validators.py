"""
Validadores compartidos que no dependen de un modelo/schema en particular.
"""

# Importa herramientas para buscar y reemplazar patrones de texto.
import re

# Permite unificar representaciones Unicode conservando letras y acentos.
import unicodedata


# Valida si un RUT chileno tiene un dígito verificador correcto.
def validar_rut_chileno(rut: str) -> bool:
    """
    Dígito verificador chileno (Módulo 11) — equivalente a la función `Modulo11()`
    que el legacy corre al presionar Enter en el campo Rut (Form5.vb, Form63.vb).
    Acepta el rut con o sin puntos/guion (ej. "12.345.678-5" o "12345678-5").
    """
    # Elimina puntos, guiones y espacios, y convierte el RUT a mayúsculas.
    limpio = re.sub(r"[.\-\s]", "", rut).upper()
    # Rechaza valores sin cuerpo numérico o sin dígito verificador.
    if len(limpio) < 2 or not limpio[:-1].isdigit():
        return False

    # Separa el cuerpo numérico del dígito verificador ingresado.
    cuerpo, dv_ingresado = limpio[:-1], limpio[-1]

    # Inicializa la suma utilizada por el algoritmo Módulo 11.
    suma = 0
    # El primer multiplicador del algoritmo es 2.
    multiplicador = 2
    # Recorre los dígitos del cuerpo desde el último hasta el primero.
    for digito in reversed(cuerpo):
        # Multiplica cada dígito por su factor y lo acumula en la suma.
        suma += int(digito) * multiplicador
        # Avanza el multiplicador hasta 7 y luego vuelve a comenzar en 2.
        multiplicador = multiplicador + 1 if multiplicador < 7 else 2

    # Calcula el resto necesario para obtener el dígito verificador.
    resto = 11 - (suma % 11)
    # Convierte el resultado al formato usado por el RUT: 0, K o un número.
    dv_esperado = "0" if resto == 11 else "K" if resto == 10 else str(resto)

    # Devuelve True si el dígito ingresado coincide con el dígito calculado.
    return dv_ingresado == dv_esperado


# Unifica la presentación de un RUT cuyo dígito verificador ya fue validado.
def normalizar_rut(rut: str) -> str:
    """Devuelve cuerpo decimal-DV sin ceros iniciales; requiere un RUT válido."""
    # Utiliza la misma limpieza del validador y deja la letra K en mayúsculas.
    limpio = re.sub(r"[.\-\s]", "", rut).upper()
    # Separa el cuerpo numérico del último carácter, que es el dígito verificador.
    cuerpo, digito_verificador = limpio[:-1], limpio[-1]
    # Unifica el cuerpo numérico como texto decimal, sin ceros iniciales.
    cuerpo = str(int(cuerpo))
    # Mantiene una representación común para altas, ediciones y búsquedas.
    return f"{cuerpo}-{digito_verificador}"


# Prepara nombres de catálogos sin consultar la base ni alterar su capitalización.
def normalizar_nombre_catalogo(valor: object) -> str:
    # Rechaza tipos no textuales antes de intentar normalizarlos.
    if not isinstance(valor, str):
        # Los schemas convierten este error en una validación del campo nombre.
        raise ValueError("El nombre debe ser texto")
    # Unifica caracteres compuestos y descompuestos sin quitar sus tildes.
    texto = unicodedata.normalize("NFC", valor)
    # Quita espacios exteriores y reduce secuencias de espacios en blanco a uno.
    return " ".join(texto.split())


# Mismo límite que aplica bcrypt: lo que pase de 72 bytes se ignoraría al comparar.
LIMITE_BYTES_PASSWORD = 72


# Exige el largo de una contraseña nueva: 8 caracteres como mínimo y 72 bytes como máximo.
def validar_password_nueva(valor: str) -> str:
    # El mínimo se cuenta en caracteres, como lo ve la persona que la escribe.
    if len(valor) < 8:
        raise ValueError("La contraseña debe tener al menos 8 caracteres")
    # El máximo se cuenta en bytes UTF-8: una tilde o una ñ ocupan 2 bytes.
    if len(valor.encode("utf-8")) > LIMITE_BYTES_PASSWORD:
        raise ValueError("La contraseña admite hasta 72 bytes (unos 72 caracteres sin tildes)")
    # Devuelve la contraseña sin cambios: los espacios también cuentan.
    return valor


# Limpia un texto opcional (dirección, teléfono): quita espacios de más y deja None si queda vacío.
def normalizar_texto_opcional(valor: object) -> str | None:
    # None significa que el campo no se envió o se dejó sin valor.
    if valor is None:
        return None
    # Rechaza números, listas u otros tipos que no son texto.
    if not isinstance(valor, str):
        raise ValueError("El valor debe ser texto")
    # Reutiliza la misma limpieza de espacios que los catálogos.
    texto = normalizar_nombre_catalogo(valor)
    # Un texto solo con espacios equivale a no informar el dato.
    return texto or None
