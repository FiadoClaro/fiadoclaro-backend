from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class ImputacionOut(BaseModel):
    orden: int
    concepto: str
    exigible: Decimal
    imputado: Decimal
    saldo: Decimal


class CotizacionOut(BaseModel):
    """Lo que el cliente debe pagar si paga en `fecha_pago` (incluye la mora si hay atraso)."""

    estado_cuenta_id: int
    fecha_pago_pactada: date
    fecha_pago: date
    dias_mora: int
    interes_moratorio: Decimal
    interes_compensatorio: Decimal
    capital: Decimal
    total_exigible: Decimal
    prelacion: list[ImputacionOut]


class PagoIn(BaseModel):
    estado_cuenta_id: int
    fecha_pago: date | None = Field(None, description="Por defecto, hoy")
    monto: Decimal = Field(gt=0, max_digits=12, decimal_places=2,
                           description="Debe ser igual al total exigible: no se aceptan pagos parciales")


class PagoOut(BaseModel):
    id: int
    estado_cuenta_id: int
    cliente_id: int
    fecha_pago: date
    dias_mora: int
    monto_total: Decimal
    imputacion: list[ImputacionOut]
    created_at: datetime
