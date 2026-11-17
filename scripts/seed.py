"""
Datos iniciales: admin del sistema, topes de tasa y una tienda de demostración
(los mismos datos de las pantallas de Figma). Se puede ejecutar varias veces.

    python -m scripts.seed            # solo admin + topes
    python -m scripts.seed --demo     # además, Bodega Don Lucho con productos y una clienta
"""
import sys
from datetime import date, time
from decimal import Decimal as D

from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import Cliente, CondicionCredito, Producto, Tienda, TopeTasa, Usuario

# Valores de EJEMPLO. Actualízalos con la circular vigente del BCRP antes de la entrega.
TOPES = [
    ("COMPENSATORIA", D("114.1300000"), date(2026, 1, 1), "Ejemplo del informe; verificar circular BCRP vigente"),
    ("MORATORIA", D("17.1200000"), date(2026, 1, 1), "Ejemplo del informe; verificar circular BCRP vigente"),
]

PRODUCTOS = [
    # codigo, nombre, marca, unidad, contado, credito, fin_mes, cuotas, max_meses
    ("SKU-00104", "Pollo fresco eviscerado", "San Fernando", "Kilo (kg)", "9.80", "10.50", True, False, None),
    ("SKU-00218", "Pan francés artesanal", "Panadería Don Lucho", "Unidad", "0.40", "0.45", True, False, None),
    ("SKU-00340", "Gaseosa Inca Kola 1.5 L", "Inca Kola", "Botella 1.5 L", "7.50", "8.20", True, False, None),
    ("SKU-00412", "Arroz Costeño Extra 5 kg", "Costeño", "Bolsa 5 kg", "22.00", "24.50", True, True, 3),
    ("SKU-00500", "Leche Gloria Azul 400g", "Gloria", "Unidad", "4.20", "4.60", True, False, None),
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
    for tipo, tea, desde, fuente in TOPES:
        if not db.scalar(select(TopeTasa).where(TopeTasa.tipo == tipo, TopeTasa.vigente_desde == desde)):
            db.add(TopeTasa(tipo=tipo, tea_maxima=tea, vigente_desde=desde, fuente=fuente))


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

    for cod, nom, marca, und, contado, credito, fm, cu, mm in PRODUCTOS:
        if not db.scalar(select(Producto).where(Producto.tienda_id == tienda.id, Producto.codigo == cod)):
            db.add(Producto(tienda_id=tienda.id, codigo=cod, nombre=nom, marca=marca, unidad_medida=und,
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


def main() -> None:
    with SessionLocal() as db:
        seed_base(db)
        if "--demo" in sys.argv:
            seed_demo(db)
        db.commit()
    print("Semilla aplicada." + (" Incluye datos de demostración." if "--demo" in sys.argv else ""))


if __name__ == "__main__":
    main()
