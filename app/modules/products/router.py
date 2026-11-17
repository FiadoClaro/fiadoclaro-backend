from typing import Literal

from fastapi import APIRouter, Query, status

from app.core.deps import DbSession, StoreAdmin
from app.modules.products import service
from app.modules.products.schemas import ProductoCreate, ProductoOut, ProductoUpdate

router = APIRouter(prefix="/products", tags=["Productos y servicios (admin de tienda)"])


@router.post("", response_model=ProductoOut, status_code=status.HTTP_201_CREATED,
             summary="Dar de alta un producto o servicio")
def crear(body: ProductoCreate, db: DbSession, actor: StoreAdmin):
    return service.crear(db, actor, body)


@router.get("", response_model=list[ProductoOut], summary="Listar el catálogo")
def listar(
    db: DbSession,
    actor: StoreAdmin,
    estado: Literal["ACTIVO", "BAJA"] | None = None,
    modalidad: Literal["FIN_MES", "CUOTAS"] | None = None,
    q: str | None = Query(None, description="Busca por nombre, código o marca"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    return service.listar(db, actor, estado, q, modalidad, limit, offset)


@router.get("/{producto_id}", response_model=ProductoOut, summary="Ver un producto")
def detalle(producto_id: int, db: DbSession, actor: StoreAdmin):
    return service.obtener(db, actor, producto_id)


@router.put("/{producto_id}", response_model=ProductoOut, summary="Editar un producto")
def actualizar(producto_id: int, body: ProductoUpdate, db: DbSession, actor: StoreAdmin):
    return service.actualizar(db, actor, producto_id, body)


@router.post("/{producto_id}/baja", response_model=ProductoOut, summary="Dar de baja un producto")
def baja(producto_id: int, db: DbSession, actor: StoreAdmin):
    return service.cambiar_estado(db, actor, producto_id, activar=False)


@router.post("/{producto_id}/alta", response_model=ProductoOut, summary="Reactivar un producto")
def alta(producto_id: int, db: DbSession, actor: StoreAdmin):
    return service.cambiar_estado(db, actor, producto_id, activar=True)
