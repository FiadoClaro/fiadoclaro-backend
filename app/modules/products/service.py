from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.deps import Actor
from app.core.errors import BusinessError, NotFoundError
from app.core.pagination import Pagina, contar_por, paginar
from app.modules.audit.service import registrar
from app.modules.products.models import Producto
from app.modules.products.schemas import ProductoCreate, ProductoUpdate


def obtener(db: Session, actor: Actor, producto_id: int) -> Producto:
    p = db.get(Producto, producto_id)
    if not p or p.tienda_id != actor.tienda_id:
        raise NotFoundError("Producto", producto_id)
    return p


def crear(db: Session, actor: Actor, data: ProductoCreate) -> Producto:
    p = Producto(tienda_id=actor.tienda_id, estado="ACTIVO", **data.model_dump())
    db.add(p)
    db.flush()
    registrar(db, actor, "CREAR", "producto", p.id, data.model_dump())
    db.commit()
    return p


def listar(db: Session, actor: Actor, estado: str | None, q: str | None, modalidad: str | None,
           limit: int, offset: int) -> Pagina:
    stmt = select(Producto).where(Producto.tienda_id == actor.tienda_id)
    if modalidad == "FIN_MES":
        stmt = stmt.where(Producto.permite_fin_mes.is_(True))
    elif modalidad == "CUOTAS":
        stmt = stmt.where(Producto.permite_cuotas.is_(True))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Producto.nombre.ilike(like), Producto.marca.ilike(like), Producto.proveedor.ilike(like)))
    por_estado = contar_por(db, stmt, Producto.estado)  # faceta: sin el filtro de estado
    if estado:
        stmt = stmt.where(Producto.estado == estado)
    productos, total = paginar(db, stmt.order_by(Producto.nombre), limit, offset)
    return Pagina(items=productos, total=total, limit=limit, offset=offset,
                  conteos={"estado": {"TODOS": sum(por_estado.values()), **por_estado}})


def actualizar(db: Session, actor: Actor, producto_id: int, data: ProductoUpdate) -> Producto:
    """El cambio de precio no afecta compras anteriores: cada compra guarda su precio."""
    p = obtener(db, actor, producto_id)
    for k, v in data.model_dump().items():
        setattr(p, k, v)
    registrar(db, actor, "ACTUALIZAR", "producto", p.id, data.model_dump())
    db.commit()
    return p


def cambiar_estado(db: Session, actor: Actor, producto_id: int, activar: bool) -> Producto:
    p = obtener(db, actor, producto_id)
    nuevo = "ACTIVO" if activar else "BAJA"
    if p.estado == nuevo:
        raise BusinessError(f"El producto ya está {'activo' if activar else 'dado de baja'}")
    p.estado = nuevo
    registrar(db, actor, "ALTA" if activar else "BAJA", "producto", p.id)
    db.commit()
    return p
