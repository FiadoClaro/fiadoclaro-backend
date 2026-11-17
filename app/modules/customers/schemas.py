from datetime import date, datetime, time
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.modules.finance.schemas import EquivalenciasOut, TasaIn
from app.modules.iam.schemas import Credenciales


class ClienteDatos(BaseModel):
    nombres: str = Field(min_length=2, max_length=80)
    apellidos: str = Field(min_length=2, max_length=80)
    telefono: str | None = Field(None, max_length=20)
    correo: EmailStr | None = None
    direccion: str | None = Field(None, max_length=200)


class CondicionIn(BaseModel):
    """Condiciones del fiado (enunciado, punto 3)."""

    moneda: Literal["PEN", "USD"] = "PEN"
    tasa: TasaIn = Field(description="Tasa compensatoria pactada (nominal o efectiva)")
    tasa_mora: TasaIn = Field(description="Tasa moratoria pactada (nominal o efectiva)")
    limite_credito: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    max_meses: int = Field(ge=1, le=36, description="Máximo de meses en cuotas para este cliente")
    dia_corte: int = Field(ge=1, le=28, description="Día del mes en que se cierra el ciclo (1 a 28)")
    hora_corte: time = Field(time(18, 0), description="Hora de corte; compras posteriores pasan al ciclo siguiente")
    dia_pago: int = Field(ge=1, le=28, description="Día del mes en que el cliente se compromete a pagar")

    @model_validator(mode="after")
    def _dias(self):
        if self.dia_corte == self.dia_pago:
            raise ValueError("El día de pago debe ser distinto al día de corte")
        return self


class ClienteCreate(ClienteDatos):
    dni: str = Field(pattern=r"^\d{8}$", description="DNI de 8 dígitos")
    condicion: CondicionIn
    acceso: Credenciales = Field(description="Usuario y contraseña del vecino para el portal")


class ClienteUpdate(BaseModel):
    nombres: str | None = Field(None, min_length=2, max_length=80)
    apellidos: str | None = Field(None, min_length=2, max_length=80)
    telefono: str | None = Field(None, max_length=20)
    correo: EmailStr | None = None
    direccion: str | None = Field(None, max_length=200)


class TasaOut(BaseModel):
    tipo: str
    valor: Decimal
    periodo_dias: int
    capitalizacion_dias: int | None
    equivalencias: EquivalenciasOut


class CondicionOut(BaseModel):
    moneda: str
    tasa: TasaOut
    tasa_mora: TasaOut
    limite_credito: Decimal
    max_meses: int
    dia_corte: int
    hora_corte: time
    dia_pago: int


class ResumenCredito(BaseModel):
    limite: Decimal
    utilizado: Decimal = Field(description="Capital pendiente de pago")
    disponible: Decimal
    porcentaje_utilizado: Decimal
    estado_pago: Literal["AL_DIA", "EN_MORA"]
    proximo_corte: date
    proximo_pago: date
    listados_pendientes: int


class ClienteOut(ClienteDatos):
    id: int
    tienda_id: int
    dni: str
    estado: str
    usuario: str
    created_at: datetime
    condicion: CondicionOut
    resumen: ResumenCredito
