from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, ForeignKeyConstraint, SmallInteger, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.types import Monto


class Pago(Base):
    """
    Pago TOTAL de un listado de pago (no se aceptan pagos parciales).
    Las columnas mora / compensatorio por atraso / compensatorio / capital guardan la imputación por prelación.
    """

    __tablename__ = "pago"
    __table_args__ = (
        CheckConstraint(
            "monto_total = monto_mora + monto_interes_comp_mora + monto_interes + monto_capital",
            name="imputacion_cuadra",
        ),
        CheckConstraint("dias_mora >= 0", name="dias_mora_no_negativos"),
        # El cliente del pago siempre pertenece a la misma tienda del pago.
        ForeignKeyConstraint(["cliente_id", "tienda_id"], ["cliente.id", "cliente.tienda_id"],
                             name="fk_pago_cliente_tienda"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tienda_id: Mapped[int] = mapped_column(ForeignKey("tienda.id"), index=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("cliente.id"), index=True)
    estado_cuenta_id: Mapped[int] = mapped_column(ForeignKey("estado_cuenta.id"), unique=True)
    registrado_por: Mapped[int] = mapped_column(ForeignKey("usuario.id"))
    fecha_pago: Mapped[date] = mapped_column(Date)
    dias_mora: Mapped[int] = mapped_column(SmallInteger, default=0)
    monto_mora: Mapped[Decimal] = mapped_column(Monto)      # 1° interés moratorio
    monto_interes_comp_mora: Mapped[Decimal] = mapped_column(Monto, default=0)  # 2° compensatorio por días de atraso
    monto_interes: Mapped[Decimal] = mapped_column(Monto)   # 3° interés compensatorio del listado
    monto_capital: Mapped[Decimal] = mapped_column(Monto)   # 4° capital
    monto_total: Mapped[Decimal] = mapped_column(Monto)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
