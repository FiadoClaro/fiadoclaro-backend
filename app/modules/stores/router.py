from typing import Literal

from fastapi import APIRouter, Query, status

from app.core.deps import DbSession, SystemAdmin
from app.modules.stores import service
from app.modules.stores.schemas import TiendaCreate, TiendaOut, TiendaUpdate

router = APIRouter(prefix="/stores", tags=["Tiendas (admin del sistema)"])


@router.post("", response_model=TiendaOut, status_code=status.HTTP_201_CREATED,
             summary="Dar de alta una tienda y su administrador")
def crear(body: TiendaCreate, db: DbSession, actor: SystemAdmin):
    return service.crear(db, actor, body)


@router.get("", response_model=list[TiendaOut], summary="Listar tiendas afiliadas")
def listar(
    db: DbSession,
    actor: SystemAdmin,
    estado: Literal["ACTIVA", "BAJA"] | None = None,
    giro: str | None = None,
    q: str | None = Query(None, description="Busca por nombre comercial, RUC o distrito"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    return service.listar(db, estado, giro, q, limit, offset)


@router.get("/{tienda_id}", response_model=TiendaOut, summary="Ver una tienda")
def detalle(tienda_id: int, db: DbSession, actor: SystemAdmin):
    return service.detalle(db, tienda_id)


@router.patch("/{tienda_id}", response_model=TiendaOut, summary="Editar datos de una tienda")
def actualizar(tienda_id: int, body: TiendaUpdate, db: DbSession, actor: SystemAdmin):
    return service.actualizar(db, actor, tienda_id, body)


@router.post("/{tienda_id}/baja", response_model=TiendaOut, summary="Dar de baja una tienda")
def baja(tienda_id: int, db: DbSession, actor: SystemAdmin):
    return service.cambiar_estado(db, actor, tienda_id, activar=False)


@router.post("/{tienda_id}/alta", response_model=TiendaOut, summary="Reactivar una tienda")
def alta(tienda_id: int, db: DbSession, actor: SystemAdmin):
    return service.cambiar_estado(db, actor, tienda_id, activar=True)
