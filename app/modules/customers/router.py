from typing import Literal

from fastapi import APIRouter, Query, status

from app.core.deps import DbSession, StoreAdmin
from app.core.pagination import Pagina
from app.modules.customers import service
from app.modules.customers.schemas import ClienteCreate, ClienteOut, ClienteUpdate, CondicionIn, ResumenCredito

router = APIRouter(prefix="/customers", tags=["Clientes (admin de tienda)"])


@router.post("", response_model=ClienteOut, status_code=status.HTTP_201_CREATED,
             summary="Dar de alta un cliente con sus condiciones de crédito")
def crear(body: ClienteCreate, db: DbSession, actor: StoreAdmin):
    return service.crear(db, actor, body)


@router.get("", response_model=Pagina[ClienteOut],
            summary="Listar la cartera de clientes (con total y conteos por estado)")
def listar(
    db: DbSession,
    actor: StoreAdmin,
    estado: Literal["ACTIVO", "BAJA", "AL_DIA", "EN_MORA"] | None = None,
    q: str | None = Query(None, description="Busca por DNI o nombre"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    return service.listar(db, actor, estado, q, limit, offset)


@router.get("/{cliente_id}", response_model=ClienteOut, summary="Ver un cliente con su resumen de crédito")
def detalle(cliente_id: int, db: DbSession, actor: StoreAdmin):
    return service.to_out(db, service.obtener(db, actor, cliente_id))


@router.get("/{cliente_id}/credito", response_model=ResumenCredito,
            summary="Línea de crédito: límite, utilizado y disponible")
def credito(cliente_id: int, db: DbSession, actor: StoreAdmin):
    return service.resumen_credito(db, service.obtener(db, actor, cliente_id))


@router.patch("/{cliente_id}", response_model=ClienteOut, summary="Editar datos personales")
def actualizar(cliente_id: int, body: ClienteUpdate, db: DbSession, actor: StoreAdmin):
    return service.actualizar(db, actor, cliente_id, body)


@router.put("/{cliente_id}/condicion", response_model=ClienteOut,
            summary="Cambiar condiciones de crédito (solo afecta compras futuras)")
def actualizar_condicion(cliente_id: int, body: CondicionIn, db: DbSession, actor: StoreAdmin):
    return service.actualizar_condicion(db, actor, cliente_id, body)


@router.post("/{cliente_id}/baja", response_model=ClienteOut, summary="Dar de baja un cliente sin deuda")
def baja(cliente_id: int, db: DbSession, actor: StoreAdmin):
    return service.cambiar_estado(db, actor, cliente_id, activar=False)


@router.post("/{cliente_id}/alta", response_model=ClienteOut, summary="Reactivar un cliente")
def alta(cliente_id: int, db: DbSession, actor: StoreAdmin):
    return service.cambiar_estado(db, actor, cliente_id, activar=True)
