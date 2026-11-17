"""
Interés compensatorio según el tiempo transcurrido (punto 5: compras a fin de mes pagan
intereses por los días entre la compra y la fecha de pago).

    I = P × [(1 + TEP)^(días / días del periodo) − 1]
"""
from datetime import date, timedelta
from decimal import Decimal as D

import pytest

from app.modules.finance import engine
from app.modules.finance.engine import Tasa

TEM_3 = Tasa("EFECTIVA", D("3"), 30)
TEM_35 = Tasa("EFECTIVA", D("3.5"), 30)


@pytest.mark.parametrize("dias, interes", [
    (0, D("0.00")),
    (1, D("0.99")),
    (15, D("14.89")),
    (30, D("30.00")),     # un mes completo = exactamente la TEM
    (60, D("60.90")),     # 1.03^2 - 1: interés compuesto, no 60.00
    (90, D("92.73")),
    (180, D("194.05")),
    (360, D("425.76")),   # TEA de una TEM del 3 %
])
def test_interes_de_1000_a_tem_3_por_dias(dias, interes):
    inicio = date(2026, 1, 1)
    r = engine.compra_fin_de_mes(D("1000"), inicio, inicio + timedelta(days=dias), TEM_3)
    assert r.dias == dias
    assert r.interes == interes
    assert r.total == D("1000") + interes


def test_interes_es_compuesto_no_simple():
    inicio = date(2026, 1, 1)
    dos_meses = engine.compra_fin_de_mes(D("1000"), inicio, inicio + timedelta(days=60), TEM_3).interes
    un_mes = engine.compra_fin_de_mes(D("1000"), inicio, inicio + timedelta(days=30), TEM_3).interes
    assert dos_meses > 2 * un_mes


def test_interes_crece_con_los_dias():
    inicio = date(2026, 1, 1)
    intereses = [engine.compra_fin_de_mes(D("500"), inicio, inicio + timedelta(days=d), TEM_35).interes
                 for d in range(0, 121, 5)]
    assert intereses == sorted(intereses)
    assert len(set(intereses)) == len(intereses)


def test_interes_proporcional_al_monto():
    inicio, fin = date(2026, 1, 1), date(2026, 1, 21)
    i100 = engine.compra_fin_de_mes(D("100"), inicio, fin, TEM_35).interes
    i1000 = engine.compra_fin_de_mes(D("1000"), inicio, fin, TEM_35).interes
    assert abs(i1000 - 10 * i100) <= D("0.05")  # solo difiere por redondeo


@pytest.mark.parametrize("monto, compra, pago, interes", [
    (D("100"), date(2026, 11, 15), date(2026, 12, 5), D("2.32")),    # 20 días
    (D("500"), date(2026, 10, 21), date(2026, 12, 5), D("26.48")),   # 45 días
])
def test_compra_fin_de_mes_tem_35(monto, compra, pago, interes):
    r = engine.compra_fin_de_mes(monto, compra, pago, TEM_35)
    assert r.interes == interes


def test_fin_de_mes_con_tasa_nominal():
    """TNA 36 % con capitalización diaria durante 30 días = TEM 3.0439 %."""
    r = engine.compra_fin_de_mes(D("1000"), date(2026, 1, 1), date(2026, 1, 31), Tasa("NOMINAL", D("36"), 360, 1))
    assert r.interes == D("30.44")


def test_pagar_el_mismo_dia_no_genera_interes():
    r = engine.compra_fin_de_mes(D("250"), date(2026, 3, 5), date(2026, 3, 5), TEM_35)
    assert r.interes == D("0.00") and r.total == D("250.00")
