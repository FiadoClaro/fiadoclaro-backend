"""
Mora y prelación (punto 5, punto 6 y Anexo A).

    Moratorio:                 IM    = pago total × [(1 + TEP_mora)^(días de mora) − 1]
    Compensatorio por atraso:  IC_m  = línea      × [(1 + TEP_comp)^(días de mora) − 1]
    Prelación: mora -> compensatorio por atraso -> compensatorio del listado -> capital
"""
from datetime import date
from decimal import Decimal as D

import pytest

from app.modules.finance import engine
from app.modules.finance.engine import Tasa

PACTADA = date(2026, 12, 5)
MORA_2 = Tasa("EFECTIVA", D("2"), 30)


# ----------------------------------------------------------------- días de mora
@pytest.mark.parametrize("pago_real, dias", [
    (date(2026, 12, 1), 0),    # pagó antes
    (date(2026, 12, 5), 0),    # pagó el día pactado
    (date(2026, 12, 6), 1),
    (date(2026, 12, 15), 10),
    (date(2027, 1, 4), 30),
])
def test_dias_de_mora(pago_real, dias):
    assert engine.dias_mora(PACTADA, pago_real) == dias


# ---------------------------------------------------------------- interés moratorio
def test_sin_atraso_no_hay_mora():
    r = engine.interes_moratorio(D("1000"), PACTADA, PACTADA, MORA_2)
    assert r.dias_mora == 0 and r.interes_moratorio == 0


def test_pago_anticipado_no_genera_mora_negativa():
    r = engine.interes_moratorio(D("1000"), PACTADA, date(2026, 11, 30), MORA_2)
    assert r.dias_mora == 0 and r.interes_moratorio == 0


def test_mora_un_mes_completo_es_la_tasa_moratoria_mensual():
    r = engine.interes_moratorio(D("1000"), PACTADA, date(2027, 1, 4), MORA_2)
    assert (r.dias_mora, r.interes_moratorio) == (30, D("20.00"))


def test_mora_del_listado_de_demostracion():
    """Listado de S/ 46.68 pagado 10 días tarde con una tasa moratoria efectiva mensual del 2 %."""
    r = engine.interes_moratorio(D("46.68"), PACTADA, date(2026, 12, 15), MORA_2)
    assert (r.dias_mora, r.interes_moratorio) == (10, D("0.31"))


def test_mora_con_tasa_efectiva_anual():
    r = engine.interes_moratorio(D("1000"), PACTADA, date(2027, 1, 19), Tasa("EFECTIVA", D("15"), 360))
    assert (r.dias_mora, r.interes_moratorio) == (45, D("17.62"))


def test_mora_con_tasa_nominal():
    r = engine.interes_moratorio(D("1000"), PACTADA, date(2026, 12, 20), Tasa("NOMINAL", D("18"), 360, 1))
    assert (r.dias_mora, r.interes_moratorio) == (15, D("7.53"))


def test_mora_crece_con_los_dias_de_atraso():
    moras = [engine.interes_moratorio(D("500"), PACTADA, date(2026, 12, d), MORA_2).interes_moratorio
             for d in range(6, 32)]
    assert moras == sorted(moras)


# ------------------------------------------------------- compensatorio por días de atraso
def test_compensatorio_por_atraso():
    ic = engine.interes_compensatorio_mora(D("1000"), PACTADA, date(2026, 12, 15), Tasa("EFECTIVA", D("3.5"), 30))
    assert ic == D("11.53")


def test_compensatorio_por_atraso_es_cero_si_paga_a_tiempo():
    assert engine.interes_compensatorio_mora(D("1000"), PACTADA, PACTADA, Tasa("EFECTIVA", D("3.5"), 30)) == 0


def test_compensatorio_y_moratorio_son_independientes():
    """Con la misma base y días, cada uno usa su propia tasa."""
    fecha = date(2026, 12, 15)
    ic = engine.interes_compensatorio_mora(D("1000"), PACTADA, fecha, Tasa("EFECTIVA", D("2"), 30))
    im = engine.interes_moratorio(D("1000"), PACTADA, fecha, MORA_2).interes_moratorio
    assert ic == im  # misma tasa -> mismo monto: la fórmula es la misma, cambia solo la tasa


# ------------------------------------------------------------------------- prelación
def test_prelacion_orden_y_conceptos():
    imp = engine.aplicar_prelacion(D("47.53"), D("0.31"), D("0.54"), D("1.18"), D("45.50"))
    assert [(i.orden, i.concepto) for i in imp] == [
        (1, "INTERES_MORATORIO"),
        (2, "INTERES_COMPENSATORIO_MORA"),
        (3, "INTERES_COMPENSATORIO"),
        (4, "CAPITAL"),
    ]
    assert all(i.imputado == i.exigible and i.saldo == 0 for i in imp)


def test_prelacion_monto_insuficiente_cubre_primero_la_mora():
    """Si alcanzara solo para una parte, primero se cubre la mora y el capital queda al final."""
    imp = {i.concepto: i for i in engine.aplicar_prelacion(D("10"), D("4"), D("3"), D("5"), D("100"))}
    assert imp["INTERES_MORATORIO"].imputado == D("4")
    assert imp["INTERES_COMPENSATORIO_MORA"].imputado == D("3")
    assert imp["INTERES_COMPENSATORIO"].imputado == D("3")
    assert imp["INTERES_COMPENSATORIO"].saldo == D("2")
    assert imp["CAPITAL"].imputado == D("0")
    assert imp["CAPITAL"].saldo == D("100")


def test_prelacion_sin_mora():
    imp = engine.aplicar_prelacion(D("46.68"), D("0"), D("0"), D("1.18"), D("45.50"))
    assert [i.imputado for i in imp] == [D("0"), D("0"), D("1.18"), D("45.50")]
