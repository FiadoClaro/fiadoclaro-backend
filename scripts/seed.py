"""
Datos iniciales: admin del sistema, topes de tasa y una tienda de demostración
(los mismos datos de las pantallas de Figma). Se puede ejecutar varias veces.

    python -m scripts.seed            # solo admin + topes
    python -m scripts.seed --demo     # además, Bodega Don Lucho con productos, la clienta Rosa
                                      # y su historial de compras, un pago y un listado pendiente
"""
import sys
from datetime import date, datetime, time, timedelta
from decimal import Decimal as D

from sqlalchemy import select

from app.core import clock
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.deps import Actor
from app.core.security import hash_password
from app.models import Cliente, CondicionCredito, Producto, Tienda, TopeTasa, Usuario
from app.modules.finance import engine
from app.modules.payments import service as payments
from app.modules.payments.schemas import PagoIn
from app.modules.purchases import service as purchases
from app.modules.purchases.models import Compra
from app.modules.purchases.schemas import CompraIn, ItemIn
from app.modules.statements import service as statements
from app.modules.statements.models import EstadoCuenta

# Valores de EJEMPLO. Actualízalos con la circular vigente del BCRP antes de la entrega.
# Topes del BCRP para operaciones entre personas ajenas al sistema financiero (art. 1243 del Código Civil,
# Circular N° 0008-2021-BCRP). TEA en %. La moratoria es el 15 % de la compensatoria.
# Al publicarse la siguiente actualización (mayo y noviembre), agregar las filas nuevas aquí o con POST /finance/topes.
FUENTE_NOV_2026 = "Circular N° 0008-2021-BCRP, tasas vigentes desde el 01/11/2026"
FUENTE_MAY_2026 = "Circular N° 0008-2021-BCRP, tasas vigentes de mayo a octubre de 2026"
TOPES = [
    # tipo, moneda, TEA máxima %, vigente desde, fuente
    ("COMPENSATORIA", "PEN", D("114.6800000"), date(2026, 11, 1), FUENTE_NOV_2026),
    ("MORATORIA", "PEN", D("17.2000000"), date(2026, 11, 1), FUENTE_NOV_2026),
    ("COMPENSATORIA", "USD", D("103.1400000"), date(2026, 11, 1), FUENTE_NOV_2026),
    ("MORATORIA", "USD", D("15.4700000"), date(2026, 11, 1), FUENTE_NOV_2026),
    # Semestre anterior (soles): necesario para validar compras con fecha anterior al 01/11/2026
    ("COMPENSATORIA", "PEN", D("114.1300000"), date(2026, 5, 1), FUENTE_MAY_2026),
    ("MORATORIA", "PEN", D("17.1200000"), date(2026, 5, 1), FUENTE_MAY_2026),
]

PRODUCTOS = [
    # nombre, marca, unidad, contado, credito, fin_mes, cuotas, max_meses
    ("Pollo fresco eviscerado", "San Fernando", "Kilo (kg)", "9.80", "10.50", True, False, None),
    ("Pan francés artesanal", "Panadería Don Lucho", "Unidad", "0.40", "0.45", True, False, None),
    ("Gaseosa Inca Kola 1.5 L", "Inca Kola", "Botella 1.5 L", "7.50", "8.20", True, False, None),
    ("Arroz Costeño Extra 5 kg", "Costeño", "Bolsa 5 kg", "22.00", "24.50", True, True, 3),
    ("Leche Gloria Azul 400g", "Gloria", "Unidad", "4.20", "4.60", True, False, None),
]


def get_or_create_user(db, username, password, rol, nombre, tienda_id=None) -> Usuario:
    u = db.scalar(select(Usuario).where(Usuario.username == username))
    if not u:
        u = Usuario(username=username, password_hash=hash_password(password), rol=rol,
                    nombre=nombre, tienda_id=tienda_id, activo=True)
        db.add(u)
        db.flush()
    return u


