from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin
from app.core.types import MONEDAS, Tasa, check_in


class TopeTasa(TimestampMixin, Base):
    """
    Tope máximo de TEA del BCRP para operaciones entre personas ajenas al sistema financiero
    (art. 1243 del Código Civil; Circular N° 0008-2021-BCRP). Hay un valor por tipo de tasa y por moneda,
    y se guarda con su fecha de vigencia porque el BCRP lo recalcula cada semestre (mayo y noviembre).
    La moratoria máxima es el 15 % de la compensatoria máxima.
    """

    __tablename__ = "tope_tasa"
    __table_args__ = (
        CheckConstraint("tipo IN ('COMPENSATORIA', 'MORATORIA')", name="tipo_valido"),
        CheckConstraint("tea_maxima > 0", name="tea_positiva"),
        CheckConstraint(check_in("moneda", MONEDAS), name="moneda_valida"),
        UniqueConstraint("tipo", "moneda", "vigente_desde", name="uq_tope_tipo_moneda_vigencia"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(String(15))
    moneda: Mapped[str] = mapped_column(String(3), default="PEN")
    tea_maxima: Mapped[Decimal] = mapped_column(Tasa)  # en porcentaje
    vigente_desde: Mapped[date] = mapped_column(Date)
    fuente: Mapped[str | None] = mapped_column(String(200))
