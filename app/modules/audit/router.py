from datetime import date, datetime

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict

from app.core.deps import AnyAdmin, DbSession
from app.core.pagination import Pagina
from app.modules.audit import service

router = APIRouter(prefix="/audit", tags=["Bitácora"])


class BitacoraOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    usuario_id: int | None
    tienda_id: int | None
    accion: str
    entidad: str
    entidad_id: int | None
    detalle: dict | None
    ip: str | None
    created_at: datetime


@router.get("", response_model=Pagina[BitacoraOut], summary="Listar operaciones registradas (con total)")
def listar(
    db: DbSession,
    actor: AnyAdmin,
    entidad: str | None = None,
    accion: str | None = None,
    desde: date | None = None,
    hasta: date | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """El admin del sistema ve todo; el admin de tienda solo su tienda."""
    return service.listar(db, actor, entidad, accion, desde, hasta, limit, offset)
