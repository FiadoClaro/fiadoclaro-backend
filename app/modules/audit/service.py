from datetime import date, datetime, time, timedelta

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import Actor
from app.modules.audit.models import Bitacora


def registrar(
    db: Session,
    actor: Actor | None,
    accion: str,
    entidad: str,
    entidad_id: int | None = None,
    detalle: dict | None = None,
    tienda_id: int | None = None,
) -> None:
    """Agrega una fila a la bitácora dentro de la misma transacción de la operación."""
    db.add(
        Bitacora(
            usuario_id=actor.id if actor else None,
            tienda_id=tienda_id if tienda_id is not None else (actor.tienda_id if actor else None),
            accion=accion,
            entidad=entidad,
            entidad_id=entidad_id,
            detalle=jsonable_encoder(detalle) if detalle else None,
            ip=actor.ip if actor else None,
        )
    )


def listar(
    db: Session,
    actor: Actor,
    entidad: str | None,
    accion: str | None,
    desde: date | None,
    hasta: date | None,
    limit: int,
    offset: int,
) -> list[Bitacora]:
    q = select(Bitacora)
    if actor.rol == "ADMIN_TIENDA":
        q = q.where(Bitacora.tienda_id == actor.tienda_id)
    if entidad:
        q = q.where(Bitacora.entidad == entidad)
    if accion:
        q = q.where(Bitacora.accion == accion)
    if desde:
        q = q.where(Bitacora.created_at >= datetime.combine(desde, time.min, settings.tz))
    if hasta:
        q = q.where(Bitacora.created_at < datetime.combine(hasta + timedelta(days=1), time.min, settings.tz))
    return list(db.scalars(q.order_by(Bitacora.id.desc()).limit(limit).offset(offset)))
