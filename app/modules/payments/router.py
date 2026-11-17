from datetime import date

from fastapi import APIRouter, Query, status

from app.core.deps import DbSession, StoreAdmin
from app.modules.payments import service
from app.modules.payments.schemas import CotizacionOut, PagoIn, PagoOut

router = APIRouter(prefix="/payments", tags=["Pagos (admin de tienda)"])


@router.get("/cotizar/{estado_cuenta_id}", response_model=CotizacionOut,
            summary="Calcular el total exigible a una fecha (con mora y prelación)")
def cotizar(estado_cuenta_id: int, db: DbSession, actor: StoreAdmin,
            fecha_pago: date | None = Query(None, description="Por defecto, hoy")):
    return service.cotizar(db, actor, estado_cuenta_id, fecha_pago)


@router.post("", response_model=PagoOut, status_code=status.HTTP_201_CREATED,
             summary="Registrar el pago total de un listado")
def registrar(body: PagoIn, db: DbSession, actor: StoreAdmin):
    return service.registrar_pago(db, actor, body)


@router.get("", response_model=list[PagoOut], summary="Listar pagos")
def listar(db: DbSession, actor: StoreAdmin, cliente_id: int | None = None,
           limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    return service.listar(db, actor, cliente_id, limit, offset)


@router.get("/{pago_id}", response_model=PagoOut, summary="Ver un pago con su imputación")
def detalle(pago_id: int, db: DbSession, actor: StoreAdmin):
    return service.to_out(service.obtener(db, actor, pago_id))
