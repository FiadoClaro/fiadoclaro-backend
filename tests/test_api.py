"""
Pruebas del API por HTTP: perfil, mi tienda, listas paginadas, usuario del portal, simulación que
excede el crédito y forma de los errores. Todo corre dentro de una transacción que se revierte.
"""
from datetime import time
from decimal import Decimal as D

import pytest

from app.core import clock
from tests.conftest import lima, login

pytestmark = pytest.mark.integracion

API = "/api/v1"


@pytest.fixture
def h_admin(api, con_claves):
    return login(api, *con_claves["admin"])


@pytest.fixture
def h_cliente(api, con_claves):
    return login(api, *con_claves["cliente"])


@pytest.fixture
def h_sistema(api, con_claves):
    return login(api, *con_claves["sistema"])


# ------------------------------------------------------------------ errores
def test_error_de_validacion_en_espanol(api, h_admin):
    r = api.post(f"{API}/customers", headers=h_admin, json={"nombres": "Rosa", "dni": "12"})
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == "validacion"
    campos = {e["campo"]: e["mensaje"] for e in body["errores"]}
    assert campos["dni"] == "El DNI debe tener exactamente 8 dígitos"
    assert campos["apellidos"] == "Los apellidos son obligatorios"
    assert body["detail"].startswith("Revisa")


def test_sin_sesion(api):
    r = api.get(f"{API}/iam/me")
    assert r.status_code == 401 and r.json()["code"] == "no_autenticado"


def test_login_contrasena_incorrecta(api, con_claves):
    r = api.post(f"{API}/iam/login", data={"username": "admin.test", "password": "mala"})
    assert r.status_code == 401
    assert r.json() == {"detail": "La contraseña es incorrecta", "code": "password_incorrecto"}


def test_login_usuario_que_no_existe(api, con_claves):
    r = api.post(f"{API}/iam/login", data={"username": "No.Existe", "password": "loquesea"})
    assert r.status_code == 404
    assert r.json() == {"detail": "El usuario 'no.existe' no existe", "code": "usuario_no_existe"}


def test_rol_sin_permiso(api, h_cliente):
    r = api.get(f"{API}/customers", headers=h_cliente)
    assert r.status_code == 403 and r.json()["code"] == "prohibido"


def test_ruta_inexistente(api):
    r = api.get(f"{API}/no-existe")
    assert r.status_code == 404 and r.json()["detail"] == "Recurso no encontrado"


# ------------------------------------------------------------------- perfil
def test_ver_y_editar_mi_perfil(api, h_admin):
    r = api.patch(f"{API}/iam/me", headers=h_admin,
                  json={"nombre": "Luis Morales", "telefono": "984512870", "correo": "lucho@gmail.com"})
    assert r.status_code == 200, r.text
    me = api.get(f"{API}/iam/me", headers=h_admin).json()
    assert (me["nombre"], me["telefono"], me["correo"]) == ("Luis Morales", "984512870", "lucho@gmail.com")


def test_perfil_sin_cambios(api, h_admin):
    r = api.patch(f"{API}/iam/me", headers=h_admin, json={})
    assert r.status_code == 422 and r.json()["code"] == "sin_cambios"


def test_vecino_no_cambia_su_nombre(api, h_cliente):
    r = api.patch(f"{API}/iam/me", headers=h_cliente, json={"nombre": "Otra Persona"})
    assert r.status_code == 422 and r.json()["code"] == "campo_no_editable"


def test_vecino_cambia_su_contacto_y_se_refleja_en_su_ficha(api, h_cliente, h_admin, cliente):
    r = api.patch(f"{API}/iam/me", headers=h_cliente, json={"telefono": "999888777"})
    assert r.status_code == 200
    ficha = api.get(f"{API}/customers/{cliente.id}", headers=h_admin).json()
    assert ficha["telefono"] == "999888777"


def test_cambiar_password(api, con_claves, h_admin):
    r = api.post(f"{API}/iam/cambiar-password", headers=h_admin,
                 json={"password_actual": "Admin.Test1", "password_nueva": "NuevaClave9"})
    assert r.status_code == 204
    login(api, "admin.test", "NuevaClave9")  # entra con la nueva


