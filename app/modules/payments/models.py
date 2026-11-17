from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, SmallInteger, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.types import Monto


class Pago(Base):
    """
    Pago TOTAL de un listado de pago (no se aceptan pagos parciales).
    Las columnas mora / compensatorio / capital guardan la imputación por prelación.
    """

    __tablename__ = "pago"
    __table_args__ = (
        CheckConstraint(
            "monto_total = monto_mora + monto_interes + monto_capital", name="imputacion_cuadra"
        ),
        CheckConstraint("dias_mora >= 0", name="dias_mora_no_negativos"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tienda_id: Mapped[int] = mapped_column(ForeignKey("tienda.id"), index=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("cliente.id"), index=True)
    estado_cuenta_id: Mapped[int] = mapped_column(ForeignKey("estado_cuenta.id"), unique=True)
    registrado_por: Mapped[int] = mapped_column(ForeignKey("usuario.id"))
    fecha_pago: Mapped[date] = mapped_column(Date)
    dias_mora: Mapped[int] = mapped_column(SmallInteger, default=0)
    monto_mora: Mapped[Decimal] = mapped_column(Monto)      # 1° en la prelación
    monto_interes: Mapped[Decimal] = mapped_column(Monto)   # 2° interés compensatorio
    monto_capital: Mapped[Decimal] = mapped_column(Monto)   # 3° capital
    monto_total: Mapped[Decimal] = mapped_column(Monto)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
