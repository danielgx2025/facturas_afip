"""Router de productos (ABM básico)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.producto import Producto
from app.models.usuario import Usuario
from app.web import flash, render

router = APIRouter(prefix="/productos", tags=["productos"])


@router.get("")
def listar(
    request: Request,
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    productos = db.query(Producto).all()
    return render(request, "productos/list.html", {"productos": productos}, user=user)


@router.get("/nuevo")
def nuevo_form(
    request: Request,
    user: Usuario = Depends(get_current_user),
):
    return render(request, "productos/form.html", user=user)


def _obtener_producto(db: Session, producto_id: int) -> Producto:
    producto = db.get(Producto, producto_id)
    if producto is None:
        raise HTTPException(status_code=404, detail="Producto inexistente.")
    return producto


@router.post("")
def crear(
    request: Request,
    codigo: str = Form(...),
    descripcion: str = Form(...),
    precio_unitario: float = Form(...),
    alicuota_iva: float = Form(21.0),
    unidad_medida: str = Form("unidad"),
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    producto = Producto(
        codigo=codigo,
        descripcion=descripcion,
        precio_unitario=precio_unitario,
        alicuota_iva=alicuota_iva,
        unidad_medida=unidad_medida,
        activo=True,
    )
    db.add(producto)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        flash(request, f"Ya existe un producto con el código '{codigo}'.", "warning")
        return RedirectResponse(url="/productos/nuevo", status_code=303)
    flash(request, f"Producto '{descripcion}' creado.", "success")
    return RedirectResponse(url="/productos", status_code=303)


@router.get("/{producto_id}/editar")
def editar_form(
    request: Request,
    producto_id: int,
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    producto = _obtener_producto(db, producto_id)
    return render(request, "productos/form.html", {"producto": producto}, user=user)


@router.post("/{producto_id}")
def actualizar(
    request: Request,
    producto_id: int,
    codigo: str = Form(...),
    descripcion: str = Form(...),
    precio_unitario: float = Form(...),
    alicuota_iva: float = Form(21.0),
    unidad_medida: str = Form("unidad"),
    activo: bool = Form(False),  # checkbox: si no viene marcado, es False
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    """Actualiza los datos del producto (incluido activar/desactivar)."""
    producto = _obtener_producto(db, producto_id)
    producto.codigo = codigo
    producto.descripcion = descripcion
    producto.precio_unitario = precio_unitario
    producto.alicuota_iva = alicuota_iva
    producto.unidad_medida = unidad_medida
    producto.activo = activo
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        flash(request, f"Ya existe otro producto con el código '{codigo}'.", "warning")
        return RedirectResponse(
            url=f"/productos/{producto_id}/editar", status_code=303
        )
    flash(request, f"Producto '{descripcion}' actualizado.", "success")
    return RedirectResponse(url="/productos", status_code=303)
