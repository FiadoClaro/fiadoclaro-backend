"""
Registro de compras fiadas (enunciado, puntos 2, 4 y 5).

Flujo: validar cliente y productos -> verificar crédito disponible -> validar topes de tasa
-> decidir el ciclo con la fecha y hora de corte -> calcular (fin de mes o francés)
-> guardar compra con COPIA de la tasa y su cronograma de cuotas.
"""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import a_hora_local, ahora
from app.core.deps import Actor
from app.core.errors import BusinessError, NotFoundError
from app.modules.audit.service import registrar
from app.modules.customers import service as customers
from app.modules.customers.models import Cliente
from app.modules.finance import engine
from app.modules.finance.service import validar_topes
from app.modules.products.models import Producto
from app.modules.purchases.models import Compra, CompraDetalle, Cuota
from app.modules.purchases.schemas import (
    CompraIn,
    CompraOut,
    CompraResumenOut,
    CuotaOut,
    DetalleOut,
    SimulacionOut,
    TasaPactadaOut,
)
from app.modules.statements.models import EstadoCuenta

CERO = Decimal("0")


@dataclass
class _Calculo:
    cliente: Cliente
    sim: SimulacionOut
    comp: engine.Tasa
    mora: engine.Tasa


def _tasa_out(t: engine.Tasa) -> TasaPactadaOut:
    eq = engine.resumen_tasa(t)
    return TasaPactadaOut(tipo=t.tipo, valor=t.valor_pct, periodo_dias=t.periodo_dias,
                          capitalizacion_dias=t.capitalizacion_dias, tem_pct=eq["tem_pct"], tea_pct=eq["tea_pct"])


