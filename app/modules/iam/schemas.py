import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

# Usuario: letras, números, punto, guion, guion bajo y @ (los vecinos usan "<DNI>@<dominio de la tienda>").
PATRON_USUARIO = r"^[a-zA-Z0-9._@-]+$"
FORMATO_CORREO = re.compile(r"^[^@\s]+@[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}$")


def normalizar_usuario(v):
    """Sin espacios y en minúsculas; si tiene @, debe tener forma de correo (nombre@dominio.com)."""
    if not isinstance(v, str):
        return v
    v = v.strip().lower()
    if "@" in v and not FORMATO_CORREO.match(v):
        raise ValueError("El usuario con @ debe tener forma de correo, por ejemplo 08765432@bodegadonlucho.com")
    return v


class Credenciales(BaseModel):
    """Usuario y contraseña del administrador de una tienda."""

    username: str = Field(min_length=4, max_length=60, pattern=PATRON_USUARIO,
                          description="Usuario de acceso: letras, números, punto, guion, guion bajo o @")
    password: str = Field(min_length=8, max_length=72, description="Mínimo 8 caracteres")

    @field_validator("username", mode="before")
    @classmethod
    def validar_usuario(cls, v: str) -> str:
        return normalizar_usuario(v)


class AccesoCliente(BaseModel):
    """
    Acceso del vecino al portal. El usuario es su DNI seguido del dominio de la tienda
    (ej. 08765432@bodegadonlucho.com). Si no se envía, el sistema lo arma solo.
    El vecino puede cambiar la contraseña desde su perfil.
    """

    username: str | None = Field(None, min_length=4, max_length=60, pattern=PATRON_USUARIO,
                                 description="Opcional. Por defecto <DNI>@<dominio de la tienda>")
    password: str = Field(min_length=8, max_length=72, description="Contraseña provisional, mínimo 8 caracteres")

    @field_validator("username", mode="before")
    @classmethod
    def validar_usuario(cls, v: str | None) -> str | None:
        return normalizar_usuario(v) if v else None


class UsuarioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    nombre: str
    rol: str
    tienda_id: int | None
    telefono: str | None = None
    correo: str | None = None
    foto_url: str | None = None
    activo: bool
    ultimo_acceso: datetime | None = None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    usuario: UsuarioOut


class CambioPassword(BaseModel):
    password_actual: str = Field(min_length=1)
    password_nueva: str = Field(min_length=8, max_length=72)
    confirmacion: str | None = Field(None, description="Opcional: si se envía, debe coincidir con la nueva")

    @model_validator(mode="after")
    def _coherencia(self):
        if self.confirmacion is not None and self.confirmacion != self.password_nueva:
            raise ValueError("La confirmación no coincide con la nueva contraseña")
        if self.password_nueva == self.password_actual:
            raise ValueError("La nueva contraseña debe ser distinta a la actual")
        return self


class PerfilUpdate(BaseModel):
    """Datos que cada usuario puede editar en su perfil."""

    nombre: str | None = Field(None, min_length=2, max_length=120,
                               description="Solo administradores; el nombre del vecino lo administra la tienda")
    telefono: str | None = Field(None, max_length=20)
    correo: EmailStr | None = None
    foto_url: str | None = Field(None, max_length=500,
                                 description="Enlace http(s) a la foto de perfil; null la quita")

    @field_validator("foto_url")
    @classmethod
    def _foto_es_enlace(cls, v: str | None) -> str | None:
        # No se suben archivos: solo se guarda el enlace a una imagen ya publicada.
        if v is None or not v.strip():
            return None
        v = v.strip()
        if not v.lower().startswith(("http://", "https://")):
            raise ValueError("La foto debe ser un enlace que empiece con http:// o https://")
        return v
