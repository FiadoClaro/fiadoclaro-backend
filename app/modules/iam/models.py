from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin
from app.core.types import ROLES, check_in


class Usuario(TimestampMixin, Base):
    """Credenciales de acceso. Un usuario es administrador del sistema, de una tienda o cliente (vecino)."""

    __tablename__ = "usuario"
    __table_args__ = (
        CheckConstraint(check_in("rol", ROLES), name="rol_valido"),
        # El admin del sistema no pertenece a ninguna tienda; los demás sí.
        CheckConstraint(
            "(rol = 'ADMIN_SISTEMA' AND tienda_id IS NULL) OR (rol <> 'ADMIN_SISTEMA' AND tienda_id IS NOT NULL)",
            name="tienda_segun_rol",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(60), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    rol: Mapped[str] = mapped_column(String(20))
    tienda_id: Mapped[int | None] = mapped_column(ForeignKey("tienda.id"), index=True)
    nombre: Mapped[str] = mapped_column(String(120))
    telefono: Mapped[str | None] = mapped_column(String(20))   # contacto personal (perfil)
    correo: Mapped[str | None] = mapped_column(String(120))    # contacto personal (perfil)
    foto_url: Mapped[str | None] = mapped_column(String(500))  # enlace a la foto de perfil (no se sube archivo)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    ultimo_acceso: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
