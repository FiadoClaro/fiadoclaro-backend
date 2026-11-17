from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.clock import ahora
from app.core.deps import Actor
from app.core.errors import BusinessError, ConflictError, NotFoundError
from app.modules.audit.service import registrar
from app.modules.iam.models import Usuario
from app.modules.iam.service import crear_usuario
from app.modules.stores.models import Tienda
from app.modules.stores.schemas import TiendaCreate, TiendaOut, TiendaUpdate


def _out(db: Session, t: Tienda) -> TiendaOut:
    admin = db.scalar(
        select(Usuario.nombre).where(Usuario.tienda_id == t.id, Usuario.rol == "ADMIN_TIENDA").limit(1)
    )
    return TiendaOut.model_validate(t).model_copy(update={"administrador": admin})


def obtener(db: Session, tienda_id: int) -> Tienda:
    t = db.get(Tienda, tienda_id)
    if not t:
        raise NotFoundError("Tienda", tienda_id)
    return t


def crear(db: Session, actor: Actor, data: TiendaCreate) -> TiendaOut:
    """Alta de tienda + usuario administrador del negocio (enunciado, punto 1)."""
    if db.scalar(select(Tienda.id).where(Tienda.ruc == data.ruc)):
        raise ConflictError(f"Ya existe una tienda con RUC {data.ruc}")
    tienda = Tienda(**data.model_dump(exclude={"administrador"}), estado="ACTIVA")
    db.add(tienda)
    db.flush()
    admin = crear_usuario(db, data.administrador, "ADMIN_TIENDA", data.administrador.nombre, tienda.id)
    registrar(db, actor, "CREAR", "tienda", tienda.id,
              {"ruc": tienda.ruc, "nombre": tienda.nombre_comercial, "admin": admin.username}, tienda.id)
    db.commit()
    return _out(db, tienda)


def listar(db: Session, estado: str | None, giro: str | None, q: str | None, limit: int, offset: int) -> list[TiendaOut]:
    stmt = select(Tienda)
    if estado:
        stmt = stmt.where(Tienda.estado == estado)
    if giro:
        stmt = stmt.where(Tienda.giro == giro)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Tienda.nombre_comercial.ilike(like), Tienda.ruc.like(like), Tienda.distrito.ilike(like)))
    tiendas = db.scalars(stmt.order_by(Tienda.nombre_comercial).limit(limit).offset(offset))
    return [_out(db, t) for t in tiendas]


def detalle(db: Session, tienda_id: int) -> TiendaOut:
    return _out(db, obtener(db, tienda_id))


def actualizar(db: Session, actor: Actor, tienda_id: int, data: TiendaUpdate) -> TiendaOut:
    tienda = obtener(db, tienda_id)
    cambios = data.model_dump(exclude_unset=True)
    for k, v in cambios.items():
        setattr(tienda, k, v)
    registrar(db, actor, "ACTUALIZAR", "tienda", tienda.id, cambios, tienda.id)
    db.commit()
    return _out(db, tienda)


def cambiar_estado(db: Session, actor: Actor, tienda_id: int, activar: bool) -> TiendaOut:
    """Baja/alta lógica: la tienda dada de baja no puede iniciar sesión ni registrar fiados."""
    tienda = obtener(db, tienda_id)
    nuevo = "ACTIVA" if activar else "BAJA"
    if tienda.estado == nuevo:
        raise BusinessError(f"La tienda ya está {nuevo.lower()}")
    tienda.estado = nuevo
    tienda.fecha_baja = None if activar else ahora()
    registrar(db, actor, "ALTA" if activar else "BAJA", "tienda", tienda.id, None, tienda.id)
    db.commit()
    return _out(db, tienda)
