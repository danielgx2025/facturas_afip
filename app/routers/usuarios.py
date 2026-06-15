"""Router de gestión de usuarios (ABM + asignación de rol + contraseñas).

El acceso requiere el permiso ``usuarios`` (gate aplicado al incluir el router en
``app.main``). Incluye protección anti-bloqueo: el sistema nunca puede quedar sin
un usuario activo capaz de administrar usuarios y roles.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.auth.permisos import PERMISO_ADMIN
from app.auth.security import hash_password
from app.database import get_db
from app.models.rol import Rol
from app.models.usuario import Usuario
from app.web import flash, render

router = APIRouter(prefix="/usuarios", tags=["usuarios"])


def _obtener_usuario(db: Session, usuario_id: int) -> Usuario:
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(status_code=404, detail="Usuario inexistente.")
    return usuario


def _roles_disponibles(db: Session) -> list[Rol]:
    return db.query(Rol).order_by(Rol.nombre).all()


def _hay_otro_admin_activo(
    db: Session, excluyendo_usuario_id: int | None = None
) -> bool:
    """¿Queda algún usuario activo (distinto del excluido) con permiso de admin?"""
    for u in db.query(Usuario).filter(Usuario.activo.is_(True)).all():
        if u.id == excluyendo_usuario_id:
            continue
        if u.puede(PERMISO_ADMIN):
            return True
    return False


@router.get("")
def listar(
    request: Request,
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    # Activos primero, luego por nombre de usuario.
    usuarios = (
        db.query(Usuario).order_by(Usuario.activo.is_(False), Usuario.username).all()
    )
    return render(request, "usuarios/list.html", {"usuarios": usuarios}, user=user)


@router.get("/nuevo")
def nuevo_form(
    request: Request,
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    return render(
        request, "usuarios/form.html", {"roles": _roles_disponibles(db)}, user=user
    )


@router.post("")
def crear(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    rol_id: int = Form(...),
    activo: bool = Form(False),  # checkbox: si no viene marcado, es False
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    if db.get(Rol, rol_id) is None:
        flash(request, "El rol seleccionado no existe.", "warning")
        return RedirectResponse(url="/usuarios/nuevo", status_code=303)

    usuario = Usuario(
        username=username.strip(),
        email=email.strip(),
        hashed_password=hash_password(password),
        rol_id=rol_id,
        activo=activo,
    )
    db.add(usuario)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        flash(request, "Ya existe un usuario con ese nombre o email.", "warning")
        return RedirectResponse(url="/usuarios/nuevo", status_code=303)
    flash(request, f"Usuario '{usuario.username}' creado.", "success")
    return RedirectResponse(url="/usuarios", status_code=303)


@router.get("/{usuario_id}/editar")
def editar_form(
    request: Request,
    usuario_id: int,
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    usuario = _obtener_usuario(db, usuario_id)
    return render(
        request,
        "usuarios/form.html",
        {"usuario": usuario, "roles": _roles_disponibles(db)},
        user=user,
    )


@router.post("/{usuario_id}")
def actualizar(
    request: Request,
    usuario_id: int,
    username: str = Form(...),
    email: str = Form(...),
    rol_id: int = Form(...),
    activo: bool = Form(False),
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    """Actualiza datos y rol del usuario. La contraseña se cambia aparte."""
    usuario = _obtener_usuario(db, usuario_id)
    nuevo_rol = db.get(Rol, rol_id)
    if nuevo_rol is None:
        flash(request, "El rol seleccionado no existe.", "warning")
        return RedirectResponse(url=f"/usuarios/{usuario_id}/editar", status_code=303)

    # Anti-bloqueo: si el cambio dejaría a este usuario sin capacidad de admin
    # (rol sin permiso o inactivo) y no queda ningún otro admin activo, se rechaza.
    seguira_siendo_admin = activo and nuevo_rol.tiene_permiso(PERMISO_ADMIN)
    if not seguira_siendo_admin and not _hay_otro_admin_activo(
        db, excluyendo_usuario_id=usuario.id
    ):
        flash(
            request,
            "No se puede quitar el último usuario con acceso a la administración.",
            "warning",
        )
        return RedirectResponse(url=f"/usuarios/{usuario_id}/editar", status_code=303)

    usuario.username = username.strip()
    usuario.email = email.strip()
    usuario.rol_id = rol_id
    usuario.activo = activo
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        flash(request, "Ya existe otro usuario con ese nombre o email.", "warning")
        return RedirectResponse(url=f"/usuarios/{usuario_id}/editar", status_code=303)
    flash(request, f"Usuario '{usuario.username}' actualizado.", "success")
    return RedirectResponse(url="/usuarios", status_code=303)


@router.get("/{usuario_id}/password")
def reset_password_form(
    request: Request,
    usuario_id: int,
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    usuario = _obtener_usuario(db, usuario_id)
    return render(
        request, "usuarios/reset_password.html", {"usuario": usuario}, user=user
    )


@router.post("/{usuario_id}/password")
def reset_password(
    request: Request,
    usuario_id: int,
    password: str = Form(...),
    password2: str = Form(...),
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    """Blanqueo de contraseña por un administrador."""
    usuario = _obtener_usuario(db, usuario_id)
    if not password or password != password2:
        flash(request, "Las contraseñas no coinciden.", "warning")
        return RedirectResponse(url=f"/usuarios/{usuario_id}/password", status_code=303)
    usuario.hashed_password = hash_password(password)
    db.commit()
    flash(request, f"Contraseña de '{usuario.username}' actualizada.", "success")
    return RedirectResponse(url="/usuarios", status_code=303)


@router.post("/{usuario_id}/desactivar")
def desactivar(
    request: Request,
    usuario_id: int,
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    usuario = _obtener_usuario(db, usuario_id)
    if usuario.id == user.id:
        flash(request, "No podés desactivar tu propio usuario.", "warning")
        return RedirectResponse(url="/usuarios", status_code=303)
    if usuario.puede(PERMISO_ADMIN) and not _hay_otro_admin_activo(
        db, excluyendo_usuario_id=usuario.id
    ):
        flash(
            request,
            "No se puede desactivar el último usuario con acceso a la administración.",
            "warning",
        )
        return RedirectResponse(url="/usuarios", status_code=303)
    usuario.activo = False
    db.commit()
    flash(request, f"Usuario '{usuario.username}' desactivado.", "warning")
    return RedirectResponse(url="/usuarios", status_code=303)


@router.post("/{usuario_id}/reactivar")
def reactivar(
    request: Request,
    usuario_id: int,
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    usuario = _obtener_usuario(db, usuario_id)
    usuario.activo = True
    db.commit()
    flash(request, f"Usuario '{usuario.username}' reactivado.", "success")
    return RedirectResponse(url="/usuarios", status_code=303)
