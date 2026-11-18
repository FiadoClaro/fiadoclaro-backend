"""
Método francés vencido ordinario con meses de 30 días (punto 4).

    Gracia total: P' = P × (1 + TEP_gracia)        (días compra -> fecha de pago del ciclo)
    Cuota:        R  = P' × i / (1 − (1 + i)^−n)   (i = TEM)
    Primera cuota: un mes después de la fecha de pago del ciclo.
"""
from datetime import date
from decimal import Decimal as D

import pytest

from app.modules.finance import engine
from app.modules.finance.engine import Tasa

TEM_3 = Tasa("EFECTIVA", D("3"), 30)


def test_cronograma_sin_gracia():
    """Ejemplo clásico: 1000 a TEM 3 % en 3 cuotas -> cuota de 353.53."""
    r = engine.compra_en_cuotas(D("1000"), date(2026, 9, 26), date(2026, 9, 26), 3, TEM_3)
    assert r.dias_gracia == 0
    assert r.monto_capitalizado == D("1000.00")
    assert r.cuota == D("353.53")
    filas = [(f.saldo_inicial, f.interes, f.amortizacion, f.cuota, f.saldo_final) for f in r.filas]
    assert filas == [
        (D("1000.00"), D("30.00"), D("323.53"), D("353.53"), D("676.47")),
        (D("676.47"), D("20.29"), D("333.24"), D("353.53"), D("343.23")),
        (D("343.23"), D("10.30"), D("343.23"), D("353.53"), D("0.00")),
    ]


def test_ejemplo_del_enunciado_con_gracia():
    """Compra el 15/09, pago el 26: 11 días de gracia capitalizados; cuotas 26/10, 26/11 y 26/12."""
    r = engine.compra_en_cuotas(D("1000"), date(2026, 9, 15), date(2026, 9, 26), 3, TEM_3)
    assert r.dias_gracia == 11
    assert r.monto_capitalizado == D("1010.90")
    assert r.interes_gracia == D("10.90")
    assert r.cuota == D("357.38")
    assert [f.fecha_vencimiento for f in r.filas] == [date(2026, 10, 26), date(2026, 11, 26), date(2026, 12, 26)]
    assert [f.interes for f in r.filas] == [D("30.33"), D("20.52"), D("10.41")]
    # La última cuota absorbe el redondeo para dejar el saldo en cero
    assert r.filas[-1].cuota == D("357.40")
    assert r.total_pagado == D("1072.16")
    assert r.total_intereses == D("72.16")


@pytest.mark.parametrize("n", [1, 2, 3, 6, 12, 24, 36])
def test_invariantes_del_cronograma(n):
    r = engine.compra_en_cuotas(D("1234.56"), date(2026, 3, 3), date(2026, 3, 26), n, Tasa("EFECTIVA", D("3.5"), 30))
    assert len(r.filas) == n
    # Las amortizaciones devuelven exactamente el monto capitalizado
    assert sum(f.amortizacion for f in r.filas) == r.monto_capitalizado
    assert r.filas[-1].saldo_final == 0
    for anterior, fila in zip(r.filas, r.filas[1:]):
        assert fila.saldo_inicial == anterior.saldo_final        # el saldo se encadena
        assert fila.interes < anterior.interes                   # el interés baja
        assert fila.amortizacion >= anterior.amortizacion        # la amortización sube
    for f in r.filas:
        assert f.cuota == f.interes + f.amortizacion
        assert f.interes == engine.dinero(f.saldo_inicial * r.tem)
    # Todas las cuotas iguales salvo la última, que absorbe el redondeo acumulado:
    # la cuota redondeada difiere a lo más 0.005 de la exacta y esa diferencia se capitaliza
    # mes a mes, así que el ajuste no supera 0.005 × Σ(1 + i)^k (+ 1 céntimo).
    assert all(f.cuota == r.cuota for f in r.filas[:-1])
    cota = D("0.005") * sum((1 + r.tem) ** k for k in range(n)) + D("0.01")
    assert abs(r.filas[-1].cuota - r.cuota) <= cota
    assert r.total_pagado == sum(f.cuota for f in r.filas)


