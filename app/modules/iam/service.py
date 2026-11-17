from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import ahora
from app.core.deps import Actor
from app.core.errors import BusinessError, ConflictError
from app.core.security import create_access_token, hash_password, verify_password
from app.modules.audit.service import registrar
from app.modules.iam.models import Usuario
from app.modules.iam.schemas import Credenciales
from app.modules.stores.models import Tienda


class LoginInvalido(BusinessError):
    status_code = 401

    def __init__(self, msg: str = "Usuario o contraseña incorrectos"):
        super().__init__(msg, code="login_invalido")


def login(db: Session, username: str, password: str, ip: str | None) -> tuple[str, Usuario]:
    usuario = db.scalar(select(Usuario).where(Usuario.username == username))
    if not usuario or not verify_password(password, usuario.password_hash):
        raise LoginInvalido()
    if not usuario.activo:
        raise LoginInvalido("El usuario está desactivado")
    if usuario.tienda_id is not None:
        tienda = db.get(Tienda, usuario.tienda_id)
        if tienda is None or tienda.estado != "ACTIVA":
            raise LoginInvalido("La tienda está dada de baja")
    usuario.ultimo_acceso = ahora()
    registrar(db, Actor(usuario, ip), "LOGIN", "usuario", usuario.id)
    db.commit()
    return create_access_token(usuario.id, usuario.rol, usuario.tienda_id), usuario


def crear_usuario(db: Session, cred: Credenciales, rol: str, nombre: str, tienda_id: int | None) -> Usuario:
    """Se usa desde stores (admin de tienda) y customers (acceso del vecino al portal)."""
    if db.scalar(select(Usuario.id).where(Usuario.username == cred.username)):
        raise ConflictError(f"El usuario '{cred.username}' ya existe")
    usuario = Usuario(
        username=cred.username,
        password_hash=hash_password(cred.password),
        rol=rol,
        nombre=nombre,
        tienda_id=tienda_id,
        activo=True,
    )
    db.add(usuario)
    db.flush()
    return usuario


def cambiar_password(db: Session, actor: Actor, actual: str, nueva: str) -> None:
    if not verify_password(actual, actor.usuario.password_hash):
        raise BusinessError("La contraseña actual no es correcta")
    actor.usuario.password_hash = hash_password(nueva)
    registrar(db, actor, "CAMBIAR_PASSWORD", "usuario", actor.id)
    db.commit()
