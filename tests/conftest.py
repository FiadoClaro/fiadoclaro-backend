"""
Fixtures de las pruebas de integración.

Cada prueba corre dentro de una transacción que se REVIERTE al terminar: aunque los servicios
hagan commit, nada queda guardado en la base. Se usa TEST_DATABASE_URL si está definida en el
entorno; si no, DATABASE_URL del .env. Si la base no responde, estas pruebas se omiten.
"""
import os
from datetime import datetime, time
from decimal import Decimal as D
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import settings
from app.core.deps import Actor
from app.models import Cliente, CondicionCredito, Producto, Tienda, TopeTasa, Usuario

LIMA = ZoneInfo("America/Lima")


def lima(*args) -> datetime:
    return datetime(*args, tzinfo=LIMA)


@pytest.fixture(scope="session")
def db_engine():
    url = os.environ.get("TEST_DATABASE_URL") or settings.DATABASE_URL
    engine = create_engine(url, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1 FROM alembic_version"))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Base de datos no disponible para pruebas de integración: {exc.__class__.__name__}")
    yield engine
    engine.dispose()


@pytest.fixture
def db(db_engine):
    conn = db_engine.connect()
    trans = conn.begin()
    session = Session(bind=conn, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        clock.fijar_ahora(None)
        session.close()
        trans.rollback()
        conn.close()


@pytest.fixture
def tienda(db) -> Tienda:
    t = Tienda(ruc="20999999991", razon_social="Bodega de Pruebas S.A.C.", nombre_comercial="Bodega Test",
               giro="Bodega", estado="ACTIVA")
    db.add(t)
    # Topes BCRP (la semilla puede no estar cargada en la base de pruebas)
    for tipo, tea in (("COMPENSATORIA", D("114.13")), ("MORATORIA", D("17.12"))):
        if not db.scalar(select(TopeTasa).where(TopeTasa.tipo == tipo)):
            db.add(TopeTasa(tipo=tipo, tea_maxima=tea, vigente_desde=datetime(2020, 1, 1).date()))
    db.flush()
    return t


@pytest.fixture
def admin(db, tienda) -> Actor:
    u = Usuario(username="admin.test", password_hash="x", rol="ADMIN_TIENDA", nombre="Admin Test",
                tienda_id=tienda.id, activo=True)
    db.add(u)
    db.flush()
    return Actor(usuario=u, ip="127.0.0.1")


@pytest.fixture
def cliente(db, tienda) -> Cliente:
    """TEM 3.5 % compensatoria, 1.3 % mensual moratoria, límite S/ 800, corte el 25 a las 18:00, pago el 5."""
    u = Usuario(username="cliente.test", password_hash="x", rol="CLIENTE", nombre="Rosa Test",
                tienda_id=tienda.id, activo=True)
    db.add(u)
    db.flush()
    c = Cliente(tienda_id=tienda.id, usuario_id=u.id, dni="11112222", nombres="Rosa", apellidos="Test",
                estado="ACTIVO")
    c.condicion = CondicionCredito(
        moneda="PEN", tipo_tasa="EFECTIVA", tasa=D("3.5"), periodo_tasa_dias=30,
        tipo_tasa_mora="EFECTIVA", tasa_mora=D("1.3"), periodo_tasa_mora_dias=30,
        limite_credito=D("800.00"), max_meses=3, dia_corte=25, hora_corte=time(18, 0), dia_pago=5,
    )
    db.add(c)
    db.flush()
    return c


@pytest.fixture
def api(db):
    """Cliente HTTP del API que usa la misma sesión de prueba (todo se revierte al final)."""
    from fastapi.testclient import TestClient

    from app.core.database import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.clear()


def login(api, username: str, password: str) -> dict[str, str]:
    """Inicia sesión y devuelve el encabezado de autorización."""
    r = api.post("/api/v1/iam/login", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def con_claves(db, admin, cliente):
    """Pone contraseñas conocidas al admin de la tienda y al vecino, y crea un admin del sistema."""
    from app.core.security import hash_password

    admin.usuario.password_hash = hash_password("Admin.Test1")
    db.get(Usuario, cliente.usuario_id).password_hash = hash_password("Vecino.Test1")
    sistema = Usuario(username="sistema.test", password_hash=hash_password("Sistema.Test1"),
                      rol="ADMIN_SISTEMA", nombre="Sistema Test", activo=True)
    db.add(sistema)
    db.flush()
    return {"admin": ("admin.test", "Admin.Test1"), "cliente": ("cliente.test", "Vecino.Test1"),
            "sistema": ("sistema.test", "Sistema.Test1")}


@pytest.fixture
def productos(db, tienda) -> dict[str, Producto]:
    datos = {
        "pollo": ("Pollo fresco", "10.50", True, False, None),
        "arroz": ("Arroz 5 kg", "24.50", True, True, 3),
        "tv": ("Televisor", "750.00", True, True, 12),
    }
    out = {}
    for clave, (nom, precio, fm, cu, mm) in datos.items():
        p = Producto(tienda_id=tienda.id, nombre=nom, unidad_medida="Unidad", moneda="PEN",
                     precio_contado=D(precio), precio_lista_credito=D(precio), permite_fin_mes=fm,
                     permite_cuotas=cu, max_meses=mm, estado="ACTIVO")
        db.add(p)
        out[clave] = p
    db.flush()
    return out
