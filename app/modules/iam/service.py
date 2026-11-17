from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import ahora
from app.core.deps import Actor
from app.core.errors import BusinessError, ConflictError
from app.core.security import create_access_token, hash_password, verify_password
from app.modules.audit.service import registrar
from app.modules.iam.models import Usuario
from app.modules.iam.schemas import PerfilUpdate
from app.modules.stores.models import Tienda


class LoginInvalido(BusinessError):
    status_code = 401

    def __init__(self, msg: str = "Usuario o contraseña incorrectos", code: str = "login_invalido"):
        super().__init__(msg, code=code)


def login(db: Session, username: str, password: str, ip: str | None) -> tuple[str, Usuario]:
    usuario = db.scalar(select(Usuario).where(Usuario.username == username.strip().lower()))
    if not usuario or not verify_password(password, usuario.password_hash):
        raise LoginInvalido()
    if not usuario.activo:
        raise LoginInvalido("Tu usuario está desactivado. Comunícate con la tienda.", "usuario_inactivo")
    if usuario.tienda_id is not None:
        tienda = db.get(Tienda, usuario.tienda_id)
        if tienda is None or tienda.estado != "ACTIVA":
            raise LoginInvalido("La tienda está dada de baja", "tienda_de_baja")
    usuario.ultimo_acceso = ahora()
    registrar(db, Actor(usuario, ip), "LOGIN", "usuario", usuario.id)
    db.commit()
    return create_access_token(usuario.id, usuario.rol, usuario.tienda_id), usuario


def crear_usuario(db: Session, username: str, password: str, rol: str, nombre: str, tienda_id: int | None,
                  telefono: str | None = None, correo: str | None = None) -> Usuario:
    """Se usa desde stores (admin de tienda) y customers (acceso del vecino al portal)."""
    if db.scalar(select(Usuario.id).where(Usuario.username == username)):
        raise ConflictError(f"El usuario '{username}' ya está en uso. Elige otro.")
    usuario = Usuario(username=username, password_hash=hash_password(password), rol=rol, nombre=nombre,
                      tienda_id=tienda_id, telefono=telefono, correo=correo, activo=True)
    db.add(usuario)
    db.flush()
    return usuario


def cambiar_password(db: Session, actor: Actor, actual: str, nueva: str) -> None:
    if not verify_password(actual, actor.usuario.password_hash):
        raise BusinessError("La contraseña actual no es correcta", code="password_incorrecto")
    actor.usuario.password_hash = hash_password(nueva)
    registrar(db, actor, "CAMBIAR_PASSWORD", "usuario", actor.id)
    db.commit()


def actualizar_perfil(db: Session, actor: Actor, data: PerfilUpdate) -> Usuario:
    """
    Cada usuario edita su propio perfil.
    El vecino (CLIENTE) solo cambia su teléfono y correo, que también se actualizan en su ficha
    de cliente; su nombre lo administra la tienda.
    """
    from app.modules.customers.models import Cliente  # evita import circular

    cambios = data.model_dump(exclude_unset=True)
    if not cambios:
        raise BusinessError("No enviaste ningún dato para actualizar", code="sin_cambios")
    usuario = actor.usuario
    if usuario.rol == "CLIENTE":
        if "nombre" in cambios:
            raise BusinessError("Tu nombre lo administra la tienda. Pídele que lo actualice.",
                                code="campo_no_editable")
        cliente = db.scalar(select(Cliente).where(Cliente.usuario_id == usuario.id))
        if cliente:
            for k, v in cambios.items():
                setattr(cliente, k, v)
    elif cambios.get("nombre") is None:
        cambios.pop("nombre", None)  # el nombre no se puede dejar vacío
    for k, v in cambios.items():
        setattr(usuario, k, v)
    registrar(db, actor, "ACTUALIZAR_PERFIL", "usuario", usuario.id, cambios)
    db.commit()
    db.refresh(usuario)
    return usuario
