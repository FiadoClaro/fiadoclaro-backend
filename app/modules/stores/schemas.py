from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.modules.iam.schemas import Credenciales


class TiendaBase(BaseModel):
    razon_social: str = Field(min_length=2, max_length=150)
    nombre_comercial: str = Field(min_length=2, max_length=120)
    giro: str = Field(min_length=2, max_length=40, description="Bodega, Frutería, Carnicería, Peluquería, Spa...")
    direccion: str | None = Field(None, max_length=200)
    telefono: str | None = Field(None, max_length=20)
    correo: EmailStr | None = None


class AdminTiendaIn(Credenciales):
    """Administrador / representante del negocio que se crea junto con la tienda."""

    nombre: str = Field(min_length=2, max_length=120, description="Nombre del administrador del negocio")
    telefono: str = Field(min_length=6, max_length=20, description="Teléfono celular personal")
    correo: EmailStr = Field(description="Correo electrónico personal")


class TiendaCreate(TiendaBase):
    ruc: str = Field(pattern=r"^\d{11}$", description="RUC de 11 dígitos")
    administrador: AdminTiendaIn


class AdministradorUpdate(BaseModel):
    nombre: str | None = Field(None, min_length=2, max_length=120)
    telefono: str | None = Field(None, min_length=6, max_length=20)
    correo: EmailStr | None = None


class TiendaUpdate(BaseModel):
    """Lo que puede editar el administrador del sistema (el RUC no se cambia)."""

    razon_social: str | None = Field(None, min_length=2, max_length=150)
    nombre_comercial: str | None = Field(None, min_length=2, max_length=120)
    giro: str | None = Field(None, min_length=2, max_length=40)
    direccion: str | None = Field(None, max_length=200)
    telefono: str | None = Field(None, max_length=20)
    correo: EmailStr | None = None
    administrador: AdministradorUpdate | None = Field(None, description="Datos de contacto del administrador")


class MiTiendaUpdate(BaseModel):
    """Lo que el administrador de la tienda puede editar de su propio negocio (el RUC no se cambia)."""

    razon_social: str | None = Field(None, min_length=2, max_length=150)
    nombre_comercial: str | None = Field(None, min_length=2, max_length=120)
    giro: str | None = Field(None, min_length=2, max_length=40)
    direccion: str | None = Field(None, max_length=200)
    telefono: str | None = Field(None, max_length=20)
    correo: EmailStr | None = None


class AdministradorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    nombre: str
    telefono: str | None
    correo: str | None
    activo: bool
    ultimo_acceso: datetime | None


class TiendaOut(TiendaBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ruc: str
    estado: str
    created_at: datetime
    updated_at: datetime
    fecha_baja: datetime | None
    dominio_portal: str = Field(description="Dominio del usuario de los vecinos: <DNI>@<dominio_portal>")
    administrador: AdministradorOut | None = None
