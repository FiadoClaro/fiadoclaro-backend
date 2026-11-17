"""Dependencias comunes: sesión de BD, usuario autenticado y control de roles."""
from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import decode_token
from app.modules.iam.models import Usuario
from app.modules.stores.models import Tienda

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_PREFIX}/iam/login")

DbSession = Annotated[Session, Depends(get_db)]


@dataclass
class Actor:
    """Quién hace la operación (se usa para permisos y para la bitácora)."""

    usuario: Usuario
    ip: str | None

    @property
    def id(self) -> int:
        return self.usuario.id

    @property
    def rol(self) -> str:
        return self.usuario.rol

    @property
    def tienda_id(self) -> int | None:
        return self.usuario.tienda_id


def _no_autorizado(detalle: str = "Credenciales inválidas") -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail=detalle, headers={"WWW-Authenticate": "Bearer"})


def get_actor(request: Request, db: DbSession, token: Annotated[str, Depends(oauth2_scheme)]) -> Actor:
    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError:
        raise _no_autorizado("La sesión expiró, vuelve a iniciar sesión")
    except jwt.PyJWTError:
        raise _no_autorizado()
    usuario = db.get(Usuario, int(payload["sub"]))
    if not usuario or not usuario.activo:
        raise _no_autorizado("Usuario inactivo o inexistente")
    if usuario.tienda_id is not None:
        tienda = db.get(Tienda, usuario.tienda_id)
        if not tienda or tienda.estado != "ACTIVA":
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="La tienda está dada de baja")
    ip = request.client.host if request.client else None
    return Actor(usuario=usuario, ip=ip)


def require_roles(*roles: str):
    def _check(actor: Annotated[Actor, Depends(get_actor)]) -> Actor:
        if actor.rol not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="No tienes permiso para esta operación")
        return actor

    return _check


CurrentActor = Annotated[Actor, Depends(get_actor)]
SystemAdmin = Annotated[Actor, Depends(require_roles("ADMIN_SISTEMA"))]
StoreAdmin = Annotated[Actor, Depends(require_roles("ADMIN_TIENDA"))]
CustomerUser = Annotated[Actor, Depends(require_roles("CLIENTE"))]
AnyAdmin = Annotated[Actor, Depends(require_roles("ADMIN_SISTEMA", "ADMIN_TIENDA"))]
