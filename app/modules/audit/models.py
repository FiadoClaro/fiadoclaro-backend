from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Bitacora(Base):
    """Registro de todas las operaciones realizadas (exigido por el enunciado, punto 9)."""

    __tablename__ = "bitacora"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), index=True)
    tienda_id: Mapped[int | None] = mapped_column(ForeignKey("tienda.id"), index=True)
    accion: Mapped[str] = mapped_column(String(40))        # CREAR, ACTUALIZAR, BAJA, LOGIN, PAGO...
    entidad: Mapped[str] = mapped_column(String(40))       # tienda, cliente, compra...
    entidad_id: Mapped[int | None] = mapped_column(BigInteger)
    detalle: Mapped[dict | None] = mapped_column(JSONB)
    ip: Mapped[str | None] = mapped_column(String(45))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
