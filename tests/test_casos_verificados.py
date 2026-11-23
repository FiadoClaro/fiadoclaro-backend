"""
Casos verificados a mano en Swagger (método francés con gracia total).

    Caso A: S/ 1000, TEM 3 %, 3 cuotas, compra 15/11, corte 20, pago 26 -> 11 días de gracia.
    Caso B: S/ 500, TEA 60 %, 6 cuotas, compra 10/11, pago 26 -> 16 días de gracia.

Se compara el cronograma completo fila por fila, tal como lo muestra la API.
"""
from datetime import date, datetime, time
from decimal import Decimal as D
from zoneinfo import ZoneInfo

import pytest

from app.modules.finance import engine
from app.modules.finance.engine import Tasa

LIMA = ZoneInfo("America/Lima")
TEM_3 = Tasa("EFECTIVA", D("3"), 30)
TEA_60 = Tasa("EFECTIVA", D("60"), 360)


def filas(r):
    return [(f.fecha_vencimiento, f.saldo_inicial, f.interes, f.amortizacion, f.cuota, f.saldo_final)
            for f in r.filas]


def test_caso_a_desde_la_fecha_de_compra_hasta_la_tcea():
    """Del ciclo (corte 20, pago 26) al cronograma completo y la TCEA exacta."""
    ciclo = engine.ciclo_de_compra(datetime(2026, 11, 15, 10, 0, tzinfo=LIMA), 20, time(18, 0), 26)
    assert ciclo.fecha_pago == date(2026, 11, 26)

    r = engine.compra_en_cuotas(D("1000"), date(2026, 11, 15), ciclo.fecha_pago, 3, TEM_3)
    assert r.dias_gracia == 11
    assert r.monto_capitalizado == D("1010.90")
    assert r.cuota == D("357.38")
    assert filas(r) == [
        (date(2026, 12, 26), D("1010.90"), D("30.33"), D("327.05"), D("357.38"), D("683.85")),
        (date(2027, 1, 26), D("683.85"), D("20.52"), D("336.86"), D("357.38"), D("346.99")),
        (date(2027, 2, 26), D("346.99"), D("10.41"), D("346.99"), D("357.40"), D("0.00")),
    ]
    assert r.total_intereses == D("72.16")
    assert r.total_pagado == D("1072.16")
    assert r.tcea_pct == D("42.5834840280")


def test_caso_b_tea_60_en_seis_cuotas():
    """Con TEA (no TEM) el motor convierte la tasa y arma las 6 cuotas; la última absorbe el redondeo."""
    r = engine.compra_en_cuotas(D("500"), date(2026, 11, 10), date(2026, 11, 26), 6, TEA_60)
    assert r.dias_gracia == 16
    assert r.monto_capitalizado == D("510.55")
    assert r.interes_gracia == D("10.55")
    assert r.cuota == D("97.38")
    assert filas(r) == [
        (date(2026, 12, 26), D("510.55"), D("20.39"), D("76.99"), D("97.38"), D("433.56")),
        (date(2027, 1, 26), D("433.56"), D("17.32"), D("80.06"), D("97.38"), D("353.50")),
        (date(2027, 2, 26), D("353.50"), D("14.12"), D("83.26"), D("97.38"), D("270.24")),
        (date(2027, 3, 26), D("270.24"), D("10.79"), D("86.59"), D("97.38"), D("183.65")),
        (date(2027, 4, 26), D("183.65"), D("7.34"), D("90.04"), D("97.38"), D("93.61")),
        (date(2027, 5, 26), D("93.61"), D("3.74"), D("93.61"), D("97.35"), D("0.00")),
    ]
    assert r.total_pagado == D("584.25")
    assert r.total_intereses == D("84.25")


def test_tea_60_a_tem_y_a_tasa_de_16_dias():
    """TEM = 1.6^(30/360) - 1 y la tasa de la gracia = 1.6^(16/360) - 1 (calculadas a mano)."""
    assert engine.tasa_q(engine.tem(TEA_60)) == D("0.0399441077")
    te_16 = engine.tasa_efectiva_periodo(TEA_60, 16)
    assert engine.tasa_q(te_16) == D("0.0211087535")
    # Esa tasa es la que capitaliza los 16 días del caso B: 500 -> 510.55
    assert engine.dinero(D("500") * (1 + te_16)) == D("510.55")


@pytest.mark.parametrize("tope, se_acepta", [
    (D("114.68"), True),   # tope BCRP en soles: 60 % entra sin problema
    (D("60"), True),       # justo en el tope: se permite (no lo supera)
    (D("59.99"), False),   # un centésimo por debajo: se rechaza
])
def test_tope_bcrp_en_el_limite_con_tea_60(tope, se_acepta):
    if se_acepta:
        engine.validar_tope(TEA_60, tope, "tasa compensatoria")
    else:
        with pytest.raises(ValueError, match="TEA de 60.0000000000 %, que supera el tope"):
            engine.validar_tope(TEA_60, tope, "tasa compensatoria")