def _calcular(db: Session, actor: Actor, data: CompraIn) -> _Calculo:
    cliente = customers.obtener(db, actor, data.cliente_id)
    if cliente.estado != "ACTIVO":
        raise BusinessError("El cliente está dado de baja")
    cond = cliente.condicion

    # 1. Fecha y hora de la compra (hora local de la tienda)
    fecha_hora = a_hora_local(data.fecha_hora) if data.fecha_hora else ahora()
    if fecha_hora > ahora():
        raise BusinessError("La fecha y hora de la compra no puede ser futura")

    # 2. Productos: activos, de la tienda, misma moneda y que permitan la modalidad
    detalles: list[DetalleOut] = []
    max_meses_productos: list[int] = []
    for item in data.items:
        p = db.get(Producto, item.producto_id)
        if not p or p.tienda_id != actor.tienda_id:
            raise NotFoundError("Producto", item.producto_id)
        if p.estado != "ACTIVO":
            raise BusinessError(f"El producto '{p.nombre}' está dado de baja")
        if p.moneda != cond.moneda:
            raise BusinessError(f"'{p.nombre}' está en {p.moneda} y el crédito del cliente en {cond.moneda}")
        if data.modalidad == "FIN_MES" and not p.permite_fin_mes:
            raise BusinessError(f"'{p.nombre}' no se puede fiar a fin de mes")
        if data.modalidad == "CUOTAS":
            if not p.permite_cuotas:
                raise BusinessError(f"'{p.nombre}' no se puede fiar en cuotas")
            max_meses_productos.append(p.max_meses)
        detalles.append(DetalleOut(
            producto_id=p.id, descripcion=p.nombre, cantidad=item.cantidad,
            precio_unitario=p.precio_lista_credito, subtotal=engine.dinero(item.cantidad * p.precio_lista_credito),
        ))

    # 3. Plazo máximo: el menor entre el del cliente y el de cada producto
    if data.modalidad == "CUOTAS":
        maximo = min([cond.max_meses, *max_meses_productos])
        if data.num_cuotas > maximo:
            raise BusinessError(f"El máximo permitido para esta compra es {maximo} meses", code="excede_plazo")

    # 4. Crédito disponible (no se permiten compras que excedan el límite)
    monto = engine.dinero(sum((d.subtotal for d in detalles), CERO))
    disponible = engine.dinero(cond.limite_credito - customers.capital_pendiente(db, cliente.id))
    if monto > disponible:
        raise BusinessError(
            f"La compra (S/ {monto}) excede el crédito disponible del cliente (S/ {disponible})",
            code="excede_credito",
        )

    # 5. Tasas pactadas y validación del tope vigente
    comp, mora = customers.tasas_de_condicion(cond)
    validar_topes(db, comp, mora, fecha_hora.date())

    # 6. Ciclo según fecha y hora de corte
    ciclo = engine.ciclo_de_compra(fecha_hora, cond.dia_corte, cond.hora_corte, cond.dia_pago)
    _validar_ciclo_abierto(db, cliente.id, ciclo.fecha_corte)

    # 7. Cálculo financiero
    f_compra = fecha_hora.date()
    if data.modalidad == "FIN_MES":
        r = engine.compra_fin_de_mes(monto, f_compra, ciclo.fecha_pago, comp)
        cronograma = [CuotaOut(numero=1, fecha_vencimiento=ciclo.fecha_pago, saldo_inicial=monto,
                               interes=r.interes, amortizacion=monto, cuota=r.total, saldo_final=CERO)]
        interes, capitalizado, valor_cuota, total = r.interes, monto, r.total, r.total
        tcea_pct = engine.tasa_q(engine.tcea(monto, f_compra, [(ciclo.fecha_pago, r.total)]) * 100)
        dias = r.dias
    else:
        r = engine.compra_en_cuotas(monto, f_compra, ciclo.fecha_pago, data.num_cuotas, comp)
        cronograma = [CuotaOut(**f.__dict__) for f in r.filas]
        interes, capitalizado, valor_cuota = r.total_intereses, r.monto_capitalizado, r.cuota
        total, tcea_pct, dias = r.total_pagado, r.tcea_pct, r.dias_gracia

    sim = SimulacionOut(
        cliente_id=cliente.id, modalidad=data.modalidad, num_cuotas=data.num_cuotas, moneda=cond.moneda,
        fecha_hora=fecha_hora, fecha_corte=ciclo.fecha_corte, fecha_pago=ciclo.fecha_pago, dias_gracia=dias,
        detalles=detalles, monto_total=monto, tasa=_tasa_out(comp), interes_total=interes,
        monto_capitalizado=capitalizado, valor_cuota=valor_cuota, total_a_pagar=total, tcea_pct=tcea_pct,
        cronograma=cronograma, credito_disponible_antes=disponible,
        credito_disponible_despues=engine.dinero(disponible - monto),
    )
    return _Calculo(cliente, sim, comp, mora)


def _validar_ciclo_abierto(db: Session, cliente_id: int, fecha_corte: date) -> None:
    """Una compra no puede caer en un ciclo cuyo listado ya fue pagado."""
    pagado = db.scalar(select(EstadoCuenta.id).where(
        EstadoCuenta.cliente_id == cliente_id, EstadoCuenta.fecha_corte >= fecha_corte,
        EstadoCuenta.estado == "PAGADO",
    ))
    if pagado:
        raise BusinessError("Ese ciclo ya fue facturado y pagado; registra la compra con la fecha actual")


# --------------------------------------------------------------- comandos
def simular(db: Session, actor: Actor, data: CompraIn) -> SimulacionOut:
    return _calcular(db, actor, data).sim


