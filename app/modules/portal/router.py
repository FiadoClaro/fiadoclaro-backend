"""
Portal del vecino (rol CLIENTE): consulta de su cuenta, compras y listados.
Solo lectura; reutiliza los servicios de los demás módulos, siempre filtrando por SU cliente.
"""
from fastapi import APIRouter
from sqlalchemy import select

from app.core.deps import CustomerUser, DbSession
from app.core.errors import NotFoundError
from app.modules.customers import service as customers
from app.modules.customers.models import Cliente
from app.modules.customers.schemas import ClienteOut
from app.modules.portal import service as portal
from app.modules.portal.schemas import PortalResumenOut
from app.modules.purchases import service as purchases
from app.modules.purchases.models import Compra
from app.modules.purchases.schemas import CompraOut, CompraResumenOut
from app.modules.statements import service as statements
from app.modules.statements.models import EstadoCuenta
from app.modules.statements.schemas import EstadoCuentaOut, EstadoCuentaResumen

router = APIRouter(prefix="/portal", tags=["Portal del cliente"])


def _mi_cliente(db, actor) -> Cliente:
    cliente = db.scalar(select(Cliente).where(Cliente.usuario_id == actor.id))
    if not cliente:
        raise NotFoundError("Cliente")
    statements.asegurar_listados(db, cliente.tienda_id, cliente.id)  # listados de los cortes ya pasados
    return cliente


@router.get("/resumen", response_model=PortalResumenOut,
            summary="Mi estado de cuenta: saldo, mora, próxima fecha, compras y cuotas (todo calculado)")
def mi_resumen(db: DbSession, actor: CustomerUser):
    return portal.resumen(db, _mi_cliente(db, actor))


@router.get("/me", response_model=ClienteOut, summary="Mis datos, condiciones y crédito disponible")
def me(db: DbSession, actor: CustomerUser):
    return customers.to_out(db, _mi_cliente(db, actor))


@router.get("/compras", response_model=list[CompraResumenOut], summary="Mis compras fiadas")
def mis_compras(db: DbSession, actor: CustomerUser):
    return purchases.listar(db, actor, None, None, None, None, 200, 0).items


@router.get("/compras/{compra_id}", response_model=CompraOut, summary="Detalle y cronograma de mi compra")
def mi_compra(compra_id: int, db: DbSession, actor: CustomerUser):
    compra = db.get(Compra, compra_id)
    if not compra or compra.cliente_id != _mi_cliente(db, actor).id:
        raise NotFoundError("Compra", compra_id)
    return purchases.to_out(compra)


@router.get("/listados", response_model=list[EstadoCuentaResumen], summary="Mis listados de pago")
def mis_listados(db: DbSession, actor: CustomerUser):
    return statements.listar(db, actor, _mi_cliente(db, actor).id, None, None, 200, 0).items


@router.get("/listados/{estado_cuenta_id}", response_model=EstadoCuentaOut,
            summary="Detalle de mi listado (incluye la mora si estoy atrasado)")
def mi_listado(estado_cuenta_id: int, db: DbSession, actor: CustomerUser):
    ec = db.get(EstadoCuenta, estado_cuenta_id)
    if not ec or ec.cliente_id != _mi_cliente(db, actor).id:
        raise NotFoundError("Listado de pago", estado_cuenta_id)
    return statements.detalle(db, ec)
