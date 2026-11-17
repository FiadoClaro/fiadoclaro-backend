from datetime import date
from typing import Literal

from fastapi import APIRouter, Query

from app.core.deps import DbSession, StoreAdmin
from app.modules.statements import service
from app.modules.statements.schemas import EstadoCuentaOut, EstadoCuentaResumen, GeneracionOut, GenerarIn

router = APIRouter(prefix="/statements", tags=["Listados de pago (admin de tienda)"])


@router.post("/generar", response_model=GeneracionOut,
             summary="Generar en la fecha de corte el listado de pago de cada cliente")
def generar(body: GenerarIn, db: DbSession, actor: StoreAdmin):
    """
    Toma a los clientes cuyo día de corte coincide con la fecha indicada y arma su listado
    con las cuotas que vencen en la fecha de pago. Es idempotente: si se vuelve a ejecutar,
    solo agrega lo que falte a los listados pendientes.
    """
    return service.generar(db, actor, body.fecha_corte, body.cliente_id)


@router.get("", response_model=list[EstadoCuentaResumen], summary="Listar listados de pago")
def listar(
    db: DbSession,
    actor: StoreAdmin,
    cliente_id: int | None = None,
    estado: Literal["PENDIENTE", "PAGADO"] | None = None,
    fecha_corte: date | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    return service.listar(db, actor, cliente_id, estado, fecha_corte, limit, offset)


@router.get("/{estado_cuenta_id}", response_model=EstadoCuentaOut,
            summary="Ver el detalle del listado (compras por fecha, intereses y mora)")
def detalle(estado_cuenta_id: int, db: DbSession, actor: StoreAdmin,
            fecha_consulta: date | None = Query(None, description="Para proyectar la mora a otra fecha")):
    return service.detalle(db, service.obtener(db, actor, estado_cuenta_id), fecha_consulta)