def test_cambiar_password_con_actual_incorrecta(api, h_admin):
    r = api.post(f"{API}/iam/cambiar-password", headers=h_admin,
                 json={"password_actual": "equivocada", "password_nueva": "NuevaClave9"})
    assert r.status_code == 422 and r.json()["code"] == "password_incorrecto"


# ---------------------------------------------------------------- mi tienda
def test_mi_tienda_para_el_admin(api, h_admin, tienda):
    t = api.get(f"{API}/iam/me/tienda", headers=h_admin).json()
    assert t["ruc"] == tienda.ruc
    assert t["dominio_portal"] == "bodegatest.com"
    assert t["administrador"]["username"] == "admin.test"
    assert "distrito" not in t


def test_mi_tienda_para_el_vecino_sin_datos_del_admin(api, h_cliente, tienda):
    t = api.get(f"{API}/iam/me/tienda", headers=h_cliente).json()
    assert t["nombre_comercial"] == tienda.nombre_comercial
    assert t["administrador"] is None


def test_admin_del_sistema_no_tiene_tienda(api, h_sistema):
    r = api.get(f"{API}/iam/me/tienda", headers=h_sistema)
    assert r.status_code == 422 and r.json()["code"] == "sin_tienda"


def test_editar_mi_tienda(api, h_admin):
    r = api.patch(f"{API}/iam/me/tienda", headers=h_admin,
                  json={"nombre_comercial": "Bodega Test Renovada", "telefono": "012345678"})
    assert r.status_code == 200
    assert r.json()["nombre_comercial"] == "Bodega Test Renovada"
    assert r.json()["dominio_portal"] == "bodegatestrenovada.com"


def test_el_ruc_no_se_edita(api, h_admin, tienda):
    api.patch(f"{API}/iam/me/tienda", headers=h_admin, json={"ruc": "20111111111", "giro": "Frutería"})
    t = api.get(f"{API}/iam/me/tienda", headers=h_admin).json()
    assert t["ruc"] == tienda.ruc and t["giro"] == "Frutería"


def test_el_vecino_no_edita_la_tienda(api, h_cliente):
    r = api.patch(f"{API}/iam/me/tienda", headers=h_cliente, json={"giro": "Spa"})
    assert r.status_code == 403


def test_admin_del_sistema_edita_tienda_y_contacto_del_admin(api, h_sistema, tienda):
    r = api.patch(f"{API}/stores/{tienda.id}", headers=h_sistema,
                  json={"giro": "Panadería", "administrador": {"telefono": "911222333"}})
    assert r.status_code == 200, r.text
    assert r.json()["giro"] == "Panadería"
    assert r.json()["administrador"]["telefono"] == "911222333"


# ------------------------------------------------------------ listas paginadas
def test_lista_de_tiendas_con_total_y_conteos(api, h_sistema, tienda):
    r = api.get(f"{API}/stores", headers=h_sistema, params={"limit": 1, "q": "Bodega Test"})
    body = r.json()
    assert set(body) == {"items", "total", "limit", "offset", "conteos"}
    assert body["total"] >= 1 and len(body["items"]) == 1
    assert body["conteos"]["estado"]["ACTIVA"] >= 1
    assert body["conteos"]["giro"]["Bodega"] >= 1


def test_lista_de_clientes_con_conteos_por_estado(api, h_admin, cliente):
    body = api.get(f"{API}/customers", headers=h_admin).json()
    assert body["total"] == 1
    assert body["conteos"]["estado"] == {"TODOS": 1, "ACTIVO": 1, "BAJA": 0, "AL_DIA": 1, "EN_MORA": 0}
    body = api.get(f"{API}/customers", headers=h_admin, params={"estado": "EN_MORA"}).json()
    assert body["total"] == 0 and body["items"] == []
    assert body["conteos"]["estado"]["TODOS"] == 1  # la faceta no depende del filtro elegido


