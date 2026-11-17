from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProductoBase(BaseModel):
    codigo: str = Field(min_length=1, max_length=30, description="SKU interno")
    nombre: str = Field(min_length=2, max_length=120)
    descripcion: str | None = Field(None, max_length=300)
    marca: str | None = Field(None, max_length=60)
    proveedor: str | None = Field(None, max_length=120)
    unidad_medida: str = Field(min_length=1, max_length=20, description="Unidad, Kilo (kg), Botella 1.5 L...")
    imagen_url: str | None = Field(None, max_length=500)
    moneda: Literal["PEN", "USD"] = "PEN"
    precio_contado: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    precio_lista_credito: Decimal = Field(gt=0, max_digits=12, decimal_places=2,
                                          description="Precio de lista a crédito (fiado)")
    permite_fin_mes: bool = Field(True, description="Se puede fiar en un solo pago a la fecha de pago")
    permite_cuotas: bool = Field(False, description="Se puede fiar en meses (cuotas)")
    max_meses: int | None = Field(None, ge=1, le=36, description="Máximo de meses si permite cuotas")

    @model_validator(mode="after")
    def _reglas(self):
        if not (self.permite_fin_mes or self.permite_cuotas):
            raise ValueError("El producto debe permitir al menos una modalidad de fiado")
        if self.permite_cuotas and not self.max_meses:
            raise ValueError("Indica el máximo de meses cuando el producto permite cuotas")
        if not self.permite_cuotas:
            self.max_meses = None
        if self.precio_lista_credito < self.precio_contado:
            raise ValueError("El precio de lista a crédito no puede ser menor al precio al contado")
        return self


class ProductoCreate(ProductoBase):
    pass


class ProductoUpdate(ProductoBase):
    """Reemplazo completo (PUT): así las reglas entre campos siempre se validan juntas."""


class ProductoOut(ProductoBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tienda_id: int
    estado: str
    created_at: datetime
