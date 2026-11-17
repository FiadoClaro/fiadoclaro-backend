"""
Flujo completo con la base de datos: compra -> listado en la fecha de corte -> pago.
Verifica que los servicios usen el motor de cálculo con las reglas del enunciado.
"""
from datetime import date
from decimal import Decimal as D

import pytest

from app.core import clock
from app.core.errors import BusinessError
from app.modules.finance import engine
from app.modules.finance.engine import Tasa
from app.modules.payments import service as payments
from app.modules.payments.schemas import PagoIn
from app.modules.purchases import service as purchases
from app.modules.purchases.schemas import CompraIn, ItemIn
from app.modules.statements import service as statements
from tests.conftest import lima

pytestmark = pytest.mark.integracion

TEM_35 = Tasa("EFECTIVA", D("3.5"), 30)


def comprar(db, admin, cliente, producto, cantidad="1", modalidad="FIN_MES", n=1):
    return purchases.registrar_compra(db, admin, CompraIn(
        cliente_id=cliente.id, modalidad=modalidad, num_cuotas=n,
        items=[ItemIn(producto_id=producto.id, cantidad=D(cantidad))]))


def generar_listado(db, admin, cliente, fecha_corte=date(2026, 11, 25)):
    clock.fijar_ahora(lima(fecha_corte.year, fecha_corte.month, fecha_corte.day, 19, 0))
    gen = statements.generar(db, admin, fecha_corte, cliente.id)
    assert gen.generados, gen.omitidos
    return statements.obtener(db, admin, gen.generados[0].id)


# ----------------------------------------------------------------------- compras
def test_compra_fin_de_mes_calcula_interes_hasta_la_fecha_de_pago(db, admin, cliente, productos):
    clock.fijar_ahora(lima(2026, 11, 15, 10, 0))
    c = comprar(db, admin, cliente, productos["pollo"], "2")
    assert (c.fecha_corte, c.fecha_pago) == (date(2026, 11, 25), date(2026, 12, 5))
    assert c.dias_gracia == 20
    assert c.monto_total == D("21.00")
    assert c.interes_total == engine.compra_fin_de_mes(D("21.00"), date(2026, 11, 15), date(2026, 12, 5), TEM_35).interes
    assert len(c.cronograma) == 1


def test_compra_despues_de_la_hora_de_corte_va_al_siguiente_ciclo(db, admin, cliente, productos):
    clock.fijar_ahora(lima(2026, 11, 25, 18, 30))
    c = comprar(db, admin, cliente, productos["pollo"])
    assert (c.fecha_corte, c.fecha_pago) == (date(2026, 12, 25), date(2027, 1, 5))


def test_compra_en_cuotas_usa_metodo_frances_con_gracia(db, admin, cliente, productos):
    clock.fijar_ahora(lima(2026, 11, 15, 10, 0))
    c = comprar(db, admin, cliente, productos["arroz"], modalidad="CUOTAS", n=3)
    esperado = engine.compra_en_cuotas(D("24.50"), date(2026, 11, 15), date(2026, 12, 5), 3, TEM_35)
    assert c.monto_capitalizado == esperado.monto_capitalizado
    assert c.valor_cuota == esperado.cuota
    assert [q.fecha_vencimiento for q in c.cronograma] == [date(2027, 1, 5), date(2027, 2, 5), date(2027, 3, 5)]


def test_no_permite_exceder_el_limite_de_credito(db, admin, cliente, productos):
    clock.fijar_ahora(lima(2026, 11, 15, 10, 0))
    comprar(db, admin, cliente, productos["tv"])  # 750 de 800
    with pytest.raises(BusinessError, match="excede el crédito disponible"):
        comprar(db, admin, cliente, productos["pollo"], "5")  # 52.50 > 50 disponibles


def test_no_permite_mas_cuotas_que_el_maximo(db, admin, cliente, productos):
    clock.fijar_ahora(lima(2026, 11, 15, 10, 0))
    with pytest.raises(BusinessError, match="máximo permitido"):
        comprar(db, admin, cliente, productos["tv"], modalidad="CUOTAS", n=6)  # cliente: máx. 3


def test_cambio_de_tasa_no_altera_compras_anteriores(db, admin, cliente, productos):
    clock.fijar_ahora(lima(2026, 11, 15, 10, 0))
    c = comprar(db, admin, cliente, productos["pollo"])
    cliente.condicion.tasa = D("5")
    db.flush()
    compra = purchases.obtener(db, admin, c.id)
    assert compra.tasa == D("3.5")