def test_una_cuota_equivale_a_un_mes_de_interes():
    r = engine.compra_en_cuotas(D("1000"), date(2026, 9, 26), date(2026, 9, 26), 1, TEM_3)
    assert r.cuota == D("1030.00")
    assert r.filas[0].fecha_vencimiento == date(2026, 10, 26)


def test_tasa_cero_divide_en_partes_iguales():
    r = engine.compra_en_cuotas(D("900"), date(2026, 9, 26), date(2026, 9, 26), 3, Tasa("EFECTIVA", D("0"), 30))
    assert [f.cuota for f in r.filas] == [D("300.00")] * 3
    assert r.total_intereses == D("0.00")


def test_mas_cuotas_mas_intereses():
    totales = [engine.compra_en_cuotas(D("1000"), date(2026, 9, 15), date(2026, 9, 26), n, TEM_3).total_intereses
               for n in (1, 3, 6, 12)]
    assert totales == sorted(totales)


def test_con_tasa_nominal():
    r = engine.compra_en_cuotas(D("1000"), date(2026, 9, 26), date(2026, 9, 26), 3, Tasa("NOMINAL", D("36"), 360, 1))
    assert r.tem == D("0.0304390875")
    assert sum(f.amortizacion for f in r.filas) == D("1000.00")


def test_cero_cuotas_no_se_permite():
    with pytest.raises(ValueError):
        engine.compra_en_cuotas(D("100"), date(2026, 9, 15), date(2026, 9, 26), 0, TEM_3)


# ------------------------------------------------------------------------- TCEA
def test_tcea_iguala_el_valor_presente_de_las_cuotas():
    """VP de las cuotas a la TCEA = monto, con plazos de gracia + 30 días por mes (Anexo A)."""
    r = engine.compra_en_cuotas(D("1000"), date(2026, 9, 15), date(2026, 9, 26), 3, TEM_3)
    tcea = r.tcea_pct / 100
    vp = sum(f.cuota / (1 + tcea) ** (D(r.dias_gracia + 30 * f.numero) / 360) for f in r.filas)
    assert abs(vp - D("1000")) < D("0.01")


def test_tcea_igual_a_la_tea_sin_gracia():
    """Con meses de 30 días, sin gracia ni costos extra, la TCEA coincide con la TEA (salvo céntimos)."""
    r = engine.compra_en_cuotas(D("1000"), date(2026, 9, 26), date(2026, 9, 26), 3, TEM_3)
    tea_pct = engine.tea(TEM_3) * 100
    assert abs(r.tcea_pct - tea_pct) < D("0.01")


def test_tcea_no_depende_de_los_dias_del_calendario():
    """Febrero (28 días) y octubre (31) dan la misma TCEA: cada mes cuenta 30 días."""
    feb = engine.compra_en_cuotas(D("1000"), date(2027, 1, 26), date(2027, 1, 26), 3, TEM_3)
    oct_ = engine.compra_en_cuotas(D("1000"), date(2026, 9, 26), date(2026, 9, 26), 3, TEM_3)
    assert feb.tcea_pct == oct_.tcea_pct


def test_tcea_fin_de_mes_es_la_tasa_efectiva_del_plazo_anualizada():
    r = engine.compra_fin_de_mes(D("100"), date(2026, 11, 15), date(2026, 12, 5), engine.Tasa("EFECTIVA", D("3.5"), 30))
    tcea = engine.tcea(D("100"), [(r.dias, r.total)])
    # 100 * (1 + TCEA)^(20/360) = total
    assert abs(D("100") * (1 + tcea) ** (D(20) / 360) - r.total) < D("0.0001")


def test_tcea_cero_si_no_hay_interes():
    assert engine.tcea(D("100"), [(30, D("100"))]) == 0
