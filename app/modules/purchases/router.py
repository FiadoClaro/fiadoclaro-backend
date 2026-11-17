from datetime import date
from typing import Literal

from fastapi import APIRouter, Query, status

from app.core.deps import DbSession, StoreAdmin
from app.modules.purchases import service
from app.modules.purchases.schemas import CompraIn, CompraOut, CompraResumenOut, SimulacionOut

router = APIRouter(prefix="/purchases", tags=["Compras fiadas (admin de tienda)"])


@router.post("/simular", response_model=SimulacionOut,
             summary="Calcular una compra sin registrarla (ciclo, interés, cuotas, TCEA)")
def simular(body: CompraIn, db: DbSession, actor: StoreAdmin):
    return service.simular(db, actor, body)


@router.post("", response_model=CompraOut, status_code=status.HTTP_201_CREATED,
             summary="Registrar una compra a fin de mes o en cuotas")
def registrar(body: CompraIn, db: DbSession, actor: StoreAdmin):
    return service.registrar_compra(db, actor, body)


@router.get("", response_model=list[CompraResumenOut], summary="Listar compras")
def listar(
    db: DbSession,
    actor: StoreAdmin,
    cliente_id: int | None = None,
    estado: Literal["VIGENTE", "CANCELADA", "ANULADA"] | None = None,
    desde: date | None = None,
    hasta: date | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    return service.listar(db, actor, cliente_id, estado, desde, hasta, limit, offset)


@router.get("/{compra_id}", response_model=CompraOut, summary="Ver una compra con su cronograma")
def detalle(compra_id: int, db: DbSession, actor: StoreAdmin):
    return service.to_out(service.obtener(db, actor, compra_id))
