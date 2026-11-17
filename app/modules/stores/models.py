import re
import unicodedata
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin


class Tienda(TimestampMixin, Base):
    """Negocio afiliado (bodega, frutería, peluquería...). Varias tiendas operan en la misma plataforma."""

    __tablename__ = "tienda"
    __table_args__ = (
        CheckConstraint("estado IN ('ACTIVA', 'BAJA')", name="estado_valido"),
        CheckConstraint("ruc ~ '^[0-9]{11}$'", name="ruc_11_digitos"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ruc: Mapped[str] = mapped_column(String(11), unique=True)
    razon_social: Mapped[str] = mapped_column(String(150))
    nombre_comercial: Mapped[str] = mapped_column(String(120))
    giro: Mapped[str] = mapped_column(String(40))  # Bodega, Frutería, Peluquería, Spa...
    direccion: Mapped[str | None] = mapped_column(String(200))
    telefono: Mapped[str | None] = mapped_column(String(20))
    correo: Mapped[str | None] = mapped_column(String(120))
    estado: Mapped[str] = mapped_column(String(10), default="ACTIVA")
    fecha_baja: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def dominio_portal(self) -> str:
        """
        Dominio de los usuarios del portal de esta tienda: el usuario de cada vecino es
        <DNI>@<dominio>. Se arma con el nombre comercial sin espacios, tildes ni símbolos.
        Ej.: "Bodega Don Lucho" -> "bodegadonlucho.com".
        """
        sin_tildes = unicodedata.normalize("NFKD", self.nombre_comercial).encode("ascii", "ignore").decode()
        base = re.sub(r"[^a-z0-9]", "", sin_tildes.lower()) or f"tienda{self.id}"
        return f"{base}.com"
