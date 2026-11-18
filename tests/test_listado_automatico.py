"""
Generación automática del listado de pago en la fecha de corte (enunciado, punto 6) y resumen del portal.
Nadie llama a POST /statements/generar: el sistema genera los listados de los cortes ya pasados.
"""
from datetime import date, datetime
from decimal import Decimal as D

import pytest

from app.core import clock
from app.modules.customers import service as customers
from app.modules.finance import engine
from app.modules.payments import service as payments
from app.modules.payments.schemas import PagoIn
from app.modules.purchases import service as purchases
from app.modules.purchases.schemas import CompraIn, ItemIn
from app.modules.statements import service as statements
from tests.conftest import LIMA, lima, login

pytestmark = pytest.mark.integracion


def comprar(db, admin, cliente, producto, cantidad="1", modalidad="FIN_MES", n=1):
    return purchases.registrar_compra(db, admin, CompraIn(
        cliente_id=cliente.id, modalidad=modalidad, num_cuotas=n,
        items=[ItemIn(producto_id=producto.id, cantidad=D(cantidad))]))


def listados(db, admin, cliente):
    return statements.listar(db, admin, cliente.id, None, None, 50, 0)


# ------------------------------------------------------------- generación automática
def test_no_se_genera_antes_de_la_hora_de_corte(db, admin, cliente, productos):
    clock.fijar_ahora(lima(2026, 11, 15, 10, 0))
    comprar(db, admin, cliente, productos["pollo"])
    clock.fijar_ahora(lima(2026, 11, 25, 17, 59))  # corte: 25 a las 18:00
    assert listados(db, admin, cliente).total == 0


def test_se_genera_solo_al_llegar_la_hora_de_corte(db, admin, cliente, productos):
    clock.fijar_ahora(lima(2026, 11, 15, 10, 0))
    comprar(db, admin, cliente, productos["pollo"], "2")
    clock.fijar_ahora(lima(2026, 11, 25, 18, 0))
    pagina = listados(db, admin, cliente)
    assert pagina.total == 1
    ec = statements.obtener(db, admin, pagina.items[0].id)
    assert (ec.fecha_corte, ec.fecha_pago) == (date(2026, 11, 25), date(2026, 12, 5))
    assert ec.generado_en == datetime(2026, 11, 25, 18, 0, tzinfo=LIMA)  # fechado en el corte
    assert ec.total_a_pagar == engine.compra_fin_de_mes(
        D("21.00"), date(2026, 11, 15), date(2026, 12, 5), engine.Tasa("EFECTIVA", D("3.5"), 30)).total


def test_no_se_repite(db, admin, cliente, productos):
    clock.fijar_ahora(lima(2026, 11, 15, 10, 0))
    comprar(db, admin, cliente, productos["pollo"])
    clock.fijar_ahora(lima(2026, 11, 26, 9, 0))
    assert statements.asegurar_listados(db, cliente.tienda_id, cliente.id) == 1
    assert statements.asegurar_listados(db, cliente.tienda_id, cliente.id) == 0
    assert listados(db, admin, cliente).total == 1


def test_genera_tarde_los_cortes_que_ya_pasaron(db, admin, cliente, productos):
    """Compra en 3 cuotas el 15/11: cuotas vencen 05/01, 05/02 y 05/03 -> cortes 25/12, 25/01 y 25/02."""
    clock.fijar_ahora(lima(2026, 11, 15, 10, 0))
    comprar(db, admin, cliente, productos["arroz"], modalidad="CUOTAS", n=3)
    clock.fijar_ahora(lima(2027, 2, 26, 10, 0))  # nadie entró al sistema en 3 meses
    cortes = sorted(l.fecha_corte for l in listados(db, admin, cliente).items)
    assert cortes == [date(2026, 12, 25), date(2027, 1, 25), date(2027, 2, 25)]


def test_cliente_pasa_a_mora_sin_generar_a_mano(db, admin, cliente, productos):
    clock.fijar_ahora(lima(2026, 11, 15, 10, 0))
    comprar(db, admin, cliente, productos["pollo"])
    clock.fijar_ahora(lima(2026, 12, 10, 10, 0))  # pasó la fecha de pago (05/12)
    resumen = customers.resumen_credito(db, customers.obtener(db, admin, cliente.id))
    assert resumen.estado_pago == "EN_MORA"
    assert resumen.listados_pendientes == 1


