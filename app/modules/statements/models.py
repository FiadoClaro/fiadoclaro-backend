from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.types import Monto
from app.modules.purchases.models import Cuota


class EstadoCuenta(Base):
    """
    Listado de pago generado en la FECHA DE CORTE (punto 6 del enunciado).
    Agrupa las cuotas del cliente que vencen en la fecha de pago de ese ciclo.
    """

    __tablename__ = "estado_cuenta"
    __table_args__ = (
        UniqueConstraint("cliente_id", "fecha_corte", name="uq_estado_cuenta_cliente_corte"),
        CheckConstraint("estado IN ('PENDIENTE', 'PAGADO')", name="estado_valido"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tienda_id: Mapped[int] = mapped_column(ForeignKey("tienda.id"), index=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("cliente.id"), index=True)
    fecha_corte: Mapped[date] = mapped_column(Date)
    fecha_pago: Mapped[date] = mapped_column(Date)
    moneda: Mapped[str] = mapped_column(String(3))
    total_capital: Mapped[Decimal] = mapped_column(Monto)
    total_interes: Mapped[Decimal] = mapped_column(Monto)
    total_a_pagar: Mapped[Decimal] = mapped_column(Monto)  # sin mora; la mora se calcula al pagar
    estado: Mapped[str] = mapped_column(String(10), default="PENDIENTE")
    generado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    cuotas: Mapped[list[Cuota]] = relationship(order_by=Cuota.fecha_vencimiento)
