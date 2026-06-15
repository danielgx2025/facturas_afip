"""Router de cuenta propia: cambio de contraseña en autoservicio.

Disponible para cualquier usuario autenticado (no requiere permisos especiales).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.auth.security import hash_password, verify_password
from app.database import get_db
from app.models.usuario import Usuario
from app.web import flash, render

router = APIRouter(prefix="/cuenta", tags=["cuenta"])


@router.get("/password")
def password_form(
    request: Request,
    user: Usuario = Depends(get_current_user),
):
    return render(request, "cuenta/password.html", user=user)


@router.post("/password")
def cambiar_password(
    request: Request,
    actual: str = Form(...),
    nueva: str = Form(...),
    repetir: str = Form(...),
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    """Cambia la contraseña del propio usuario validando la actual."""
    if not verify_password(actual, user.hashed_password):
        flash(request, "La contraseña actual es incorrecta.", "danger")
        return RedirectResponse(url="/cuenta/password", status_code=303)
    if not nueva or nueva != repetir:
        flash(request, "La nueva contraseña no coincide.", "warning")
        return RedirectResponse(url="/cuenta/password", status_code=303)

    user.hashed_password = hash_password(nueva)
    db.commit()
    flash(request, "Contraseña actualizada.", "success")
    return RedirectResponse(url="/facturas", status_code=303)
