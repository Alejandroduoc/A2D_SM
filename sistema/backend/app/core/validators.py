"""
Validadores compartidos que no dependen de un modelo/schema en particular.
"""

# Importa herramientas para buscar y reemplazar patrones de texto.
import re


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
