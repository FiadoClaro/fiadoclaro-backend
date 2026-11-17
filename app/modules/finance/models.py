from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin
from app.core.types import Tasa


class TopeTasa(TimestampMixin, Base):
    """
    Tope máximo de TEA (BCRP) para tasas compensatorias y moratorias.
    Se guarda con fecha de vigencia porque el BCRP lo actualiza cada semestre.
    """

    __tablename__ = "tope_tasa"
    __table_args__ = (
        CheckConstraint("tipo IN ('COMPENSATORIA', 'MORATORIA')", name="tipo_valido"),
        CheckConstraint("tea_maxima > 0", name="tea_positiva"),
        UniqueConstraint("tipo", "vigente_desde", name="uq_tope_tipo_vigencia"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(String(15))
    tea_maxima: Mapped[Decimal] = mapped_column(Tasa)  # en porcentaje
    vigente_desde: Mapped[date] = mapped_column(Date)
    fuente: Mapped[str | None] = mapped_column(String(200))
