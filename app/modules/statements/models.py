from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.types import TIPOS_TASA, Monto, Tasa, check_in
from app.modules.finance import engine
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
        CheckConstraint(check_in("tipo_tasa_mora", TIPOS_TASA), name="tipo_tasa_mora_valido"),
        # El cliente del listado siempre pertenece a la misma tienda del listado.
        ForeignKeyConstraint(["cliente_id", "tienda_id"], ["cliente.id", "cliente.tienda_id"],
                             name="fk_estado_cuenta_cliente_tienda"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tienda_id: Mapped[int] = mapped_column(ForeignKey("tienda.id"), index=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("cliente.id"), index=True)
    fecha_corte: Mapped[date] = mapped_column(Date)
    fecha_pago: Mapped[date] = mapped_column(Date)
    moneda: Mapped[str] = mapped_column(String(3))

    # Tasa moratoria vigente el día del corte (copia): una sola tasa para el pago total del listado
    # (punto 6: "...al cual se le aplica la tasa de interés moratoria pactada").
    tipo_tasa_mora: Mapped[str] = mapped_column(String(10))
    tasa_mora: Mapped[Decimal] = mapped_column(Tasa)
    periodo_tasa_mora_dias: Mapped[int] = mapped_column(SmallInteger)
    capitalizacion_mora_dias: Mapped[int | None] = mapped_column(SmallInteger)

    total_capital: Mapped[Decimal] = mapped_column(Monto)
    total_interes: Mapped[Decimal] = mapped_column(Monto)
    total_a_pagar: Mapped[Decimal] = mapped_column(Monto)  # sin mora; la mora se calcula al pagar
    estado: Mapped[str] = mapped_column(String(10), default="PENDIENTE")
    generado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    cuotas: Mapped[list[Cuota]] = relationship(order_by=Cuota.fecha_vencimiento)

    @property
    def tasa_moratoria(self) -> engine.Tasa:
        return engine.Tasa(self.tipo_tasa_mora, self.tasa_mora, self.periodo_tasa_mora_dias,
                           self.capitalizacion_mora_dias)
