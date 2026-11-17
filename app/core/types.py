"""Tipos de columna reutilizables: montos y tasas siempre NUMERIC (nunca float)."""
from sqlalchemy import Numeric

Monto = Numeric(12, 2)        # S/ 9,999,999,999.99
Tasa = Numeric(12, 7)         # porcentaje con 7 decimales: 3.5000000 = 3.5 %
TasaDerivada = Numeric(16, 10)  # TEM/TEA calculadas, guardadas con 10 decimales
Cantidad = Numeric(10, 3)     # 2.500 kg

ROLES = ("ADMIN_SISTEMA", "ADMIN_TIENDA", "CLIENTE")
TIPOS_TASA = ("NOMINAL", "EFECTIVA")
MONEDAS = ("PEN", "USD")
MODALIDADES = ("FIN_MES", "CUOTAS")


def check_in(columna: str, valores: tuple[str, ...]) -> str:
    lista = ", ".join(f"'{v}'" for v in valores)
    return f"{columna} IN ({lista})"
