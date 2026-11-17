from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.clock import ahora, hoy
from app.core.deps import Actor
from app.core.errors import BusinessError, ConflictError, NotFoundError
from app.core.pagination import Pagina
from app.modules.audit.service import registrar
from app.modules.customers.models import Cliente, CondicionCredito
from app.modules.customers.schemas import (
    ClienteCreate,
    ClienteOut,
    ClienteUpdate,
    CondicionIn,
    CondicionOut,
    ResumenCredito,
    TasaOut,
)
from app.modules.finance import engine
from app.modules.finance.service import validar_topes
from app.modules.iam.models import Usuario
from app.modules.iam.service import crear_usuario
from app.modules.purchases.models import Compra, Cuota
from app.modules.statements.models import EstadoCuenta
from app.modules.stores.models import Tienda

CERO = Decimal("0")


# ------------------------------------------------------------- utilidades
def tasas_de_condicion(c: CondicionCredito) -> tuple[engine.Tasa, engine.Tasa]:
    comp = engine.Tasa(c.tipo_tasa, c.tasa, c.periodo_tasa_dias, c.capitalizacion_dias)
    mora = engine.Tasa(c.tipo_tasa_mora, c.tasa_mora, c.periodo_tasa_mora_dias, c.capitalizacion_mora_dias)
    return comp, mora


def _tasa_out(t: engine.Tasa) -> TasaOut:
    return TasaOut(
        tipo=t.tipo, valor=t.valor_pct, periodo_dias=t.periodo_dias,
        capitalizacion_dias=t.capitalizacion_dias, equivalencias=engine.resumen_tasa(t),
    )


def capital_pendiente(db: Session, cliente_id: int) -> Decimal:
    """Crédito utilizado = capital de las cuotas aún no pagadas."""
    total = db.scalar(
        select(func.coalesce(func.sum(Cuota.amortizacion), 0))
        .join(Compra, Compra.id == Cuota.compra_id)
        .where(Compra.cliente_id == cliente_id, Compra.estado == "VIGENTE", Cuota.estado == "PENDIENTE")
    )
    return engine.dinero(total)


def listados_pendientes(db: Session, cliente_id: int, solo_vencidos: bool = False) -> int:
    q = select(func.count(EstadoCuenta.id)).where(
        EstadoCuenta.cliente_id == cliente_id, EstadoCuenta.estado == "PENDIENTE"
    )
    if solo_vencidos:
        q = q.where(EstadoCuenta.fecha_pago < hoy())
    return db.scalar(q) or 0


def resumen_credito(db: Session, cliente: Cliente) -> ResumenCredito:
    c = cliente.condicion
    utilizado = capital_pendiente(db, cliente.id)
    disponible = max(CERO, c.limite_credito - utilizado)
    ciclo = engine.ciclo_de_compra(ahora(), c.dia_corte, c.hora_corte, c.dia_pago)
    return ResumenCredito(
        limite=c.limite_credito,
        utilizado=utilizado,
        disponible=engine.dinero(disponible),
        porcentaje_utilizado=engine.dinero(utilizado / c.limite_credito * 100),
        estado_pago="EN_MORA" if listados_pendientes(db, cliente.id, solo_vencidos=True) else "AL_DIA",
        proximo_corte=ciclo.fecha_corte,
        proximo_pago=ciclo.fecha_pago,
        listados_pendientes=listados_pendientes(db, cliente.id),
    )


def to_out(db: Session, cliente: Cliente) -> ClienteOut:
    c = cliente.condicion
    comp, mora = tasas_de_condicion(c)
    usuario = db.get(Usuario, cliente.usuario_id)
    return ClienteOut(
        id=cliente.id, tienda_id=cliente.tienda_id, dni=cliente.dni, nombres=cliente.nombres,
        apellidos=cliente.apellidos, telefono=cliente.telefono, correo=cliente.correo,
        direccion=cliente.direccion, estado=cliente.estado, usuario=usuario.username,
        created_at=cliente.created_at,
        condicion=CondicionOut(
            moneda=c.moneda, tasa=_tasa_out(comp), tasa_mora=_tasa_out(mora),
            limite_credito=c.limite_credito, max_meses=c.max_meses, dia_corte=c.dia_corte,
            hora_corte=c.hora_corte, dia_pago=c.dia_pago,
        ),
        resumen=resumen_credito(db, cliente),
    )


