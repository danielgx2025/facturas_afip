"""Router de gestión de roles (ABM + permisos por sección).

El acceso requiere el permiso ``usuarios`` (gate aplicado al incluir el router en
``app.main``). El rol marcado ``sistema`` está protegido: no se renombra, no se
elimina y no se le puede quitar el permiso de administración.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.auth.permisos import PERMISO_ADMIN, PERMISOS, filtrar_permisos
from app.database import get_db
from app.models.rol import Rol
from app.models.usuario import Usuario
from app.web import flash, render

router = APIRouter(prefix="/roles", tags=["roles"])


def _obtener_rol(db: Session, rol_id: int) -> Rol:
    rol = db.get(Rol, rol_id)
    if rol is None:
        raise HTTPException(status_code=404, detail="Rol inexistente.")
    return rol


@router.get("")
def listar(
    request: Request,
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    roles = db.query(Rol).order_by(Rol.nombre).all()
    return render(
        request, "roles/list.html", {"roles": roles, "permisos": PERMISOS}, user=user
    )


@router.get("/nuevo")
def nuevo_form(
    request: Request,
    user: Usuario = Depends(get_current_user),
):
    return render(request, "roles/form.html", {"permisos": PERMISOS}, user=user)


@router.post("")
def crear(
    request: Request,
    nombre: str = Form(...),
    descripcion: str = Form(""),
    permisos: list[str] = Form([]),
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    rol = Rol(
        nombre=nombre.strip(),
        descripcion=descripcion.strip(),
        permisos=filtrar_permisos(permisos),
        sistema=False,
    )
    db.add(rol)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        flash(request, f"Ya existe un rol con el nombre '{nombre}'.", "warning")
        return RedirectResponse(url="/roles/nuevo", status_code=303)
    flash(request, f"Rol '{rol.nombre}' creado.", "success")
    return RedirectResponse(url="/roles", status_code=303)


@router.get("/{rol_id}/editar")
def editar_form(
    request: Request,
    rol_id: int,
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    rol = _obtener_rol(db, rol_id)
    return render(
        request, "roles/form.html", {"rol": rol, "permisos": PERMISOS}, user=user
    )


@router.post("/{rol_id}")
def actualizar(
    request: Request,
    rol_id: int,
    nombre: str = Form(...),
    descripcion: str = Form(""),
    permisos: list[str] = Form([]),
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    rol = _obtener_rol(db, rol_id)
    seleccionados = filtrar_permisos(permisos)

    if rol.sistema:
        # Rol protegido: no se renombra y conserva siempre el permiso de admin.
        nombre = rol.nombre
        if PERMISO_ADMIN not in seleccionados:
            seleccionados.append(PERMISO_ADMIN)
            seleccionados = filtrar_permisos(seleccionados)

    rol.nombre = nombre.strip()
    rol.descripcion = descripcion.strip()
    rol.permisos = seleccionados
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        flash(request, f"Ya existe otro rol con el nombre '{nombre}'.", "warning")
        return RedirectResponse(url=f"/roles/{rol_id}/editar", status_code=303)
    flash(request, f"Rol '{rol.nombre}' actualizado.", "success")
    return RedirectResponse(url="/roles", status_code=303)


@router.post("/{rol_id}/eliminar")
def eliminar(
    request: Request,
    rol_id: int,
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    rol = _obtener_rol(db, rol_id)
    if rol.sistema:
        flash(request, "No se puede eliminar un rol del sistema.", "warning")
        return RedirectResponse(url="/roles", status_code=303)
    if rol.usuarios:
        flash(
            request,
            f"No se puede eliminar el rol '{rol.nombre}': tiene usuarios asignados.",
            "warning",
        )
        return RedirectResponse(url="/roles", status_code=303)
    db.delete(rol)
    db.commit()
    flash(request, f"Rol '{rol.nombre}' eliminado.", "warning")
    return RedirectResponse(url="/roles", status_code=303)
