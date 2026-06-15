"""Router de autenticación: login y logout."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth.security import verify_password
from app.database import get_db
from app.models.usuario import Usuario
from app.web import flash, render

router = APIRouter(tags=["auth"])


@router.get("/login")
def login_form(request: Request):
    """Muestra el formulario de login (o redirige si ya hay sesión)."""
    if request.session.get("user_id"):
        return RedirectResponse(url="/facturas", status_code=303)
    return render(request, "login.html")


@router.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    """Valida credenciales y crea la sesión."""
    user = db.query(Usuario).filter(Usuario.username == username).first()
    if (
        user is None
        or not user.activo
        or not verify_password(password, user.hashed_password)
    ):
        flash(request, "Usuario o contraseña incorrectos.", "danger")
        return render(request, "login.html", status_code=401)

    request.session["user_id"] = user.id
    request.session["username"] = user.username
    request.session["rol"] = user.rol.nombre
    flash(request, f"Bienvenido, {user.username}.", "success")
    return RedirectResponse(url="/facturas", status_code=303)


@router.get("/logout")
def logout(request: Request):
    """Cierra la sesión."""
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)