def obtener(db: Session, actor: Actor, cliente_id: int) -> Cliente:
    """Busca un cliente de la tienda del usuario (nunca de otra tienda)."""
    cliente = db.get(Cliente, cliente_id)
    if not cliente or cliente.tienda_id != actor.tienda_id:
        raise NotFoundError("Cliente", cliente_id)
    return cliente


def _aplicar_condicion(db: Session, cond: CondicionCredito, data: CondicionIn) -> None:
    comp, mora = data.tasa.to_engine(), data.tasa_mora.to_engine()
    validar_topes(db, comp, mora, hoy())
    cond.moneda = data.moneda
    cond.tipo_tasa, cond.tasa = comp.tipo, comp.valor_pct
    cond.periodo_tasa_dias, cond.capitalizacion_dias = comp.periodo_dias, comp.capitalizacion_dias
    cond.tipo_tasa_mora, cond.tasa_mora = mora.tipo, mora.valor_pct
    cond.periodo_tasa_mora_dias, cond.capitalizacion_mora_dias = mora.periodo_dias, mora.capitalizacion_dias
    cond.limite_credito = data.limite_credito
    cond.max_meses = data.max_meses
    cond.dia_corte, cond.hora_corte, cond.dia_pago = data.dia_corte, data.hora_corte, data.dia_pago


def usuario_portal(db: Session, tienda_id: int, dni: str, propuesto: str | None) -> str:
    """
    Usuario del vecino en el portal: <DNI>@<dominio de la tienda> (ej. 08765432@bodegadonlucho.com).
    Si la tienda no lo envía, se arma solo; si lo envía, debe empezar con el DNI del cliente.
    """
    if not propuesto:
        return f"{dni}@{db.get(Tienda, tienda_id).dominio_portal}"
    if propuesto.split("@")[0] != dni:
        raise BusinessError(
            f"El usuario del portal debe empezar con el DNI del cliente, por ejemplo "
            f"{dni}@{db.get(Tienda, tienda_id).dominio_portal}",
            code="usuario_portal_invalido",
        )
    return propuesto


# --------------------------------------------------------------- comandos
def crear(db: Session, actor: Actor, data: ClienteCreate) -> ClienteOut:
    """Alta de cliente con su tasa, límite, plazo máximo, corte y pago (enunciado, punto 3)."""
    if db.scalar(select(Cliente.id).where(Cliente.tienda_id == actor.tienda_id, Cliente.dni == data.dni)):
        raise ConflictError(f"Ya existe un cliente con DNI {data.dni} en esta tienda")
    nombre = f"{data.nombres} {data.apellidos}"
    username = usuario_portal(db, actor.tienda_id, data.dni, data.acceso.username)
    usuario = crear_usuario(db, username, data.acceso.password, "CLIENTE", nombre, actor.tienda_id,
                            data.telefono, data.correo)
    cliente = Cliente(
        tienda_id=actor.tienda_id, usuario_id=usuario.id, dni=data.dni,
        **data.model_dump(include={"nombres", "apellidos", "telefono", "correo", "direccion"}),
        estado="ACTIVO",
    )
    cond = CondicionCredito()
    _aplicar_condicion(db, cond, data.condicion)
    cliente.condicion = cond
    db.add(cliente)
    db.flush()
    registrar(db, actor, "CREAR", "cliente", cliente.id,
              {"dni": cliente.dni, "condicion": data.condicion.model_dump()})
    db.commit()
    return to_out(db, cliente)


