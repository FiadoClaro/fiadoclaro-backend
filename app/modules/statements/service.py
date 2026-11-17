"""
Listado de pago generado en la fecha de corte (enunciado, punto 6).

Incluye las compras del ciclo ordenadas por fecha, con los intereses por los días entre
la compra y la fecha de pago. Si se paga tarde, la mora se detalla en un ítem aparte:
interés moratorio sobre el pago total que debió hacerse, por los días de atraso.
"""
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import a_hora_local, ahora, hoy
from app.core.deps import Actor
from app.core.errors import BusinessError, NotFoundError
from app.modules.audit.service import registrar
from app.modules.customers.models import Cliente, CondicionCredito
from app.modules.finance import engine
from app.modules.payments.models import Pago
from app.modules.purchases.models import Compra, Cuota
from app.modules.purchases.service import tasas_de_compra
from app.modules.statements.models import EstadoCuenta
from app.modules.statements.schemas import (
    EstadoCuentaOut,
    EstadoCuentaResumen,
    GeneracionOut,
    ItemListado,
    Omitido,
)

CERO = Decimal("0")


# -------------------------------------------------------------------- mora
@dataclass
class Mora:
    dias: int
    monto: Decimal


def calcular_mora(ec: EstadoCuenta, fecha_pago_real: date) -> Mora:
    """Mora de cada cuota con la tasa moratoria COPIADA en su compra."""
    dias_max, total = 0, CERO
    for c in ec.cuotas:
        _, t_mora = tasas_de_compra(c.compra)
        r = engine.interes_moratorio(c.cuota, c.fecha_vencimiento, fecha_pago_real, t_mora)
        dias_max, total = max(dias_max, r.dias_mora), total + r.interes_moratorio
    return Mora(dias_max, engine.dinero(total))


# --------------------------------------------------------------- generación
def _recalcular_totales(ec: EstadoCuenta) -> None:
    ec.total_capital = engine.dinero(sum((c.amortizacion for c in ec.cuotas), CERO))
    ec.total_interes = engine.dinero(sum((c.interes for c in ec.cuotas), CERO))
    ec.total_a_pagar = engine.dinero(sum((c.cuota for c in ec.cuotas), CERO))


def _generar_para(db: Session, actor: Actor, cliente: Cliente, fecha_corte: date) -> EstadoCuenta | str:
    cond = cliente.condicion
    momento_corte = datetime.combine(fecha_corte, cond.hora_corte, tzinfo=ahora().tzinfo)
    if ahora() < momento_corte:
        return f"Aún no llega el corte ({fecha_corte} {cond.hora_corte:%H:%M})"
    fecha_pago = engine.fecha_pago_de_corte(fecha_corte, cond.dia_pago)

    ec = db.scalar(select(EstadoCuenta).where(
        EstadoCuenta.cliente_id == cliente.id, EstadoCuenta.fecha_corte == fecha_corte))
    if ec and ec.estado == "PAGADO":
        return "El listado de este ciclo ya fue pagado"

    # Cuotas pendientes que vencen hasta la fecha de pago y aún no están en ningún listado
    nuevas = list(db.scalars(
        select(Cuota).join(Compra, Compra.id == Cuota.compra_id).where(
            Compra.cliente_id == cliente.id, Compra.estado == "VIGENTE", Cuota.estado == "PENDIENTE",
            Cuota.estado_cuenta_id.is_(None), Cuota.fecha_vencimiento <= fecha_pago,
        )
    ))
    if not ec and not nuevas:
        return "Sin deuda que vence en este ciclo"

    if not ec:
        ec = EstadoCuenta(tienda_id=cliente.tienda_id, cliente_id=cliente.id, fecha_corte=fecha_corte,
                          fecha_pago=fecha_pago, moneda=cond.moneda, estado="PENDIENTE",
                          total_capital=CERO, total_interes=CERO, total_a_pagar=CERO)
        db.add(ec)
        db.flush()
    for c in nuevas:
        c.estado_cuenta_id = ec.id
    db.flush()
    db.refresh(ec)
    _recalcular_totales(ec)
    registrar(db, actor, "GENERAR_LISTADO", "estado_cuenta", ec.id,
              {"cliente_id": cliente.id, "fecha_corte": fecha_corte, "cuotas": len(ec.cuotas),
               "total": ec.total_a_pagar})
    return ec


