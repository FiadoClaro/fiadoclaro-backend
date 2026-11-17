"""
Pago de un listado (enunciado, puntos 5 y 6; Anexo A).

* No se aceptan pagos parciales: el monto debe ser igual al total exigible.
* Si se paga después de la fecha pactada, se suma el interés moratorio.
* El pago se imputa por prelación: 1) mora, 2) interés compensatorio, 3) capital.
"""
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import hoy
from app.core.deps import Actor
from app.core.errors import BusinessError, NotFoundError
from app.modules.audit.service import registrar
from app.modules.finance import engine
from app.modules.payments.models import Pago
from app.modules.payments.schemas import CotizacionOut, ImputacionOut, PagoIn, PagoOut
from app.modules.purchases.models import Compra
from app.modules.statements import service as statements
from app.modules.statements.models import EstadoCuenta


def _fecha_valida(ec: EstadoCuenta, fecha: date | None) -> date:
    fecha = fecha or hoy()
    if fecha > hoy():
        raise BusinessError("La fecha de pago no puede ser futura")
    if fecha < ec.fecha_corte:
        raise BusinessError("La fecha de pago no puede ser anterior a la fecha de corte del listado")
    return fecha


def cotizar(db: Session, actor: Actor, ec_id: int, fecha: date | None) -> CotizacionOut:
    ec = statements.obtener(db, actor, ec_id)
    statements.validar_pendiente(ec)
    fecha = _fecha_valida(ec, fecha)
    mora = statements.calcular_mora(ec, fecha)
    total = engine.dinero(ec.total_a_pagar + mora.monto)
    prelacion = engine.aplicar_prelacion(total, mora.monto, ec.total_interes, ec.total_capital)
    return CotizacionOut(
        estado_cuenta_id=ec.id, fecha_pago_pactada=ec.fecha_pago, fecha_pago=fecha, dias_mora=mora.dias,
        interes_moratorio=mora.monto, interes_compensatorio=ec.total_interes, capital=ec.total_capital,
        total_exigible=total, prelacion=[ImputacionOut(**i.__dict__) for i in prelacion],
    )


def registrar_pago(db: Session, actor: Actor, data: PagoIn) -> PagoOut:
    cot = cotizar(db, actor, data.estado_cuenta_id, data.fecha_pago)
    if data.monto != cot.total_exigible:
        raise BusinessError(
            f"No se aceptan pagos parciales: el total exigible al {cot.fecha_pago} es "
            f"{cot.total_exigible} (incluye {cot.interes_moratorio} de mora)",
            code="monto_distinto_al_exigible",
        )
    ec = statements.obtener(db, actor, data.estado_cuenta_id)
    imp = {i.concepto: i.imputado for i in cot.prelacion}
    pago = Pago(
        tienda_id=ec.tienda_id, cliente_id=ec.cliente_id, estado_cuenta_id=ec.id, registrado_por=actor.id,
        fecha_pago=cot.fecha_pago, dias_mora=cot.dias_mora, monto_mora=imp["INTERES_MORATORIO"],
        monto_interes=imp["INTERES_COMPENSATORIO"], monto_capital=imp["CAPITAL"], monto_total=data.monto,
    )
    db.add(pago)

    # Cerrar cuotas, listado y, si ya no quedan cuotas, la compra
    ec.estado = "PAGADO"
    compras: set[int] = set()
    for c in ec.cuotas:
        c.estado = "PAGADA"
        compras.add(c.compra_id)
    db.flush()
    for compra_id in compras:
        compra = db.get(Compra, compra_id)
        if all(q.estado == "PAGADA" for q in compra.cuotas):
            compra.estado = "CANCELADA"

    registrar(db, actor, "PAGO", "estado_cuenta", ec.id, {
        "pago_id": pago.id, "fecha_pago": cot.fecha_pago, "dias_mora": cot.dias_mora,
        "mora": pago.monto_mora, "interes": pago.monto_interes, "capital": pago.monto_capital,
        "total": pago.monto_total,
    })
    db.commit()
    db.refresh(pago)
    return to_out(pago)


def to_out(p: Pago) -> PagoOut:
    imput = engine.aplicar_prelacion(p.monto_total, p.monto_mora, p.monto_interes, p.monto_capital)
    return PagoOut(
        id=p.id, estado_cuenta_id=p.estado_cuenta_id, cliente_id=p.cliente_id, fecha_pago=p.fecha_pago,
        dias_mora=p.dias_mora, monto_total=p.monto_total, created_at=p.created_at,
        imputacion=[ImputacionOut(**i.__dict__) for i in imput],
    )


def obtener(db: Session, actor: Actor, pago_id: int) -> Pago:
    p = db.get(Pago, pago_id)
    if not p or p.tienda_id != actor.tienda_id:
        raise NotFoundError("Pago", pago_id)
    return p


def listar(db: Session, actor: Actor, cliente_id: int | None, limit: int, offset: int) -> list[PagoOut]:
    q = select(Pago).where(Pago.tienda_id == actor.tienda_id)
    if cliente_id:
        q = q.where(Pago.cliente_id == cliente_id)
    return [to_out(p) for p in db.scalars(q.order_by(Pago.id.desc()).limit(limit).offset(offset))]
