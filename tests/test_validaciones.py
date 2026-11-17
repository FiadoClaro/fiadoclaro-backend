"""Mensajes de error en español, formato del usuario y dominio del portal (sin base de datos)."""
import pytest
from pydantic import ValidationError

from app.core.errors import mensaje_validacion
from app.modules.customers.schemas import ClienteCreate
from app.modules.iam.schemas import AccesoCliente, CambioPassword, Credenciales
from app.modules.stores.models import Tienda


def errores(modelo, **datos) -> dict[str, str]:
    """Valida y devuelve {campo: mensaje en español}."""
    with pytest.raises(ValidationError) as e:
        modelo(**datos)
    return {m["campo"]: m["mensaje"] for m in (mensaje_validacion(x) for x in e.value.errors())}


# ---------------------------------------------------------------- usuario
@pytest.mark.parametrize("usuario, esperado", [
    ("08765432@bodegadonlucho.com", "08765432@bodegadonlucho.com"),
    ("  DLucho_Admin ", "dlucho_admin"),          # se normaliza: sin espacios y en minúsculas
    ("rosa.flores", "rosa.flores"),
])
def test_usuarios_validos(usuario, esperado):
    assert Credenciales(username=usuario, password="Clave1234").username == esperado


def test_usuario_con_arroba_debe_parecer_correo():
    assert errores(Credenciales, username="0876@", password="Clave1234") == {
        "username": "El usuario con @ debe tener forma de correo, por ejemplo 08765432@bodegadonlucho.com"}


def test_usuario_con_caracteres_no_permitidos():
    assert errores(Credenciales, username="rosa flores!", password="Clave1234") == {
        "username": "El usuario solo puede tener letras, números, punto, guion, guion bajo y @"}


def test_usuario_del_portal_es_opcional():
    assert AccesoCliente(password="Clave1234").username is None


# ------------------------------------------------------------- contraseñas
def test_password_corto():
    assert errores(Credenciales, username="dlucho", password="123") == {
        "password": "La contraseña debe tener al menos 8 caracteres"}


def test_cambio_password_confirmacion_distinta():
    msg = errores(CambioPassword, password_actual="Vieja1234", password_nueva="Nueva1234", confirmacion="Otra1234")
    assert msg == {"solicitud": "La confirmación no coincide con la nueva contraseña"}


def test_cambio_password_igual_a_la_actual():
    msg = errores(CambioPassword, password_actual="Igual1234", password_nueva="Igual1234")
    assert msg == {"solicitud": "La nueva contraseña debe ser distinta a la actual"}


# ------------------------------------------------------ mensajes de validación
def test_mensajes_de_alta_de_cliente():
    msg = errores(ClienteCreate, nombres="R", apellidos="Flores", dni="123", correo="no-es-correo",
                  condicion={"tasa": {"tipo": "EFECTIVA", "valor": "-1", "periodo_dias": 30},
                             "tasa_mora": {"tipo": "MIXTA", "valor": "2", "periodo_dias": 30},
                             "limite_credito": "0", "max_meses": 40, "dia_corte": 25, "dia_pago": 5},
                  acceso={"password": "Clave1234"})
    assert msg["nombres"] == "Los nombres deben tener al menos 2 caracteres"
    assert msg["dni"] == "El DNI debe tener exactamente 8 dígitos"
    assert msg["correo"] == "El correo no es válido"
    assert msg["condicion.tasa.valor"] == "La tasa debe ser mayor o igual que 0"
    assert msg["condicion.tasa_mora.tipo"].startswith("El campo 'tipo' debe ser uno de")
    assert msg["condicion.limite_credito"] == "El límite de crédito debe ser mayor que 0"
    assert msg["condicion.max_meses"] == "El máximo de meses debe ser menor o igual que 36"


def test_campo_obligatorio():
    assert errores(Credenciales, username="dlucho") == {"password": "La contraseña es obligatoria"}


def test_validador_propio_sin_prefijo_en_ingles():
    msg = errores(ClienteCreate, nombres="Rosa", apellidos="Flores", dni="12345678",
                  condicion={"tasa": {"tipo": "EFECTIVA", "valor": "3", "periodo_dias": 30},
                             "tasa_mora": {"tipo": "EFECTIVA", "valor": "2", "periodo_dias": 30},
                             "limite_credito": "100", "max_meses": 3, "dia_corte": 5, "dia_pago": 5},
                  acceso={"password": "Clave1234"})
    assert msg == {"condicion": "El día de pago debe ser distinto al día de corte"}


# ------------------------------------------------------------ dominio del portal
@pytest.mark.parametrize("nombre, dominio", [
    ("Bodega Don Lucho", "bodegadonlucho.com"),
    ("Frutería La Chacarera", "fruterialachacarera.com"),   # sin tildes
    ("Peluquería & Spa 'Karina'", "peluqueriaspakarina.com"),  # sin símbolos
])
def test_dominio_portal(nombre, dominio):
    assert Tienda(id=1, nombre_comercial=nombre).dominio_portal == dominio
