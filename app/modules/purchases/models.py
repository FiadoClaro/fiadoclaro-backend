from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin
from app.core.types import MODALIDADES, MONEDAS, TIPOS_TASA, Cantidad, Monto, Tasa, TasaDerivada, check_in


class Compra(TimestampMixin, Base):
    """
    Compra fiada. Guarda una COPIA de la tasa pactada (compensatoria y moratoria) vigente
    al momento de la compra, para que cambios posteriores en el cliente no la alteren.
    """

    __tablename__ = "compra"
    __table_args__ = (
        CheckConstraint(check_in("modalidad", MODALIDADES), name="modalidad_valida"),
        CheckConstraint(check_in("moneda", MONEDAS), name="moneda_valida"),
        CheckConstraint(check_in("tipo_tasa", TIPOS_TASA), name="tipo_tasa_valido"),
        CheckConstraint(check_in("tipo_tasa_mora", TIPOS_TASA), name="tipo_tasa_mora_valido"),
        CheckConstraint("estado IN ('VIGENTE', 'CANCELADA', 'ANULADA')", name="estado_valido"),
        CheckConstraint("monto_total > 0", name="monto_positivo"),
        CheckConstraint(
            "(modalidad = 'FIN_MES' AND num_cuotas = 1) OR (modalidad = 'CUOTAS' AND num_cuotas >= 1)",
            name="cuotas_segun_modalidad",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tienda_id: Mapped[int] = mapped_column(ForeignKey("tienda.id"), index=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("cliente.id"), index=True)
    registrado_por: Mapped[int] = mapped_column(ForeignKey("usuario.id"))
    fecha_hora: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    modalidad: Mapped[str] = mapped_column(String(10))
    num_cuotas: Mapped[int] = mapped_column(SmallInteger, default=1)
    moneda: Mapped[str] = mapped_column(String(3))
    monto_total: Mapped[Decimal] = mapped_column(Monto)

    # Ciclo al que pertenece la compra (decidido con la fecha y hora de corte)
    fecha_corte: Mapped[date] = mapped_column(Date)
    fecha_pago: Mapped[date] = mapped_column(Date)
    dias_gracia: Mapped[int] = mapped_column(SmallInteger)  # días entre la compra y la fecha de pago

    # Copia de la tasa pactada (snapshot)
    tipo_tasa: Mapped[str] = mapped_column(String(10))
    tasa: Mapped[Decimal] = mapped_column(Tasa)
    periodo_tasa_dias: Mapped[int] = mapped_column(SmallInteger)
    capitalizacion_dias: Mapped[int | None] = mapped_column(SmallInteger)
    tipo_tasa_mora: Mapped[str] = mapped_column(String(10))
    tasa_mora: Mapped[Decimal] = mapped_column(Tasa)
    periodo_tasa_mora_dias: Mapped[int] = mapped_column(SmallInteger)
    capitalizacion_mora_dias: Mapped[int | None] = mapped_column(SmallInteger)
    tem: Mapped[Decimal] = mapped_column(TasaDerivada)  # TEM equivalente (fracción)
    tea: Mapped[Decimal] = mapped_column(TasaDerivada)  # TEA equivalente (fracción)

    # Resultados del cálculo
    interes_total: Mapped[Decimal] = mapped_column(Monto)  # compensatorio (incluye gracia en cuotas)
    monto_capitalizado: Mapped[Decimal] = mapped_column(Monto)  # = monto_total en FIN_MES
    valor_cuota: Mapped[Decimal] = mapped_column(Monto)
    tcea: Mapped[Decimal | None] = mapped_column(TasaDerivada)
    estado: Mapped[str] = mapped_column(String(10), default="VIGENTE")

    detalles: Mapped[list["CompraDetalle"]] = relationship(
        back_populates="compra", cascade="all, delete-orphan", order_by="CompraDetalle.id"
    )
    cuotas: Mapped[list["Cuota"]] = relationship(
        back_populates="compra", cascade="all, delete-orphan", order_by="Cuota.numero"
    )


class CompraDetalle(Base):
    """Línea de la compra. Copia el precio de lista a crédito vigente al comprar."""

    __tablename__ = "compra_detalle"
    __table_args__ = (CheckConstraint("cantidad > 0", name="cantidad_positiva"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    compra_id: Mapped[int] = mapped_column(ForeignKey("compra.id", ondelete="CASCADE"), index=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey("producto.id"))
    descripcion: Mapped[str] = mapped_column(String(120))
    cantidad: Mapped[Decimal] = mapped_column(Cantidad)
    precio_unitario: Mapped[Decimal] = mapped_column(Monto)
    subtotal: Mapped[Decimal] = mapped_column(Monto)

    compra: Mapped[Compra] = relationship(back_populates="detalles")


class Cuota(Base):
    """
    Obligación de pago de una compra.
    FIN_MES: una sola fila (capital + interés hasta la fecha de pago).
    CUOTAS: una fila por mes según el método francés.
    El listado de pago (estado_cuenta) agrupa las cuotas que vencen en su fecha de pago.
    """

    __tablename__ = "cuota"
    __table_args__ = (CheckConstraint("estado IN ('PENDIENTE', 'PAGADA')", name="estado_valido"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    compra_id: Mapped[int] = mapped_column(ForeignKey("compra.id", ondelete="CASCADE"), index=True)
    numero: Mapped[int] = mapped_column(SmallInteger)
    fecha_vencimiento: Mapped[date] = mapped_column(Date, index=True)
    saldo_inicial: Mapped[Decimal] = mapped_column(Monto)
    interes: Mapped[Decimal] = mapped_column(Monto)
    amortizacion: Mapped[Decimal] = mapped_column(Monto)
    cuota: Mapped[Decimal] = mapped_column(Monto)
    saldo_final: Mapped[Decimal] = mapped_column(Monto)
    estado: Mapped[str] = mapped_column(String(10), default="PENDIENTE")
    estado_cuenta_id: Mapped[int | None] = mapped_column(ForeignKey("estado_cuenta.id"), index=True)

    compra: Mapped[Compra] = relationship(back_populates="cuotas")
