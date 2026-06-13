"""Dependencias de FastAPI para autenticación y control de roles.

El login guarda ``user_id`` en la sesión (cookie firmada). Estas dependencias
recuperan el usuario actual y restringen el acceso por rol.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.usuario import RolUsuario, Usuario


class NotAuthenticatedError(Exception):
    """Se lanza cuando no hay usuario en sesión (se traduce a redirect al login)."""


def get_current_user(
    request: Request, db: Session = Depends(get_db)
) -> Usuario:
    """Devuelve el usuario autenticado o lanza ``NotAuthenticatedError``."""
    user_id = request.session.get("user_id")
    if not user_id:
        raise NotAuthenticatedError()
    user = db.get(Usuario, user_id)
    if user is None or not user.activo:
        request.session.clear()
        raise NotAuthenticatedError()
    return user


def require_role(*roles: RolUsuario) -> Callable[..., Usuario]:
    """Crea una dependencia que exige uno de los roles indicados."""

    def _checker(user: Usuario = Depends(get_current_user)) -> Usuario:
        if roles and user.rol not in roles:
            # 403: autenticado pero sin permisos.
            from fastapi import HTTPException, status

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tenés permisos para esta acción.",
            )
        return user

    return _checker


def redirect_to_login() -> RedirectResponse:
    """Helper para redirigir al login (usado por el handler de excepción)."""
    return RedirectResponse(url="/login", status_code=303)