def seed_base(db) -> None:
    get_or_create_user(db, settings.ADMIN_USERNAME, settings.ADMIN_PASSWORD, "ADMIN_SISTEMA", "Administrador del Sistema")
    for tipo, moneda, tea, desde, fuente in TOPES:
        if not db.scalar(select(TopeTasa).where(TopeTasa.tipo == tipo, TopeTasa.moneda == moneda,
                                                TopeTasa.vigente_desde == desde)):
            db.add(TopeTasa(tipo=tipo, moneda=moneda, tea_maxima=tea, vigente_desde=desde, fuente=fuente))


def seed_demo(db) -> None:
    tienda = db.scalar(select(Tienda).where(Tienda.ruc == "20554892101"))
    if not tienda:
        tienda = Tienda(ruc="20554892101", razon_social="Comercializadora Morales e Hijos S.A.C.",
                        nombre_comercial="Bodega Don Lucho", giro="Bodega", direccion="Av. Brasil 1234",
                        telefono="(01) 263-8890",
                        correo="contacto@bodegadonlucho.pe", estado="ACTIVA")
        db.add(tienda)
        db.flush()
    admin = get_or_create_user(db, "dlucho", "Lucho2026*", "ADMIN_TIENDA", "Luis Morales Vega", tienda.id)
    admin.telefono, admin.correo = admin.telefono or "984512870", admin.correo or "lucho.morales@gmail.com"

    for nom, marca, und, contado, credito, fm, cu, mm in PRODUCTOS:
        if not db.scalar(select(Producto).where(Producto.tienda_id == tienda.id, Producto.nombre == nom)):
            db.add(Producto(tienda_id=tienda.id, nombre=nom, marca=marca, unidad_medida=und,
                            moneda="PEN", precio_contado=D(contado), precio_lista_credito=D(credito),
                            permite_fin_mes=fm, permite_cuotas=cu, max_meses=mm, estado="ACTIVO"))

    if not db.scalar(select(Cliente).where(Cliente.tienda_id == tienda.id, Cliente.dni == "08765432")):
        u = get_or_create_user(db, f"08765432@{tienda.dominio_portal}", "Rosa2024*Lucho", "CLIENTE",
                               "Rosa Flores Benites", tienda.id)
        u.telefono, u.correo = "987654321", "rosa.flores@gmail.com"
        cliente = Cliente(tienda_id=tienda.id, usuario_id=u.id, dni="08765432", nombres="Rosa",
                          apellidos="Flores Benites", telefono="987654321", correo="rosa.flores@gmail.com",
                          estado="ACTIVO")
        cliente.condicion = CondicionCredito(
            moneda="PEN", tipo_tasa="EFECTIVA", tasa=D("3.5"), periodo_tasa_dias=30, capitalizacion_dias=None,
            tipo_tasa_mora="EFECTIVA", tasa_mora=D("1.3"), periodo_tasa_mora_dias=30,
            capitalizacion_mora_dias=None, limite_credito=D("800.00"), max_meses=3,
            dia_corte=25, hora_corte=time(18, 0), dia_pago=5,
        )
        db.add(cliente)


def _ultimo_corte(ahora: datetime, dia_corte: int, hora_corte: time) -> date:
    """Fecha del último corte que ya pasó (día y hora de corte <= ahora)."""
    corte = date(ahora.year, ahora.month, dia_corte)
    if datetime.combine(corte, hora_corte, tzinfo=ahora.tzinfo) > ahora:
        corte = engine.sumar_meses(corte, -1)
    return corte