# ------------------------------------------------------------------ listado y pago
@pytest.fixture
def listado(db, admin, cliente, productos):
    """Dos compras a fin de mes antes del corte del 25/11 -> listado con pago el 05/12."""
    clock.fijar_ahora(lima(2026, 11, 10, 10, 0))
    comprar(db, admin, cliente, productos["pollo"], "2")
    clock.fijar_ahora(lima(2026, 11, 15, 10, 0))
    comprar(db, admin, cliente, productos["arroz"])
    return generar_listado(db, admin, cliente)


def test_listado_ordena_compras_y_suma_totales(db, listado):
    det = statements.detalle(db, listado, date(2026, 12, 5))
    assert [i.tipo for i in det.items] == ["COMPRA_FIN_MES", "COMPRA_FIN_MES"]
    assert det.items[0].fecha_compra < det.items[1].fecha_compra
    assert listado.total_a_pagar == listado.total_capital + listado.total_interes
    assert listado.total_capital == D("45.50")


def test_listado_copia_la_tasa_moratoria_al_corte(db, admin, cliente, listado):
    assert listado.tasa_mora == D("1.3")
    cliente.condicion.tasa_mora = D("2.5")  # cambio después del corte
    db.flush()
    clock.fijar_ahora(lima(2026, 12, 15, 12, 0))
    cot = payments.cotizar(db, admin, listado.id, None)
    esperado = engine.interes_moratorio(listado.total_a_pagar, date(2026, 12, 5), date(2026, 12, 15),
                                        Tasa("EFECTIVA", D("1.3"), 30))
    assert cot.interes_moratorio == esperado.interes_moratorio


def test_pago_a_tiempo_sin_mora(db, admin, listado):
    clock.fijar_ahora(lima(2026, 12, 5, 12, 0))
    cot = payments.cotizar(db, admin, listado.id, None)
    assert cot.dias_mora == 0
    assert cot.interes_moratorio == cot.interes_compensatorio_mora == 0
    assert cot.total_exigible == listado.total_a_pagar


def test_pago_con_atraso_suma_mora_y_compensatorio(db, admin, listado):
    clock.fijar_ahora(lima(2026, 12, 15, 12, 0))
    cot = payments.cotizar(db, admin, listado.id, None)
    mora = engine.interes_moratorio(listado.total_a_pagar, date(2026, 12, 5), date(2026, 12, 15),
                                    Tasa("EFECTIVA", D("1.3"), 30))
    comp = sum(engine.interes_compensatorio_mora(c.cuota, date(2026, 12, 5), date(2026, 12, 15), TEM_35)
               for c in listado.cuotas)
    assert cot.dias_mora == 10
    assert cot.interes_moratorio == mora.interes_moratorio
    assert cot.interes_compensatorio_mora == comp
    assert cot.total_exigible == listado.total_a_pagar + mora.interes_moratorio + comp


def test_pago_parcial_rechazado(db, admin, listado):
    clock.fijar_ahora(lima(2026, 12, 15, 12, 0))
    with pytest.raises(BusinessError, match="pagos parciales"):
        payments.registrar_pago(db, admin, PagoIn(estado_cuenta_id=listado.id, monto=listado.total_a_pagar))


def test_pago_con_atraso_registra_prelacion_e_items(db, admin, listado):
    clock.fijar_ahora(lima(2026, 12, 15, 12, 0))
    cot = payments.cotizar(db, admin, listado.id, None)
    pago = payments.registrar_pago(db, admin, PagoIn(estado_cuenta_id=listado.id, monto=cot.total_exigible))
    imp = {i.concepto: i.imputado for i in pago.imputacion}
    assert imp == {
        "INTERES_MORATORIO": cot.interes_moratorio,
        "INTERES_COMPENSATORIO_MORA": cot.interes_compensatorio_mora,
        "INTERES_COMPENSATORIO": listado.total_interes,
        "CAPITAL": listado.total_capital,
    }
    det = statements.detalle(db, statements.obtener(db, admin, listado.id))
    assert det.estado == "PAGADO"
    assert [i.tipo for i in det.items][-2:] == ["INTERES_MORA", "INTERES_COMP_MORA"]
    assert det.total_exigible == cot.total_exigible
    with pytest.raises(BusinessError, match="ya fue pagado"):
        payments.cotizar(db, admin, listado.id, None)


def test_pago_cancela_las_compras(db, admin, listado):
    clock.fijar_ahora(lima(2026, 12, 5, 12, 0))
    payments.registrar_pago(db, admin, PagoIn(estado_cuenta_id=listado.id, monto=listado.total_a_pagar))
    assert all(c.compra.estado == "CANCELADA" for c in listado.cuotas)