def registrar_compra(db: Session, actor: Actor, data: CompraIn) -> CompraOut:
    calc = _calcular(db, actor, data)
    s, comp, mora = calc.sim, calc.comp, calc.mora
    compra = Compra(
        tienda_id=actor.tienda_id, cliente_id=s.cliente_id, registrado_por=actor.id, fecha_hora=s.fecha_hora,
        modalidad=s.modalidad, num_cuotas=s.num_cuotas, moneda=s.moneda, monto_total=s.monto_total,
        fecha_corte=s.fecha_corte, fecha_pago=s.fecha_pago, dias_gracia=s.dias_gracia,
        tipo_tasa=comp.tipo, tasa=comp.valor_pct, periodo_tasa_dias=comp.periodo_dias,
        capitalizacion_dias=comp.capitalizacion_dias, tipo_tasa_mora=mora.tipo, tasa_mora=mora.valor_pct,
        periodo_tasa_mora_dias=mora.periodo_dias, capitalizacion_mora_dias=mora.capitalizacion_dias,
        tem=engine.tasa_q(engine.tem(comp)), tea=engine.tasa_q(engine.tea(comp)),
        interes_total=s.interes_total, monto_capitalizado=s.monto_capitalizado, valor_cuota=s.valor_cuota,
        tcea=engine.tasa_q(s.tcea_pct / 100) if s.tcea_pct is not None else None, estado="VIGENTE",
        detalles=[CompraDetalle(**d.model_dump()) for d in s.detalles],
        cuotas=[Cuota(**c.model_dump(exclude={"estado"}), estado="PENDIENTE") for c in s.cronograma],
    )
    db.add(compra)
    db.flush()
    registrar(db, actor, "CREAR", "compra", compra.id, {
        "cliente_id": s.cliente_id, "modalidad": s.modalidad, "num_cuotas": s.num_cuotas,
        "monto": s.monto_total, "fecha_corte": s.fecha_corte, "fecha_pago": s.fecha_pago,
    })
    db.commit()
    return CompraOut(**s.model_dump(), id=compra.id, estado=compra.estado, registrado_por=actor.id)


def obtener(db: Session, actor: Actor, compra_id: int) -> Compra:
    compra = db.get(Compra, compra_id)
    if not compra or compra.tienda_id != actor.tienda_id:
        raise NotFoundError("Compra", compra_id)
    return compra


def tasas_de_compra(c: Compra) -> tuple[engine.Tasa, engine.Tasa]:
    """Tasas COPIADAS en la compra (no las vigentes del cliente)."""
    return (
        engine.Tasa(c.tipo_tasa, c.tasa, c.periodo_tasa_dias, c.capitalizacion_dias),
        engine.Tasa(c.tipo_tasa_mora, c.tasa_mora, c.periodo_tasa_mora_dias, c.capitalizacion_mora_dias),
    )


def to_out(c: Compra) -> CompraOut:
    comp, _ = tasas_de_compra(c)
    return CompraOut(
        id=c.id, estado=c.estado, registrado_por=c.registrado_por, cliente_id=c.cliente_id,
        modalidad=c.modalidad, num_cuotas=c.num_cuotas, moneda=c.moneda, fecha_hora=a_hora_local(c.fecha_hora),
        fecha_corte=c.fecha_corte, fecha_pago=c.fecha_pago, dias_gracia=c.dias_gracia,
        detalles=[DetalleOut.model_validate(d) for d in c.detalles], monto_total=c.monto_total,
        tasa=_tasa_out(comp), interes_total=c.interes_total, monto_capitalizado=c.monto_capitalizado,
        valor_cuota=c.valor_cuota, total_a_pagar=sum((q.cuota for q in c.cuotas), CERO),
        tcea_pct=engine.tasa_q(c.tcea * 100) if c.tcea is not None else None,
        cronograma=[CuotaOut.model_validate(q) for q in c.cuotas],
    )


def listar(db: Session, actor: Actor, cliente_id: int | None, estado: str | None,
           desde: date | None, hasta: date | None, limit: int, offset: int) -> list[CompraResumenOut]:
    q = select(Compra).where(Compra.tienda_id == actor.tienda_id)
    if actor.rol == "CLIENTE":
        cliente_id = db.scalar(select(Cliente.id).where(Cliente.usuario_id == actor.id))
    if cliente_id:
        q = q.where(Compra.cliente_id == cliente_id)
    if estado:
        q = q.where(Compra.estado == estado)
    if desde:
        q = q.where(Compra.fecha_hora >= a_hora_local(_inicio(desde)))
    if hasta:
        q = q.where(Compra.fecha_hora < a_hora_local(_inicio(hasta, dias=1)))
    compras = db.scalars(q.order_by(Compra.fecha_hora.desc()).limit(limit).offset(offset))
    return [CompraResumenOut.model_validate(c) for c in compras]


def _inicio(d: date, dias: int = 0) -> datetime:
    return datetime.combine(d + timedelta(days=dias), time.min)
