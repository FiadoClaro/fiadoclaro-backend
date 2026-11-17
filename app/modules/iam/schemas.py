from pydantic import BaseModel, ConfigDict, Field


class Credenciales(BaseModel):
    """Usuario y contraseña que se crean junto con la tienda o el cliente."""

    username: str = Field(min_length=4, max_length=60, pattern=r"^[a-zA-Z0-9._-]+$",
                          description="Usuario de acceso; solo letras, números, punto, guion")
    password: str = Field(min_length=8, max_length=72, description="Mínimo 8 caracteres")


class UsuarioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    nombre: str
    rol: str
    tienda_id: int | None
    activo: bool


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    usuario: UsuarioOut


class CambioPassword(BaseModel):
    password_actual: str
    password_nueva: str = Field(min_length=8, max_length=72)
