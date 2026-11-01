"""Reglas de negocio de las tarjas de recepción (HU12, HU13 y HU14).

Por ahora contiene los errores de negocio y el cálculo de kilos netos, que no
usan la base. registrar_tarja, pendientes_productor y obtener_tarja se agregan
cuando estén los modelos de Diego (D2).
"""

# Pesos exactos y redondeo bancario.
from decimal import ROUND_HALF_EVEN, Decimal


# El router traduce este error a HTTP 400.
class CatalogoNoValidoError(Exception):
    """El productor o un catálogo elegido no existe o está inactivo."""


# El router traduce este error a HTTP 400.
class KilosNetosNoValidosError(Exception):
    """Los kilos netos calculados son cero o negativos (HU14 criterio 2)."""


# Calcula los kilos netos de una tarja (HU14 criterio 1).
def calcular_kilos_netos(kilos_brutos: Decimal, cantidad: int, tara: Decimal, pallet: Decimal) -> int:
    """Neto = brutos − bandejas × tara − pallet, redondeado a entero.

    El redondeo es bancario (ROUND_HALF_EVEN), igual que CInt en Form4.vb del
    legado: 2,5 queda en 2 y 3,5 sube a 4. Es una función pura: no valida que
    el resultado sea positivo; eso lo decide registrar_tarja.
    """
    # Todo en Decimal para no perder precisión con float.
    neto = kilos_brutos - cantidad * tara - pallet
    # Redondea a entero con el criterio del legado y lo entrega como int.
    return int(neto.quantize(Decimal("1"), rounding=ROUND_HALF_EVEN))
