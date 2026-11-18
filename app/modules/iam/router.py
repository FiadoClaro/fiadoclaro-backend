"""
Acceso y perfil del usuario de la sesión.

    Consultas (queries)                      Comandos (commands)
    GET  /iam/me          mi perfil          PATCH /iam/me                editar mi perfil
    GET  /iam/me/tienda   mi tienda          PATCH /iam/me/tienda         editar mi tienda (admin de tienda)
                                             POST  /iam/cambiar-password  cambiar mi contraseña
"""
from typing import Annotated

from fastapi import APIRouter, Form, Request, status

from app.core.deps import CurrentActor, DbSession, StoreAdmin
from app.modules.iam import service
from app.modules.iam.schemas import CambioPassword, PerfilUpdate, TokenOut, UsuarioOut
from app.modules.stores import service as stores
from app.modules.stores.schemas import MiTiendaUpdate, TiendaOut

router = APIRouter(prefix="/iam", tags=["IAM - Acceso y perfil"])


@router.post("/login", response_model=TokenOut, summary="Iniciar sesión (usuario y contraseña)")
def login(
    request: Request,
    db: DbSession,
    username: Annotated[str, Form(description="Usuario o correo, ej. dlucho o 08765432@bodegadonlucho.com")],
    password: Annotated[str, Form(description="Contraseña")],
):
    """Solo pide usuario y contraseña. Devuelve el token para el encabezado `Authorization: Bearer <token>`."""
    token, usuario = service.login(db, username, password, request.client.host if request.client else None)
    return TokenOut(access_token=token, usuario=UsuarioOut.model_validate(usuario))


@router.get("/me", response_model=UsuarioOut, summary="Mi perfil (usuario de la sesión)")
def me(actor: CurrentActor):
    return actor.usuario


@router.patch("/me", response_model=UsuarioOut, summary="Editar mi perfil (nombre, teléfono, correo)")
def editar_perfil(body: PerfilUpdate, db: DbSession, actor: CurrentActor):
    return service.actualizar_perfil(db, actor, body)


@router.post("/cambiar-password", status_code=status.HTTP_204_NO_CONTENT, summary="Cambiar mi contraseña")
def cambiar_password(body: CambioPassword, db: DbSession, actor: CurrentActor):
    service.cambiar_password(db, actor, body.password_actual, body.password_nueva)


@router.get("/me/tienda", response_model=TiendaOut,
            summary="Mi tienda: la que administro o, si soy vecino, donde tengo mi cuenta")
def mi_tienda(db: DbSession, actor: CurrentActor):
    return stores.mi_tienda(db, actor)


@router.patch("/me/tienda", response_model=TiendaOut,
              summary="Editar los datos de mi tienda (solo el administrador de la tienda; el RUC no cambia)")
def editar_mi_tienda(body: MiTiendaUpdate, db: DbSession, actor: StoreAdmin):
    return stores.actualizar_mi_tienda(db, actor, body)
