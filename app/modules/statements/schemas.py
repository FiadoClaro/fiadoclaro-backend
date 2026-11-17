from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class GenerarIn(BaseModel):
    fecha_corte: date = Field(description="Fecha de corte del ciclo que se cierra")
    cliente_id: int | None = Field(None, description="Opcional: solo para un cliente")


class ItemListado(BaseModel):
    tipo: Literal["COMPRA_FIN_MES", "CUOTA", "INTERES_MORA"]
    compra_id: int | None
    fecha_compra: datetime | None
    descripcion: str
    cuota: str | None = Field(None, description="Ej. 1/3")
    fecha_vencimiento: date
    capital: Decimal
    interes: Decimal = Field(description="Interés compensatorio")
    dias_interes: int | None = Field(None, description="Días entre la compra y la fecha de pago (fin de mes)")
    mora: Decimal = Decimal("0.00")
    total: Decimal


class EstadoCuentaResumen(BaseModel):
    id: int
    cliente_id: int
    cliente: str
    dni: str
    fecha_corte: date
    fecha_pago: date
    moneda: str
    total_a_pagar: Decimal
    estado: str
    vencido: bool


class EstadoCuentaOut(EstadoCuentaResumen):
    items: list[ItemListado] = Field(description="Compras ordenadas por fecha; la mora va en un ítem aparte")
    total_capital: Decimal
    total_interes: Decimal
    fecha_consulta: date
    dias_mora: int
    interes_moratorio: Decimal
    total_exigible: Decimal = Field(description="Total a pagar a la fecha de consulta (incluye mora)")


class Omitido(BaseModel):
    cliente_id: int
    motivo: str


class GeneracionOut(BaseModel):
    fecha_corte: date
    generados: list[EstadoCuentaResumen]
    omitidos: list[Omitido]
