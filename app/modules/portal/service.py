"""
Resumen del portal del vecino ("Mi estado de cuenta"): reúne en una sola respuesta lo que la pantalla
muestra. No tiene fórmulas propias: la mora sale de statements.calcular_mora y los demás montos son
sumas de lo ya calculado y guardado en compras, cuotas y listados.
"""
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import a_hora_local, hoy
from app.modules.customers import service as customers
from app.modules.customers.models import Cliente
from app.modules.finance import engine
from app.modules.iam.models import Usuario
from app.modules.portal.schemas import (
    CompraEnCuotasOut,
    CompraFinDeMesOut,
    CuotaPortalOut,
    ListadoPendienteOut,
    PortalResumenOut,
)
from app.modules.purchases.models import Compra, Cuota
from app.modules.statements.models import EstadoCuenta
from app.modules.statements.service import calcular_mora
from app.modules.stores.models import Tienda

CERO = Decimal("0")


def _descripcion(compra: Compra) -> str:
    """'3x Leche Gloria Azul 400g, 1x Arroz Costeño 5 kg'."""
    return ", ".join(f"{d.cantidad.normalize():f}x {d.descripcion}" for d in compra.detalles)


def _atendido_por(db: Session, compra: Compra) -> str:
    usuario = db.get(Usuario, compra.registrado_por)
    return usuario.nombre if usuario else ""


def resumen(db: Session, cliente: Cliente) -> PortalResumenOut:
    hoy_ = hoy()
    tienda = db.get(Tienda, cliente.tienda_id)
    credito = customers.resumen_credito(db, cliente)

    # Listados pendientes, del más antiguo al más reciente, con la mora a hoy
    pendientes = list(db.scalars(select(EstadoCuenta).where(
        EstadoCuenta.cliente_id == cliente.id, EstadoCuenta.estado == "PENDIENTE"
    ).order_by(EstadoCuenta.fecha_corte)))
    listados: list[ListadoPendienteOut] = []
    for ec in pendientes:
        mora = calcular_mora(ec, hoy_)
        listados.append(ListadoPendienteOut(
            id=ec.id, fecha_corte=ec.fecha_corte, fecha_pago=ec.fecha_pago, vencido=hoy_ > ec.fecha_pago,
            total_a_pagar=ec.total_a_pagar, dias_mora=mora.dias, interes_moratorio=mora.moratorio,
            interes_compensatorio_mora=mora.comp_mora, total_exigible=engine.dinero(ec.total_a_pagar + mora.total),
        ))
    vencidos = [l for l in listados if l.vencido]
    total_hoy = engine.dinero(sum((l.total_exigible for l in listados), CERO))
    saldo_anterior = engine.dinero(sum((l.total_exigible for l in listados[:-1]), CERO))

    # Compras con deuda (VIGENTE = aún no se terminan de pagar)
    compras = list(db.scalars(select(Compra).where(
        Compra.cliente_id == cliente.id, Compra.estado == "VIGENTE").order_by(Compra.fecha_hora)))
    fin_de_mes, en_cuotas = [], []
    for c in compras:
        if c.modalidad == "FIN_MES":
            cuota = c.cuotas[0]
            fin_de_mes.append(CompraFinDeMesOut(
                id=c.id, fecha_hora=a_hora_local(c.fecha_hora), descripcion=_descripcion(c),
                atendido_por=_atendido_por(db, c), monto=c.monto_total, dias=c.dias_gracia,
                interes=c.interes_total, total=cuota.cuota, fecha_pago=c.fecha_pago,
                en_listado=cuota.estado_cuenta_id is not None,
            ))
        else:
            cuotas = [CuotaPortalOut(
                numero=q.numero, fecha_vencimiento=q.fecha_vencimiento, monto=q.cuota,
                estado="PAGADA" if q.estado == "PAGADA" else ("VENCIDA" if q.fecha_vencimiento < hoy_ else "PENDIENTE"),
            ) for q in c.cuotas]
            en_cuotas.append(CompraEnCuotasOut(
                id=c.id, fecha_hora=a_hora_local(c.fecha_hora), descripcion=_descripcion(c),
                atendido_por=_atendido_por(db, c), monto=c.monto_total, num_cuotas=c.num_cuotas,
                valor_cuota=c.valor_cuota,
                saldo_pendiente=engine.dinero(sum((q.monto for q in cuotas if q.estado != "PAGADA"), CERO)),
                cuotas_pagadas=sum(1 for q in cuotas if q.estado == "PAGADA"), cuotas=cuotas,
            ))

    # Deuda que todavía no entra a ningún listado (cuotas futuras y compras del ciclo abierto)
    por_vencer = db.scalar(
        select(func.coalesce(func.sum(Cuota.cuota), 0))
        .join(Compra, Compra.id == Cuota.compra_id)
        .where(Compra.cliente_id == cliente.id, Compra.estado == "VIGENTE", Cuota.estado == "PENDIENTE",
               Cuota.estado_cuenta_id.is_(None))
    )
    deuda_por_vencer = engine.dinero(por_vencer or 0)

    proximas = [l.fecha_pago for l in listados if not l.vencido]
    return PortalResumenOut(
        cliente=f"{cliente.nombres} {cliente.apellidos}", dni=cliente.dni,
        tienda=tienda.nombre_comercial, tienda_ruc=tienda.ruc, credito=credito,
        estado_pago="EN_MORA" if vencidos else "AL_DIA",
        dias_mora=max((l.dias_mora for l in vencidos), default=0),
        vencio_el=vencidos[0].fecha_pago if vencidos else None,
        proxima_fecha_limite=min(proximas) if proximas else credito.proximo_pago,
        total_a_pagar_hoy=total_hoy, saldo_anterior=saldo_anterior, deuda_por_vencer=deuda_por_vencer,
        saldo_total=engine.dinero(total_hoy + deuda_por_vencer),
        listados_pendientes=listados, compras_fin_de_mes=fin_de_mes, compras_en_cuotas=en_cuotas,
    )
