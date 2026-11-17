from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, SmallInteger, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin
from app.core.types import MONEDAS, Monto, check_in


class Producto(TimestampMixin, Base):
    """Producto o servicio del catálogo de una tienda."""

    __tablename__ = "producto"
    __table_args__ = (
        UniqueConstraint("tienda_id", "codigo", name="uq_producto_tienda_codigo"),
        CheckConstraint(check_in("moneda", MONEDAS), name="moneda_valida"),
        CheckConstraint("precio_contado > 0 AND precio_lista_credito > 0", name="precios_positivos"),
        CheckConstraint("permite_fin_mes OR permite_cuotas", name="alguna_modalidad"),
        CheckConstraint(
            "(permite_cuotas AND max_meses BETWEEN 1 AND 36) OR (NOT permite_cuotas AND max_meses IS NULL)",
            name="max_meses_segun_cuotas",
        ),
        CheckConstraint("estado IN ('ACTIVO', 'BAJA')", name="estado_valido"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tienda_id: Mapped[int] = mapped_column(ForeignKey("tienda.id"), index=True)
    codigo: Mapped[str] = mapped_column(String(30))  # SKU
    nombre: Mapped[str] = mapped_column(String(120))
    descripcion: Mapped[str | None] = mapped_column(String(300))
    marca: Mapped[str | None] = mapped_column(String(60))
    proveedor: Mapped[str | None] = mapped_column(String(120))
    unidad_medida: Mapped[str] = mapped_column(String(20))
    imagen_url: Mapped[str | None] = mapped_column(String(500))
    moneda: Mapped[str] = mapped_column(String(3), default="PEN")
    precio_contado: Mapped[Decimal] = mapped_column(Monto)
    precio_lista_credito: Mapped[Decimal] = mapped_column(Monto)
    permite_fin_mes: Mapped[bool] = mapped_column(Boolean, default=True)
    permite_cuotas: Mapped[bool] = mapped_column(Boolean, default=False)
    max_meses: Mapped[int | None] = mapped_column(SmallInteger)  # máximo de meses por producto
    estado: Mapped[str] = mapped_column(String(10), default="ACTIVO")
