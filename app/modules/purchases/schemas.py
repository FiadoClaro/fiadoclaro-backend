from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ItemIn(BaseModel):
    producto_id: int
    cantidad: Decimal = Field(gt=0, max_digits=10, decimal_places=3)


class CompraIn(BaseModel):
    cliente_id: int
    items: list[ItemIn] = Field(min_length=1)
    modalidad: Literal["FIN_MES", "CUOTAS"]
    num_cuotas: int = Field(1, ge=1, le=36, description="Solo para CUOTAS")
    fecha_hora: datetime | None = Field(
        None, description="Opcional, para pasar al sistema compras del cuaderno; por defecto, ahora"
    )

    @model_validator(mode="after")
    def _cuotas(self):
        if self.modalidad == "FIN_MES":
            self.num_cuotas = 1
        return self


class DetalleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    producto_id: int
    descripcion: str
    cantidad: Decimal
    precio_unitario: Decimal
    subtotal: Decimal


class CuotaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    numero: int
    fecha_vencimiento: date
    saldo_inicial: Decimal
    interes: Decimal
    amortizacion: Decimal
    cuota: Decimal
    saldo_final: Decimal
    estado: str = "PENDIENTE"


class TasaPactadaOut(BaseModel):
    tipo: str
    valor: Decimal
    periodo_dias: int
    capitalizacion_dias: int | None
    tem_pct: Decimal
    tea_pct: Decimal


class SimulacionOut(BaseModel):
    """Resultado del cálculo, antes o después de registrar la compra."""

    cliente_id: int
    modalidad: str
    num_cuotas: int
    moneda: str
    fecha_hora: datetime
    fecha_corte: date = Field(description="Ciclo al que pertenece la compra")
    fecha_pago: date = Field(description="Fecha de pago del ciclo")
    dias_gracia: int = Field(description="Días entre la compra y la fecha de pago")
    detalles: list[DetalleOut]
    monto_total: Decimal
    tasa: TasaPactadaOut
    interes_total: Decimal
    monto_capitalizado: Decimal
    valor_cuota: Decimal
    total_a_pagar: Decimal
    tcea_pct: Decimal | None
    cronograma: list[CuotaOut]
    credito_disponible_antes: Decimal | None = None
    credito_disponible_despues: Decimal | None = None
    excede_credito: bool = Field(False, description="True si el monto supera el crédito disponible")
    deficit: Decimal = Field(Decimal("0.00"), description="Cuánto falta de crédito para poder registrarla")
    mensaje: str | None = Field(None, description="Aviso para mostrar cuando la compra no se puede registrar")


class CompraOut(SimulacionOut):
    id: int
    estado: str
    registrado_por: int


class CompraResumenOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cliente_id: int
    fecha_hora: datetime
    modalidad: str
    num_cuotas: int
    moneda: str
    monto_total: Decimal
    interes_total: Decimal
    fecha_corte: date
    fecha_pago: date
    estado: str
