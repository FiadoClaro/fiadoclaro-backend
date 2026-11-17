from datetime import datetime, time
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, SmallInteger, String, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin
from app.core.types import MONEDAS, TIPOS_TASA, Monto, Tasa, check_in


class Cliente(TimestampMixin, Base):
    """Vecino al que la tienda le fía. Su acceso al portal es un usuario con rol CLIENTE."""

    __tablename__ = "cliente"
    __table_args__ = (
        UniqueConstraint("tienda_id", "dni", name="uq_cliente_tienda_dni"),
        # Soporte de las FK compuestas (cliente_id, tienda_id) de compra, estado_cuenta y pago.
        UniqueConstraint("id", "tienda_id", name="uq_cliente_id_tienda"),
        CheckConstraint("dni ~ '^[0-9]{8}$'", name="dni_8_digitos"),
        CheckConstraint("estado IN ('ACTIVO', 'BAJA')", name="estado_valido"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tienda_id: Mapped[int] = mapped_column(ForeignKey("tienda.id"), index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"), unique=True)
    dni: Mapped[str] = mapped_column(String(8))
    nombres: Mapped[str] = mapped_column(String(80))
    apellidos: Mapped[str] = mapped_column(String(80))
    telefono: Mapped[str | None] = mapped_column(String(20))
    correo: Mapped[str | None] = mapped_column(String(120))
    direccion: Mapped[str | None] = mapped_column(String(200))
    estado: Mapped[str] = mapped_column(String(10), default="ACTIVO")
    fecha_baja: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    condicion: Mapped["CondicionCredito"] = relationship(
        back_populates="cliente", uselist=False, cascade="all, delete-orphan", lazy="joined"
    )


class CondicionCredito(TimestampMixin, Base):
    """
    Condiciones VIGENTES del fiado de un cliente (relación 1 a 1).
    Cada compra copia la tasa al registrarse, así un cambio aquí no altera compras anteriores.
    """

    __tablename__ = "condicion_credito"
    __table_args__ = (
        CheckConstraint(check_in("moneda", MONEDAS), name="moneda_valida"),
        CheckConstraint(check_in("tipo_tasa", TIPOS_TASA), name="tipo_tasa_valido"),
        CheckConstraint(check_in("tipo_tasa_mora", TIPOS_TASA), name="tipo_tasa_mora_valido"),
        CheckConstraint("tasa >= 0 AND tasa_mora >= 0", name="tasas_no_negativas"),
        CheckConstraint("limite_credito > 0", name="limite_positivo"),
        CheckConstraint("max_meses BETWEEN 1 AND 36", name="max_meses_rango"),
        CheckConstraint("dia_corte BETWEEN 1 AND 28 AND dia_pago BETWEEN 1 AND 28", name="dias_rango"),
        CheckConstraint("dia_corte <> dia_pago", name="corte_distinto_pago"),
    )

    cliente_id: Mapped[int] = mapped_column(ForeignKey("cliente.id", ondelete="CASCADE"), primary_key=True)
    moneda: Mapped[str] = mapped_column(String(3), default="PEN")

    # Tasa compensatoria pactada
    tipo_tasa: Mapped[str] = mapped_column(String(10))
    tasa: Mapped[Decimal] = mapped_column(Tasa)
    periodo_tasa_dias: Mapped[int] = mapped_column(SmallInteger)
    capitalizacion_dias: Mapped[int | None] = mapped_column(SmallInteger)  # solo si es nominal

    # Tasa moratoria pactada
    tipo_tasa_mora: Mapped[str] = mapped_column(String(10))
    tasa_mora: Mapped[Decimal] = mapped_column(Tasa)
    periodo_tasa_mora_dias: Mapped[int] = mapped_column(SmallInteger)
    capitalizacion_mora_dias: Mapped[int | None] = mapped_column(SmallInteger)

    limite_credito: Mapped[Decimal] = mapped_column(Monto)
    max_meses: Mapped[int] = mapped_column(SmallInteger)
    dia_corte: Mapped[int] = mapped_column(SmallInteger)
    hora_corte: Mapped[time] = mapped_column(Time, default=time(18, 0))
    dia_pago: Mapped[int] = mapped_column(SmallInteger)

    cliente: Mapped[Cliente] = relationship(back_populates="condicion")