def listar(db: Session, actor: Actor, estado: str | None, q: str | None,
           limit: int, offset: int) -> Pagina[ClienteOut]:
    """
    Cartera de clientes con su resumen de crédito.
    `conteos.estado` alimenta los filtros: TODOS, ACTIVO, BAJA, AL_DIA y EN_MORA (los dos últimos
    solo cuentan clientes activos). Se calculan con la búsqueda aplicada.
    """
    stmt = select(Cliente).where(Cliente.tienda_id == actor.tienda_id)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Cliente.dni.like(like), Cliente.nombres.ilike(like), Cliente.apellidos.ilike(like)))
    # El estado de pago (al día / en mora) se calcula por cliente, así que se filtra en memoria.
    todos = [to_out(db, c) for c in db.scalars(stmt.order_by(Cliente.apellidos, Cliente.nombres)).unique()]
    activos = [c for c in todos if c.estado == "ACTIVO"]
    conteos = {
        "TODOS": len(todos),
        "ACTIVO": len(activos),
        "BAJA": len(todos) - len(activos),
        "AL_DIA": sum(1 for c in activos if c.resumen.estado_pago == "AL_DIA"),
        "EN_MORA": sum(1 for c in activos if c.resumen.estado_pago == "EN_MORA"),
    }
    if estado in ("ACTIVO", "BAJA"):
        filtrados = [c for c in todos if c.estado == estado]
    elif estado in ("AL_DIA", "EN_MORA"):
        filtrados = [c for c in activos if c.resumen.estado_pago == estado]
    else:
        filtrados = todos
    return Pagina(items=filtrados[offset: offset + limit], total=len(filtrados), limit=limit, offset=offset,
                  conteos={"estado": conteos})


def actualizar(db: Session, actor: Actor, cliente_id: int, data: ClienteUpdate) -> ClienteOut:
    cliente = obtener(db, actor, cliente_id)
    cambios = data.model_dump(exclude_unset=True)
    if not cambios:
        raise BusinessError("No enviaste ningún dato para actualizar", code="sin_cambios")
    for k, v in cambios.items():
        setattr(cliente, k, v)
    # El usuario del portal refleja el nombre y el contacto de la ficha del cliente
    usuario = db.get(Usuario, cliente.usuario_id)
    usuario.nombre = f"{cliente.nombres} {cliente.apellidos}"
    usuario.telefono, usuario.correo = cliente.telefono, cliente.correo
    registrar(db, actor, "ACTUALIZAR", "cliente", cliente.id, cambios)
    db.commit()
    return to_out(db, cliente)


def actualizar_condicion(db: Session, actor: Actor, cliente_id: int, data: CondicionIn) -> ClienteOut:
    """Cambia las condiciones para compras FUTURAS; las compras ya hechas conservan su tasa."""
    cliente = obtener(db, actor, cliente_id)
    utilizado = capital_pendiente(db, cliente.id)
    if data.limite_credito < utilizado:
        raise BusinessError(f"El nuevo límite no puede ser menor a la deuda pendiente ({utilizado})")
    if data.moneda != cliente.condicion.moneda and utilizado > 0:
        raise BusinessError("No se puede cambiar la moneda mientras el cliente tenga deuda pendiente")
    _aplicar_condicion(db, cliente.condicion, data)
    registrar(db, actor, "ACTUALIZAR_CONDICION", "cliente", cliente.id, data.model_dump())
    db.commit()
    return to_out(db, cliente)


def cambiar_estado(db: Session, actor: Actor, cliente_id: int, activar: bool) -> ClienteOut:
    cliente = obtener(db, actor, cliente_id)
    nuevo = "ACTIVO" if activar else "BAJA"
    if cliente.estado == nuevo:
        raise BusinessError(f"El cliente ya está {'activo' if activar else 'dado de baja'}")
    if not activar and (capital_pendiente(db, cliente.id) > 0 or listados_pendientes(db, cliente.id)):
        raise BusinessError("No se puede dar de baja a un cliente con deuda pendiente")
    cliente.estado = nuevo
    cliente.fecha_baja = None if activar else ahora()
    db.get(Usuario, cliente.usuario_id).activo = activar  # sin acceso al portal mientras esté de baja
    registrar(db, actor, "ALTA" if activar else "BAJA", "cliente", cliente.id)
    db.commit()
    return to_out(db, cliente)
