from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.modules.iam.schemas import Credenciales


class TiendaBase(BaseModel):
    razon_social: str = Field(min_length=2, max_length=150)
    nombre_comercial: str = Field(min_length=2, max_length=120)
    giro: str = Field(min_length=2, max_length=40, description="Bodega, Frutería, Carnicería, Peluquería, Spa...")
    direccion: str | None = Field(None, max_length=200)
    distrito: str | None = Field(None, max_length=80)
    telefono: str | None = Field(None, max_length=20)
    correo: EmailStr | None = None


class AdminTiendaIn(Credenciales):
    nombre: str = Field(min_length=2, max_length=120, description="Nombre del administrador del negocio")


class TiendaCreate(TiendaBase):
    ruc: str = Field(pattern=r"^\d{11}$", description="RUC de 11 dígitos")
    administrador: AdminTiendaIn


class TiendaUpdate(BaseModel):
    razon_social: str | None = Field(None, min_length=2, max_length=150)
    nombre_comercial: str | None = Field(None, min_length=2, max_length=120)
    giro: str | None = Field(None, min_length=2, max_length=40)
    direccion: str | None = Field(None, max_length=200)
    distrito: str | None = Field(None, max_length=80)
    telefono: str | None = Field(None, max_length=20)
    correo: EmailStr | None = None


class TiendaOut(TiendaBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ruc: str
    estado: str
    created_at: datetime
    fecha_baja: datetime | None
    administrador: str | None = None
