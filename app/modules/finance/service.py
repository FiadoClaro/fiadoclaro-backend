from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import Actor
from app.core.errors import BusinessError, ConflictError
from app.modules.audit.service import registrar
from app.modules.finance import engine
from app.modules.finance.models import TopeTasa
from app.modules.finance.schemas import TopeIn


def tope_vigente(db: Session, tipo: str, moneda: str, fecha: date) -> Decimal | None:
    """TEA máxima del tipo y la moneda, vigente a la fecha (la publicación más reciente que ya rige)."""
    return db.scalar(
        select(TopeTasa.tea_maxima)
        .where(TopeTasa.tipo == tipo, TopeTasa.moneda == moneda, TopeTasa.vigente_desde <= fecha)
        .order_by(TopeTasa.vigente_desde.desc())
        .limit(1)
    )


def validar_topes(db: Session, compensatoria: engine.Tasa, moratoria: engine.Tasa, fecha: date,
                  moneda: str) -> None:
    """Rechaza tasas cuya TEA supere el tope del BCRP vigente a la fecha, en la moneda del crédito."""
    for tipo, tasa, nombre in (
        ("COMPENSATORIA", compensatoria, "tasa compensatoria"),
        ("MORATORIA", moratoria, "tasa moratoria"),
    ):
        tope = tope_vigente(db, tipo, moneda, fecha)
        if tope is None:
            nombre_moneda = "soles" if moneda == "PEN" else "dólares"
            raise BusinessError(f"No hay un tope de tasa {tipo.lower()} en {nombre_moneda} vigente al {fecha}",
                                code="sin_tope")
        try:
            engine.validar_tope(tasa, tope, nombre)
        except ValueError as e:
            raise BusinessError(str(e), code="tasa_supera_tope") from e


def listar_topes(db: Session) -> list[TopeTasa]:
    return list(db.scalars(select(TopeTasa).order_by(TopeTasa.vigente_desde.desc(), TopeTasa.moneda,
                                                     TopeTasa.tipo)))


def crear_tope(db: Session, actor: Actor, data: TopeIn) -> TopeTasa:
    if db.scalar(select(TopeTasa.id).where(TopeTasa.tipo == data.tipo, TopeTasa.moneda == data.moneda,
                                           TopeTasa.vigente_desde == data.vigente_desde)):
        raise ConflictError("Ya existe un tope de ese tipo y moneda con esa fecha de vigencia")
    tope = TopeTasa(**data.model_dump())
    db.add(tope)
    db.flush()
    registrar(db, actor, "CREAR", "tope_tasa", tope.id, data.model_dump())
    db.commit()
    return tope
