from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.clock import ahora
from app.core.deps import Actor
from app.core.errors import BusinessError, ConflictError, NotFoundError
from app.core.pagination import Pagina, contar_por, paginar
from app.modules.audit.service import registrar
from app.modules.iam.models import Usuario
from app.modules.iam.service import crear_usuario
from app.modules.stores.models import Tienda
from app.modules.stores.schemas import (
    AdministradorOut,
    MiTiendaUpdate,
    TiendaCreate,
    TiendaOut,
    TiendaUpdate,
)


def _admin(db: Session, tienda_id: int) -> Usuario | None:
    return db.scalar(select(Usuario).where(Usuario.tienda_id == tienda_id, Usuario.rol == "ADMIN_TIENDA")
                     .order_by(Usuario.id).limit(1))


def _out(db: Session, t: Tienda) -> TiendaOut:
    admin = _admin(db, t.id)
    return TiendaOut.model_validate(t).model_copy(
        update={"administrador": AdministradorOut.model_validate(admin) if admin else None})


def obtener(db: Session, tienda_id: int) -> Tienda:
    t = db.get(Tienda, tienda_id)
    if not t:
        raise NotFoundError("Tienda", tienda_id)
    return t


# ----------------------------------------------------------- admin del sistema
def crear(db: Session, actor: Actor, data: TiendaCreate) -> TiendaOut:
    """Alta de tienda + usuario administrador del negocio (enunciado, punto 1)."""
    if db.scalar(select(Tienda.id).where(Tienda.ruc == data.ruc)):
        raise ConflictError(f"Ya existe una tienda con RUC {data.ruc}")
    tienda = Tienda(**data.model_dump(exclude={"administrador"}), estado="ACTIVA")
    db.add(tienda)
    db.flush()
    a = data.administrador
    admin = crear_usuario(db, a.username, a.password, "ADMIN_TIENDA", a.nombre, tienda.id, a.telefono, a.correo)
    registrar(db, actor, "CREAR", "tienda", tienda.id,
              {"ruc": tienda.ruc, "nombre": tienda.nombre_comercial, "admin": admin.username}, tienda.id)
    db.commit()
    return _out(db, tienda)


def listar(db: Session, estado: str | None, giro: str | None, q: str | None,
           limit: int, offset: int) -> Pagina[TiendaOut]:
    base = select(Tienda)
    if q:
        like = f"%{q.strip()}%"
        base = base.where(or_(Tienda.nombre_comercial.ilike(like), Tienda.razon_social.ilike(like),
                              Tienda.ruc.like(like)))
    # Facetas: cada una con los demás filtros aplicados, sin el suyo
    por_estado = contar_por(db, base.where(Tienda.giro == giro) if giro else base, Tienda.estado)
    por_giro = contar_por(db, base.where(Tienda.estado == estado) if estado else base, Tienda.giro)

    stmt = base
    if estado:
        stmt = stmt.where(Tienda.estado == estado)
    if giro:
        stmt = stmt.where(Tienda.giro == giro)
    tiendas, total = paginar(db, stmt.order_by(Tienda.nombre_comercial), limit, offset)
    return Pagina(items=[_out(db, t) for t in tiendas], total=total, limit=limit, offset=offset,
                  conteos={"estado": por_estado, "giro": por_giro})


def detalle(db: Session, tienda_id: int) -> TiendaOut:
    return _out(db, obtener(db, tienda_id))


def _aplicar(db: Session, tienda: Tienda, cambios: dict) -> dict:
    """Aplica cambios de la tienda y, si vienen, los del administrador. Devuelve lo cambiado."""
    admin_cambios = cambios.pop("administrador", None) or {}
    for k, v in cambios.items():
        setattr(tienda, k, v)
    if admin_cambios:
        admin = _admin(db, tienda.id)
        if not admin:
            raise NotFoundError("Administrador de la tienda")
        for k, v in admin_cambios.items():
            if v is not None:
                setattr(admin, k, v)
        cambios["administrador"] = admin_cambios
    return cambios


def actualizar(db: Session, actor: Actor, tienda_id: int, data: TiendaUpdate) -> TiendaOut:
    tienda = obtener(db, tienda_id)
    cambios = data.model_dump(exclude_unset=True)
    if not cambios:
        raise BusinessError("No enviaste ningún dato para actualizar", code="sin_cambios")
    cambios = _aplicar(db, tienda, cambios)
    registrar(db, actor, "ACTUALIZAR", "tienda", tienda.id, cambios, tienda.id)
    db.commit()
    return _out(db, tienda)


def cambiar_estado(db: Session, actor: Actor, tienda_id: int, activar: bool) -> TiendaOut:
    """Baja/alta lógica: la tienda dada de baja no puede iniciar sesión ni registrar fiados."""
    tienda = obtener(db, tienda_id)
    nuevo = "ACTIVA" if activar else "BAJA"
    if tienda.estado == nuevo:
        raise BusinessError(f"La tienda ya está {'activa' if activar else 'dada de baja'}", code="sin_cambios")
    tienda.estado = nuevo
    tienda.fecha_baja = None if activar else ahora()
    registrar(db, actor, "ALTA" if activar else "BAJA", "tienda", tienda.id, None, tienda.id)
    db.commit()
    return _out(db, tienda)


# ------------------------------------------------- mi tienda (admin de tienda / vecino)
def _mi_tienda(db: Session, actor: Actor) -> Tienda:
    if actor.tienda_id is None:
        raise BusinessError("El administrador del sistema no pertenece a ninguna tienda",
                            code="sin_tienda")
    return obtener(db, actor.tienda_id)


def mi_tienda(db: Session, actor: Actor) -> TiendaOut:
    """Tienda del usuario de la sesión: la que administra o, para el vecino, donde tiene su cuenta."""
    tienda = _out(db, _mi_tienda(db, actor))
    if actor.rol == "CLIENTE":
        # El vecino ve los datos del negocio, no el usuario ni el último acceso del administrador.
        tienda = tienda.model_copy(update={"administrador": None})
    return tienda


def actualizar_mi_tienda(db: Session, actor: Actor, data: MiTiendaUpdate) -> TiendaOut:
    tienda = _mi_tienda(db, actor)
    cambios = data.model_dump(exclude_unset=True)
    if not cambios:
        raise BusinessError("No enviaste ningún dato para actualizar", code="sin_cambios")
    cambios = _aplicar(db, tienda, cambios)
    registrar(db, actor, "ACTUALIZAR", "tienda", tienda.id, cambios, tienda.id)
    db.commit()
    return _out(db, tienda)