def test_lista_de_productos_paginada(api, h_admin, productos):
    p1 = api.get(f"{API}/products", headers=h_admin, params={"limit": 2, "offset": 0}).json()
    p2 = api.get(f"{API}/products", headers=h_admin, params={"limit": 2, "offset": 2}).json()
    assert p1["total"] == p2["total"] == 3
    assert len(p1["items"]) == 2 and len(p2["items"]) == 1
    assert p1["conteos"]["estado"] == {"TODOS": 3, "ACTIVO": 3}


# ------------------------------------------------------------- usuario del portal
def nuevo_cliente(dni: str, username: str | None = None) -> dict:
    acceso = {"password": "Clave1234"} | ({"username": username} if username else {})
    return {
        "nombres": "Elena", "apellidos": "Paucar", "dni": dni, "acceso": acceso,
        "condicion": {"tasa": {"tipo": "EFECTIVA", "valor": "3.5", "periodo_dias": 30},
                      "tasa_mora": {"tipo": "EFECTIVA", "valor": "1.3", "periodo_dias": 30},
                      "limite_credito": "500", "max_meses": 3, "dia_corte": 25,
                      "hora_corte": str(time(18, 0)), "dia_pago": 5},
    }


def test_usuario_del_portal_se_arma_con_dni_y_dominio(api, h_admin):
    r = api.post(f"{API}/customers", headers=h_admin, json=nuevo_cliente("45892134"))
    assert r.status_code == 201, r.text
    assert r.json()["usuario"] == "45892134@bodegatest.com"
    login(api, "45892134@bodegatest.com", "Clave1234")


def test_usuario_del_portal_debe_empezar_con_el_dni(api, h_admin):
    r = api.post(f"{API}/customers", headers=h_admin, json=nuevo_cliente("45892134", "elena@bodegatest.com"))
    assert r.status_code == 422
    assert r.json()["code"] == "usuario_portal_invalido"
    assert "45892134@bodegatest.com" in r.json()["detail"]


def test_usuario_repetido(api, h_admin):
    api.post(f"{API}/customers", headers=h_admin, json=nuevo_cliente("45892134"))
    r = api.post(f"{API}/customers", headers=h_admin,
                 json=nuevo_cliente("45892135", "45892135@bodegatest.com") | {"dni": "45892135"})
    assert r.status_code == 201
    r = api.post(f"{API}/customers", headers=h_admin, json=nuevo_cliente("45892134"))
    assert r.status_code == 409


# ------------------------------------------------------ compra que excede el crédito
def test_simular_compra_que_excede_el_credito(api, h_admin, cliente, productos):
    clock.fijar_ahora(lima(2026, 11, 15, 10, 0))
    compra = {"cliente_id": cliente.id, "modalidad": "FIN_MES",
              "items": [{"producto_id": productos["tv"].id, "cantidad": "2"}]}  # 1500 > 800
    sim = api.post(f"{API}/purchases/simular", headers=h_admin, json=compra)
    assert sim.status_code == 200, sim.text
    s = sim.json()
    assert s["excede_credito"] is True
    assert D(s["deficit"]) == D("700.00")
    assert "excede el crédito disponible" in s["mensaje"]

    reg = api.post(f"{API}/purchases", headers=h_admin, json=compra)
    assert reg.status_code == 422
    assert reg.json()["code"] == "excede_credito"
    assert {k: D(v) for k, v in reg.json()["datos"].items()} == {
        "disponible": D("800.00"), "solicitado": D("1500.00"), "deficit": D("700.00")}


def test_simular_compra_dentro_del_limite(api, h_admin, cliente, productos):
    clock.fijar_ahora(lima(2026, 11, 15, 10, 0))
    s = api.post(f"{API}/purchases/simular", headers=h_admin, json={
        "cliente_id": cliente.id, "modalidad": "FIN_MES",
        "items": [{"producto_id": productos["pollo"].id, "cantidad": "1"}]}).json()
    assert s["excede_credito"] is False and D(s["deficit"]) == 0 and s["mensaje"] is None
