from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.finance.engine import Tasa


class TasaIn(BaseModel):
    """Tasa tal como la pacta la tienda. El valor va en porcentaje (3.5 = 3.5 %)."""

    tipo: Literal["NOMINAL", "EFECTIVA"]
    valor: Decimal = Field(ge=0, le=1000, max_digits=12, decimal_places=7, description="Porcentaje, hasta 7 decimales")
    periodo_dias: int = Field(30, ge=1, le=360, description="30 = mensual, 360 = anual (año comercial)")
    capitalizacion_dias: int | None = Field(
        None, ge=1, le=360, description="Solo para nominal. Por defecto 1 (diaria), regla del curso"
    )

    @model_validator(mode="after")
    def _coherencia(self):
        if self.tipo == "EFECTIVA":
            self.capitalizacion_dias = None
        else:
            self.capitalizacion_dias = self.capitalizacion_dias or 1
            if self.capitalizacion_dias > self.periodo_dias:
                raise ValueError("La capitalización no puede ser mayor al periodo de la tasa")
        return self

    def to_engine(self) -> Tasa:
        return Tasa(self.tipo, self.valor, self.periodo_dias, self.capitalizacion_dias)


class EquivalenciasOut(BaseModel):
    ted_pct: Decimal
    tem_pct: Decimal
    tea_pct: Decimal


class TopeIn(BaseModel):
    tipo: Literal["COMPENSATORIA", "MORATORIA"]
    moneda: Literal["PEN", "USD"] = Field("PEN", description="PEN = soles, USD = dólares")
    tea_maxima: Decimal = Field(gt=0, max_digits=12, decimal_places=7, description="TEA máxima en %")
    vigente_desde: date
    fuente: str | None = Field(None, max_length=200)


class TopeOut(TopeIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
