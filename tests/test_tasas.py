"""
Conversión de tasas (Anexo A: base 360, mes de 30 días, conversión explícita nominal -> efectiva).

Los valores esperados se calcularon a mano con las fórmulas del curso:
    Efectiva -> efectiva:  TEP2 = (1 + TEP1)^(días2 / días1) - 1
    Nominal  -> efectiva:  TEP  = (1 + TN / m)^n - 1
"""
from decimal import Decimal as D

import pytest

from app.modules.finance import engine
from app.modules.finance.engine import Tasa

EFECTIVA, NOMINAL = "EFECTIVA", "NOMINAL"


def pct(x: D) -> D:
    """Fracción -> redondeo a 10 decimales para comparar."""
    return engine.tasa_q(x)


# ------------------------------------------------------------ efectiva -> efectiva
def test_tem_a_tea():
    assert pct(engine.tea(Tasa(EFECTIVA, D("3.5"), 30))) == D("0.5110686573")


def test_tea_a_tem():
    assert pct(engine.tem(Tasa(EFECTIVA, D("12"), 360))) == D("0.0094887929")


def test_tem_a_ted():
    assert pct(engine.tasa_efectiva_periodo(Tasa(EFECTIVA, D("3"), 30), 1)) == D("0.0009857790")


def test_tasa_del_mismo_periodo_no_cambia():
    assert pct(engine.tem(Tasa(EFECTIVA, D("3.5"), 30))) == D("0.0350000000")
    assert pct(engine.tea(Tasa(EFECTIVA, D("40"), 360))) == D("0.4000000000")


def test_ida_y_vuelta_tem_tea_tem():
    tea = engine.tea(Tasa(EFECTIVA, D("2.75"), 30)) * 100
    assert pct(engine.tem(Tasa(EFECTIVA, tea, 360))) == D("0.0275000000")


# -------------------------------------------------------------- nominal -> efectiva
def test_tna_capitalizacion_diaria_a_tem():
    assert pct(engine.tem(Tasa(NOMINAL, D("36"), 360, 1))) == D("0.0304390875")


def test_tna_capitalizacion_diaria_a_tea():
    assert pct(engine.tea(Tasa(NOMINAL, D("36"), 360, 1))) == D("0.4330716103")


def test_nominal_sin_capitalizacion_usa_diaria_por_defecto():
    con_diaria = engine.tea(Tasa(NOMINAL, D("36"), 360, 1))
    por_defecto = engine.tea(Tasa(NOMINAL, D("36"), 360, None))
    assert con_diaria == por_defecto


def test_tna_capitalizacion_mensual():
    t = Tasa(NOMINAL, D("24"), 360, 30)
    assert pct(engine.tem(t)) == D("0.0200000000")
    assert pct(engine.tasa_efectiva_periodo(t, 90)) == D("0.0612080000")  # trimestral: 1.02^3 - 1


def test_tnm_y_tna_equivalentes_dan_la_misma_tem():
    """3 % nominal mensual = 36 % nominal anual (ambas con capitalización diaria)."""
    tnm = engine.tem(Tasa(NOMINAL, D("3"), 30, 1))
    tna = engine.tem(Tasa(NOMINAL, D("36"), 360, 1))
    assert pct(tnm) == pct(tna) == D("0.0304390875")


def test_nominal_rinde_mas_que_su_efectiva_de_igual_valor():
    """Por la capitalización, una TN del 36 % equivale a una TEA mayor al 36 %."""
    assert engine.tea(Tasa(NOMINAL, D("36"), 360, 1)) > engine.tea(Tasa(EFECTIVA, D("36"), 360))


def test_cero_dias_o_tasa_cero_no_genera_interes():
    assert engine.tasa_efectiva_periodo(Tasa(EFECTIVA, D("3.5"), 30), 0) == 0
    assert engine.tasa_efectiva_periodo(Tasa(EFECTIVA, D("0"), 30), 45) == 0


# ---------------------------------------------------------------- precisión y redondeo
def test_tasas_con_al_menos_7_decimales():
    resumen = engine.resumen_tasa(Tasa(EFECTIVA, D("3.5"), 30))
    for valor in resumen.values():
        assert -valor.as_tuple().exponent >= 7


def test_redondeo_monetario_half_up():
    assert engine.dinero(D("10.005")) == D("10.01")
    assert engine.dinero(D("10.004")) == D("10.00")
    assert engine.dinero(D("2.675")) == D("2.68")  # con float daría 2.67


# ----------------------------------------------------------------------- validaciones
@pytest.mark.parametrize("kwargs", [
    dict(tipo="MIXTA", valor_pct=D("3"), periodo_dias=30),
    dict(tipo=EFECTIVA, valor_pct=D("-1"), periodo_dias=30),
    dict(tipo=EFECTIVA, valor_pct=D("3"), periodo_dias=0),
    dict(tipo=NOMINAL, valor_pct=D("3"), periodo_dias=30, capitalizacion_dias=60),
])
def test_tasa_invalida(kwargs):
    with pytest.raises(ValueError):
        Tasa(**kwargs)


def test_tope_bcrp():
    t = Tasa(EFECTIVA, D("3.5"), 30)  # TEA 51.1 %
    engine.validar_tope(t, D("114.13"), "tasa compensatoria")  # no lanza
    with pytest.raises(ValueError, match="supera el tope"):
        engine.validar_tope(t, D("50"), "tasa compensatoria")
