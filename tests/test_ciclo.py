"""
Fechas de corte y de pago (enunciado, puntos 4 y 5).

Una compra ANTES de la fecha y hora de corte pertenece a ese corte; si no, al del mes siguiente.
Días = fecha final - fecha inicial.
"""
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from app.modules.finance import engine

LIMA = ZoneInfo("America/Lima")
CORTE_18H = time(18, 0)


def lima(*args) -> datetime:
    return datetime(*args, tzinfo=LIMA)


def test_ejemplo_del_enunciado():
    """Compra el 15/09, corte el 20, pago el 26 -> paga el 26/09 con 11 días de gracia."""
    ciclo = engine.ciclo_de_compra(lima(2026, 9, 15, 10, 0), 20, CORTE_18H, 26)
    assert ciclo.fecha_corte == date(2026, 9, 20)
    assert ciclo.fecha_pago == date(2026, 9, 26)
    assert engine.dias_entre(date(2026, 9, 15), ciclo.fecha_pago) == 11


def test_compra_despues_del_corte_pasa_al_mes_siguiente():
    ciclo = engine.ciclo_de_compra(lima(2026, 9, 21, 9, 0), 20, CORTE_18H, 26)
    assert ciclo.fecha_corte == date(2026, 10, 20)
    assert ciclo.fecha_pago == date(2026, 10, 26)


@pytest.mark.parametrize("hora, corte_esperado", [
    (time(17, 59), date(2026, 9, 20)),   # un minuto antes: entra en este corte
    (time(18, 0), date(2026, 10, 20)),   # exactamente a la hora de corte: siguiente ciclo
    (time(18, 1), date(2026, 10, 20)),
])
def test_hora_de_corte(hora, corte_esperado):
    compra = datetime.combine(date(2026, 9, 20), hora, tzinfo=LIMA)
    assert engine.ciclo_de_compra(compra, 20, CORTE_18H, 26).fecha_corte == corte_esperado


def test_dia_de_pago_anterior_al_corte_cae_el_mes_siguiente():
    """Corte el 25, pago el 5: el pago es el 5 del mes siguiente al corte."""
    ciclo = engine.ciclo_de_compra(lima(2026, 11, 10, 12, 0), 25, CORTE_18H, 5)
    assert ciclo.fecha_corte == date(2026, 11, 25)
    assert ciclo.fecha_pago == date(2026, 12, 5)


def test_cambio_de_anio():
    ciclo = engine.ciclo_de_compra(lima(2026, 12, 28, 12, 0), 25, CORTE_18H, 5)
    assert ciclo.fecha_corte == date(2027, 1, 25)
    assert ciclo.fecha_pago == date(2027, 2, 5)


def test_compra_en_hora_utc_se_evalua_en_hora_de_lima():
    """23:30 UTC del 20/09 = 18:30 en Lima -> ya pasó el corte de las 18:00."""
    compra_utc = datetime(2026, 9, 20, 23, 30, tzinfo=ZoneInfo("UTC"))
    ciclo = engine.ciclo_de_compra(compra_utc.astimezone(LIMA), 20, CORTE_18H, 26)
    assert ciclo.fecha_corte == date(2026, 10, 20)


@pytest.mark.parametrize("inicio, meses, esperado", [
    (date(2026, 9, 26), 1, date(2026, 10, 26)),
    (date(2026, 9, 26), 3, date(2026, 12, 26)),
    (date(2026, 11, 5), 2, date(2027, 1, 5)),
    (date(2026, 1, 31), 1, date(2026, 2, 28)),  # mes corto: último día del mes
])
def test_sumar_meses(inicio, meses, esperado):
    assert engine.sumar_meses(inicio, meses) == esperado


def test_conteo_de_dias():
    assert engine.dias_entre(date(2026, 9, 15), date(2026, 9, 26)) == 11
    assert engine.dias_entre(date(2026, 11, 25), date(2026, 12, 5)) == 10
    assert engine.dias_entre(date(2026, 12, 5), date(2026, 12, 5)) == 0
