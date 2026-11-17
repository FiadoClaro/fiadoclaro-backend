from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from fastapi.security import OAuth2PasswordRequestForm

from app.core.deps import CurrentActor, DbSession
from app.modules.iam import service
from app.modules.iam.schemas import CambioPassword, TokenOut, UsuarioOut

router = APIRouter(prefix="/iam", tags=["IAM - Acceso"])


@router.post("/login", response_model=TokenOut, summary="Iniciar sesión (usuario y contraseña)")
def login(request: Request, db: DbSession, form: Annotated[OAuth2PasswordRequestForm, Depends()]):
    token, usuario = service.login(db, form.username, form.password, request.client.host if request.client else None)
    return TokenOut(access_token=token, usuario=UsuarioOut.model_validate(usuario))


@router.get("/me", response_model=UsuarioOut, summary="Usuario de la sesión actual")
def me(actor: CurrentActor):
    return actor.usuario


@router.post("/cambiar-password", status_code=status.HTTP_204_NO_CONTENT, summary="Cambiar mi contraseña")
def cambiar_password(body: CambioPassword, db: DbSession, actor: CurrentActor):
    service.cambiar_password(db, actor, body.password_actual, body.password_nueva)