def generar(db: Session, actor: Actor, fecha_corte: date, cliente_id: int | None) -> GeneracionOut:
    q = (select(Cliente).join(CondicionCredito)
         .where(Cliente.tienda_id == actor.tienda_id, Cliente.estado == "ACTIVO"))
    if cliente_id:
        q = q.where(Cliente.id == cliente_id)
    else:
        q = q.where(CondicionCredito.dia_corte == fecha_corte.day)
    clientes = list(db.scalars(q).unique())
    if cliente_id and not clientes:
        raise NotFoundError("Cliente", cliente_id)

    generados, omitidos = [], []
    for cliente in clientes:
        if cliente.condicion.dia_corte != fecha_corte.day:
            omitidos.append(Omitido(cliente_id=cliente.id,
                                    motivo=f"Su día de corte es el {cliente.condicion.dia_corte}"))
            continue
        r = _generar_para(db, actor, cliente, fecha_corte)
        if isinstance(r, str):
            omitidos.append(Omitido(cliente_id=cliente.id, motivo=r))
        else:
            generados.append(_resumen(r, cliente))
    db.commit()
    return GeneracionOut(fecha_corte=fecha_corte, generados=generados, omitidos=omitidos)


# ----------------------------------------------------------------- consulta
def _resumen(ec: EstadoCuenta, cliente: Cliente) -> EstadoCuentaResumen:
    return EstadoCuentaResumen(
        id=ec.id, cliente_id=cliente.id, cliente=f"{cliente.nombres} {cliente.apellidos}", dni=cliente.dni,
        fecha_corte=ec.fecha_corte, fecha_pago=ec.fecha_pago, moneda=ec.moneda,
        total_a_pagar=ec.total_a_pagar, estado=ec.estado,
        vencido=ec.estado == "PENDIENTE" and hoy() > ec.fecha_pago,
    )


def obtener(db: Session, actor: Actor, ec_id: int) -> EstadoCuenta:
    ec = db.get(EstadoCuenta, ec_id)
    if not ec or ec.tienda_id != actor.tienda_id:
        raise NotFoundError("Listado de pago", ec_id)
    return ec


def detalle(db: Session, ec: EstadoCuenta, fecha_consulta: date | None = None) -> EstadoCuentaOut:
    cliente = db.get(Cliente, ec.cliente_id)
    fecha_consulta = fecha_consulta or hoy()
    items: list[ItemListado] = []
    for c in sorted(ec.cuotas, key=lambda q: (q.compra.fecha_hora, q.numero)):
        compra = c.compra
        nombres = ", ".join(d.descripcion for d in compra.detalles)
        fin_mes = compra.modalidad == "FIN_MES"
        items.append(ItemListado(
            tipo="COMPRA_FIN_MES" if fin_mes else "CUOTA", compra_id=compra.id,
            fecha_compra=a_hora_local(compra.fecha_hora), descripcion=nombres,
            cuota=None if fin_mes else f"{c.numero}/{compra.num_cuotas}",
            fecha_vencimiento=c.fecha_vencimiento, capital=c.amortizacion, interes=c.interes,
            dias_interes=compra.dias_gracia if fin_mes else None, total=c.cuota,
        ))

    if ec.estado == "PAGADO":
        pago = db.scalar(select(Pago).where(Pago.estado_cuenta_id == ec.id))
        mora = Mora(pago.dias_mora, pago.monto_mora)
        fecha_consulta = pago.fecha_pago
    else:
        mora = calcular_mora(ec, fecha_consulta)

    if mora.monto > 0:
        items.append(ItemListado(
            tipo="INTERES_MORA", compra_id=None, fecha_compra=None,
            descripcion=f"Intereses por mora ({mora.dias} días de atraso)",
            fecha_vencimiento=ec.fecha_pago, capital=CERO, interes=CERO, mora=mora.monto, total=mora.monto,
        ))

    base = _resumen(ec, cliente)
    return EstadoCuentaOut(
        **base.model_dump(), items=items, total_capital=ec.total_capital, total_interes=ec.total_interes,
        fecha_consulta=fecha_consulta, dias_mora=mora.dias, interes_moratorio=mora.monto,
        total_exigible=engine.dinero(ec.total_a_pagar + mora.monto),
    )


def listar(db: Session, actor: Actor, cliente_id: int | None, estado: str | None,
           fecha_corte: date | None, limit: int, offset: int) -> list[EstadoCuentaResumen]:
    q = select(EstadoCuenta, Cliente).join(Cliente, Cliente.id == EstadoCuenta.cliente_id).where(
        EstadoCuenta.tienda_id == actor.tienda_id)
    if cliente_id:
        q = q.where(EstadoCuenta.cliente_id == cliente_id)
    if estado:
        q = q.where(EstadoCuenta.estado == estado)
    if fecha_corte:
        q = q.where(EstadoCuenta.fecha_corte == fecha_corte)
    filas = db.execute(q.order_by(EstadoCuenta.fecha_corte.desc(), Cliente.apellidos).limit(limit).offset(offset))
    return [_resumen(ec, cl) for ec, cl in filas]


def validar_pendiente(ec: EstadoCuenta) -> None:
    if ec.estado != "PENDIENTE":
        raise BusinessError("Este listado ya fue pagado")