def test_compra_despues_del_corte_va_al_listado_siguiente(db, admin, cliente, productos):
    clock.fijar_ahora(lima(2026, 11, 15, 10, 0))
    comprar(db, admin, cliente, productos["pollo"])
    clock.fijar_ahora(lima(2026, 11, 26, 10, 0))
    comprar(db, admin, cliente, productos["arroz"])  # ciclo de diciembre
    clock.fijar_ahora(lima(2026, 12, 26, 10, 0))
    por_corte = {l.fecha_corte: l.total_a_pagar for l in listados(db, admin, cliente).items}
    assert set(por_corte) == {date(2026, 11, 25), date(2026, 12, 25)}


def test_listado_pagado_no_se_regenera(db, admin, cliente, productos):
    clock.fijar_ahora(lima(2026, 11, 15, 10, 0))
    comprar(db, admin, cliente, productos["pollo"])
    clock.fijar_ahora(lima(2026, 12, 5, 12, 0))
    ec = listados(db, admin, cliente).items[0]
    payments.registrar_pago(db, admin, PagoIn(estado_cuenta_id=ec.id, monto=ec.total_a_pagar))
    clock.fijar_ahora(lima(2027, 1, 30, 12, 0))
    assert statements.asegurar_listados(db, cliente.tienda_id) == 0
    assert [l.estado for l in listados(db, admin, cliente).items] == ["PAGADO"]


# ------------------------------------------------------------------- resumen del portal
def test_resumen_del_portal(api, db, admin, cliente, productos, con_claves):
    clock.fijar_ahora(lima(2026, 11, 10, 10, 0))
    comprar(db, admin, cliente, productos["pollo"], "2")                       # fin de mes: 21.00
    cuotas = comprar(db, admin, cliente, productos["arroz"], modalidad="CUOTAS", n=3)
    clock.fijar_ahora(lima(2026, 12, 15, 12, 0))                              # 10 días de atraso

    r = api.get("/api/v1/portal/resumen", headers=login(api, *con_claves["cliente"]))
    assert r.status_code == 200, r.text
    s = r.json()
    assert (s["cliente"], s["dni"], s["tienda"]) == ("Rosa Test", "11112222", "Bodega Test")
    assert s["estado_pago"] == "EN_MORA"
    assert (s["dias_mora"], s["vencio_el"]) == (10, "2026-12-05")

    [listado] = s["listados_pendientes"]
    ec = statements.obtener(db, admin, listado["id"])
    mora = statements.calcular_mora(ec, date(2026, 12, 15))
    assert D(listado["total_exigible"]) == ec.total_a_pagar + mora.total
    assert D(s["total_a_pagar_hoy"]) == D(listado["total_exigible"])
    assert D(s["saldo_anterior"]) == 0

    [fm] = s["compras_fin_de_mes"]
    assert fm["descripcion"] == "2x Pollo fresco" and fm["atendido_por"] == "Admin Test" and fm["en_listado"]

    [cu] = s["compras_en_cuotas"]
    assert [q["estado"] for q in cu["cuotas"]] == ["PENDIENTE"] * 3
    total_cuotas = sum(q.cuota for q in cuotas.cronograma)
    assert D(cu["saldo_pendiente"]) == total_cuotas
    assert D(s["deuda_por_vencer"]) == total_cuotas                # aún no entran a ningún listado
    assert D(s["saldo_total"]) == D(s["total_a_pagar_hoy"]) + total_cuotas
    assert s["proxima_fecha_limite"] == "2027-01-05"


def test_resumen_del_portal_sin_deuda(api, cliente, con_claves):
    s = api.get("/api/v1/portal/resumen", headers=login(api, *con_claves["cliente"])).json()
    assert s["estado_pago"] == "AL_DIA" and s["dias_mora"] == 0 and s["vencio_el"] is None
    assert D(s["saldo_total"]) == 0 and s["listados_pendientes"] == [] and s["compras_en_cuotas"] == []


def test_resumen_solo_para_vecinos(api, con_claves):
    r = api.get("/api/v1/portal/resumen", headers=login(api, *con_claves["admin"]))
    assert r.status_code == 403
