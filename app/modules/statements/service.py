"""
Listado de pago generado en la fecha de corte (enunciado, punto 6).

Incluye las compras del ciclo ordenadas por fecha, con los intereses por los días entre
la compra y la fecha de pago. Si se paga tarde, se agregan dos ítems aparte:
  * interés moratorio sobre el pago total que debió hacerse, con la tasa moratoria del listado;
  * interés compensatorio por los mismos días de atraso.
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import a_hora_local, ahora, hoy
from app.core.deps import Actor
from app.core.errors import BusinessError, NotFoundError
from app.core.pagination import Pagina, contar, contar_por
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
    moratorio: Decimal      # interés moratorio (penalidad)
    comp_mora: Decimal      # interés compensatorio por los días de atraso

    @property
    def total(self) -> Decimal:
        return engine.dinero(self.moratorio + self.comp_mora)


def calcular_mora(ec: EstadoCuenta, fecha_pago_real: date) -> Mora:
    """
    Si se paga después de la fecha de pago del listado:
      * Interés moratorio: sobre el PAGO TOTAL del listado, con UNA sola tasa moratoria
        (la copiada en el listado el día del corte), por los días de atraso (punto 6).
      * Interés compensatorio por atraso: el dinero se sigue usando, así que cada línea sigue
        generando su compensatorio con la tasa COPIADA en su compra (punto 5).
    """
    r = engine.interes_moratorio(ec.total_a_pagar, ec.fecha_pago, fecha_pago_real, ec.tasa_moratoria)
    if r.dias_mora == 0:
        return Mora(0, CERO, CERO)
    comp = CERO
    for c in ec.cuotas:
        t_comp, _ = tasas_de_compra(c.compra)
        comp += engine.interes_compensatorio_mora(c.cuota, ec.fecha_pago, fecha_pago_real, t_comp)
    return Mora(r.dias_mora, r.interes_moratorio, engine.dinero(comp))


# --------------------------------------------------------------- generación
def _recalcular_totales(ec: EstadoCuenta) -> None:
    ec.total_capital = engine.dinero(sum((c.amortizacion for c in ec.cuotas), CERO))
    ec.total_interes = engine.dinero(sum((c.interes for c in ec.cuotas), CERO))
    ec.total_a_pagar = engine.dinero(sum((c.cuota for c in ec.cuotas), CERO))


def _momento_corte(fecha_corte: date, cond: CondicionCredito) -> datetime:
    """Fecha y hora exactas del corte, en hora de Lima."""
    return datetime.combine(fecha_corte, cond.hora_corte, tzinfo=ahora().tzinfo)


def _generar_para(db: Session, actor: Actor | None, cliente: Cliente, fecha_corte: date) -> EstadoCuenta | str:
    """
    Genera (o completa) el listado de un cliente para un corte. `actor=None` = generación automática.
    El listado queda fechado en el momento del corte (`generado_en`), que es cuando el enunciado dice que
    se genera; la bitácora guarda además cuándo lo calculó el sistema.
    """
    cond = cliente.condicion
    momento_corte = _momento_corte(fecha_corte, cond)
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
    if not nuevas:
        return "El listado de este ciclo ya estaba generado" if ec else "Sin deuda que vence en este ciclo"

    if not ec:
        # Copia de la tasa moratoria vigente al corte: un cambio posterior en el cliente no altera el listado.
        ec = EstadoCuenta(tienda_id=cliente.tienda_id, cliente_id=cliente.id, fecha_corte=fecha_corte,
                          fecha_pago=fecha_pago, moneda=cond.moneda, estado="PENDIENTE",
                          tipo_tasa_mora=cond.tipo_tasa_mora, tasa_mora=cond.tasa_mora,
                          periodo_tasa_mora_dias=cond.periodo_tasa_mora_dias,
                          capitalizacion_mora_dias=cond.capitalizacion_mora_dias,
                          total_capital=CERO, total_interes=CERO, total_a_pagar=CERO,
                          generado_en=momento_corte)
        db.add(ec)
        db.flush()
    for c in nuevas:
        c.estado_cuenta_id = ec.id
    db.flush()
    db.refresh(ec)
    _recalcular_totales(ec)
    registrar(db, actor, "GENERAR_LISTADO" if actor else "GENERAR_LISTADO_AUTOMATICO", "estado_cuenta", ec.id,
              {"cliente_id": cliente.id, "fecha_corte": fecha_corte, "cuotas": len(ec.cuotas),
               "total": ec.total_a_pagar}, cliente.tienda_id)
    return ec


# Una cuota entra al listado del corte anterior a su vencimiento; como la fecha de pago cae a lo más
# ~1 mes después del corte, solo pueden tener un corte ya pasado las cuotas que vencen dentro de 40 días.
_HORIZONTE_DIAS = 40


def asegurar_listados(db: Session, tienda_id: int, cliente_id: int | None = None) -> int:
    """
    Generación automática del listado de pago en la fecha de corte (enunciado, punto 6).

    No depende de que alguien pulse un botón: antes de mostrar o usar los datos de un cliente, el sistema
    genera los listados de todos los cortes que ya pasaron y aún no se generaron. El resultado es el mismo
    que si se hubieran generado justo a la hora del corte, porque una compra hecha después del corte ya
    pertenece al ciclo siguiente. Devuelve cuántos listados generó o completó.
    """
    q = (select(Compra.cliente_id, func.min(Cuota.fecha_vencimiento))
         .join(Cuota, Cuota.compra_id == Compra.id)
         .where(Compra.tienda_id == tienda_id, Compra.estado == "VIGENTE", Cuota.estado == "PENDIENTE",
                Cuota.estado_cuenta_id.is_(None),
                Cuota.fecha_vencimiento <= hoy() + timedelta(days=_HORIZONTE_DIAS))
         .group_by(Compra.cliente_id))
    if cliente_id:
        q = q.where(Compra.cliente_id == cliente_id)

    generados = 0
    for cid, primer_vencimiento in db.execute(q).all():
        cliente = db.get(Cliente, cid)
        cond = cliente.condicion
        # Recorre los cortes desde el que cobra la cuota más antigua hasta el último que ya pasó
        corte = engine.sumar_meses(date(primer_vencimiento.year, primer_vencimiento.month, cond.dia_corte), -2)
        while _momento_corte(corte, cond) <= ahora():
            if engine.fecha_pago_de_corte(corte, cond.dia_pago) >= primer_vencimiento:
                if isinstance(_generar_para(db, None, cliente, corte), EstadoCuenta):
                    generados += 1
            corte = engine.sumar_meses(corte, 1)
    if generados:
        db.commit()
    return generados


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
        mora = Mora(pago.dias_mora, pago.monto_mora, pago.monto_interes_comp_mora)
        fecha_consulta = pago.fecha_pago
    else:
        mora = calcular_mora(ec, fecha_consulta)

    # Punto 6: la mora se detalla en ítems nuevos, después de las compras.
    if mora.moratorio > 0:
        items.append(ItemListado(
            tipo="INTERES_MORA", compra_id=None, fecha_compra=None,
            descripcion=f"Intereses por mora ({mora.dias} días de atraso, tasa moratoria {ec.tasa_mora.normalize():f} %)",
            fecha_vencimiento=ec.fecha_pago, capital=CERO, interes=CERO, mora=mora.moratorio,
            dias_interes=mora.dias, total=mora.moratorio,
        ))
    if mora.comp_mora > 0:
        items.append(ItemListado(
            tipo="INTERES_COMP_MORA", compra_id=None, fecha_compra=None,
            descripcion=f"Interés compensatorio por los {mora.dias} días de atraso",
            fecha_vencimiento=ec.fecha_pago, capital=CERO, interes=mora.comp_mora,
            dias_interes=mora.dias, total=mora.comp_mora,
        ))

    base = _resumen(ec, cliente)
    return EstadoCuentaOut(
        **base.model_dump(), items=items, total_capital=ec.total_capital, total_interes=ec.total_interes,
        fecha_consulta=fecha_consulta, dias_mora=mora.dias, interes_moratorio=mora.moratorio,
        interes_compensatorio_mora=mora.comp_mora, total_exigible=engine.dinero(ec.total_a_pagar + mora.total),
    )


def listar(db: Session, actor: Actor, cliente_id: int | None, estado: str | None,
           fecha_corte: date | None, limit: int, offset: int) -> Pagina[EstadoCuentaResumen]:
    asegurar_listados(db, actor.tienda_id, cliente_id)  # generación automática en la fecha de corte
    q = select(EstadoCuenta, Cliente).join(Cliente, Cliente.id == EstadoCuenta.cliente_id).where(
        EstadoCuenta.tienda_id == actor.tienda_id)
    if cliente_id:
        q = q.where(EstadoCuenta.cliente_id == cliente_id)
    if fecha_corte:
        q = q.where(EstadoCuenta.fecha_corte == fecha_corte)
    por_estado = contar_por(db, q, EstadoCuenta.estado)  # faceta: sin el filtro de estado
    if estado:
        q = q.where(EstadoCuenta.estado == estado)
    total = contar(db, q)
    filas = db.execute(q.order_by(EstadoCuenta.fecha_corte.desc(), Cliente.apellidos).limit(limit).offset(offset))
    return Pagina(items=[_resumen(ec, cl) for ec, cl in filas], total=total, limit=limit, offset=offset,
                  conteos={"estado": por_estado})


def validar_pendiente(ec: EstadoCuenta) -> None:
    if ec.estado != "PENDIENTE":
        raise BusinessError("Este listado ya fue pagado")