def seed_compras_demo(db) -> None:
    """
    Historial de Rosa para la demo, con fechas relativas a HOY para que siempre se vean todos los casos:

      * Ciclo anterior (corte C-1): compras a fin de mes + una compra en 3 cuotas -> listado PAGADO a tiempo.
      * Último corte (C0): compras a fin de mes + la 1.a cuota -> listado PENDIENTE
        (vencido y con mora si hoy ya pasó su fecha de pago).
      * Ciclo abierto (después de C0): compras que todavía no entran a ningún listado.

    Se registra todo con los servicios reales (cálculos, bitácora y listados automáticos), moviendo el
    reloj del sistema a cada fecha, como si la tienda hubiera anotado las compras día a día.
    """
    tienda = db.scalar(select(Tienda).where(Tienda.ruc == "20554892101"))
    rosa = db.scalar(select(Cliente).where(Cliente.tienda_id == tienda.id, Cliente.dni == "08765432"))
    if db.scalar(select(Compra.id).where(Compra.cliente_id == rosa.id)):
        return  # ya tiene historial
    admin = Actor(db.scalar(select(Usuario).where(Usuario.username == "dlucho")), "seed")
    p = {pr.nombre: pr.id for pr in db.scalars(select(Producto).where(Producto.tienda_id == tienda.id))}
    cond = rosa.condicion
    hoy_real = clock.ahora()
    c0 = _ultimo_corte(hoy_real, cond.dia_corte, cond.hora_corte)
    c_1 = engine.sumar_meses(c0, -1)

    def en(dia: date, hora: int = 10) -> None:
        clock.fijar_ahora(datetime.combine(dia, time(hora, 0), tzinfo=hoy_real.tzinfo))

    def comprar(dia: date, items: list[tuple[str, str]], modalidad: str = "FIN_MES", cuotas: int = 1) -> None:
        en(dia)
        purchases.registrar_compra(db, admin, CompraIn(
            cliente_id=rosa.id, modalidad=modalidad, num_cuotas=cuotas,
            items=[ItemIn(producto_id=p[nombre], cantidad=D(cant)) for nombre, cant in items]))

    try:
        # ---- Ciclo anterior: se paga a tiempo
        comprar(c_1 - timedelta(days=22), [("Pollo fresco eviscerado", "2"), ("Pan francés artesanal", "10")])
        comprar(c_1 - timedelta(days=15), [("Arroz Costeño Extra 5 kg", "3")], modalidad="CUOTAS", cuotas=3)
        comprar(c_1 - timedelta(days=7), [("Gaseosa Inca Kola 1.5 L", "2"), ("Leche Gloria Azul 400g", "3")])
        # Primera compra del ciclo siguiente (antes de que Rosa pague el ciclo anterior)
        comprar(c0 - timedelta(days=23), [("Pollo fresco eviscerado", "1"), ("Leche Gloria Azul 400g", "6")])
        # Rosa paga el ciclo anterior el día pactado (sin mora)
        en(engine.fecha_pago_de_corte(c_1, cond.dia_pago), 11)
        statements.asegurar_listados(db, tienda.id, rosa.id)
        ec = db.scalar(select(EstadoCuenta).where(EstadoCuenta.cliente_id == rosa.id, EstadoCuenta.fecha_corte == c_1))
        payments.registrar_pago(db, admin, PagoIn(estado_cuenta_id=ec.id, monto=ec.total_a_pagar))

        # ---- Último corte: queda pendiente (con mora si ya venció)
        comprar(c0 - timedelta(days=10), [("Gaseosa Inca Kola 1.5 L", "2"), ("Pan francés artesanal", "10")])
        comprar(c0 - timedelta(days=3), [("Arroz Costeño Extra 5 kg", "1")])

        # ---- Ciclo abierto: compras después del corte, hasta hoy
        abiertos = [(c0 + timedelta(days=3), [("Pollo fresco eviscerado", "2")]),
                    (c0 + timedelta(days=12), [("Leche Gloria Azul 400g", "4"), ("Gaseosa Inca Kola 1.5 L", "1")])]
        for dia, items in abiertos:
            if datetime.combine(dia, time(10, 0), tzinfo=hoy_real.tzinfo) < hoy_real:
                comprar(dia, items)
    finally:
        clock.fijar_ahora(None)
    statements.asegurar_listados(db, tienda.id, rosa.id)  # genera el listado del último corte a la fecha real


def main() -> None:
    demo = "--demo" in sys.argv
    with SessionLocal() as db:
        seed_base(db)
        if demo:
            seed_demo(db)
        db.commit()
        if demo:
            seed_compras_demo(db)
    print("Semilla aplicada." + (" Incluye datos de demostración y compras de Rosa." if demo else ""))


if __name__ == "__main__":
    main()
