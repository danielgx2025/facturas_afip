"""Router de empresas emisoras (alta, edición y certificados). Solo admin."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, require_role
from app.config import settings
from app.database import get_db
from app.models.empresa import Empresa
from app.models.punto_venta import PuntoVenta
from app.models.usuario import RolUsuario, Usuario
from app.web import flash, render

router = APIRouter(prefix="/empresas", tags=["empresas"])


@router.get("")
def listar(
    request: Request,
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    empresas = db.query(Empresa).all()
    return render(request, "empresas/list.html", {"empresas": empresas}, user=user)


@router.get("/nueva")
def nueva_form(
    request: Request,
    user: Usuario = Depends(require_role(RolUsuario.ADMIN)),
):
    return render(request, "empresas/form.html", user=user)


def _guardar_certificado(archivo: UploadFile, nombre_destino: str) -> str:
    """Guarda un certificado/clave en certs/ y devuelve su nombre relativo."""
    settings.ensure_directories()
    destino = settings.certs_path / nombre_destino
    with destino.open("wb") as f:
        f.write(archivo.file.read())
    return nombre_destino


def _obtener_empresa(db: Session, empresa_id: int) -> Empresa:
    empresa = db.get(Empresa, empresa_id)
    if empresa is None:
        raise HTTPException(status_code=404, detail="Empresa inexistente.")
    return empresa


@router.post("")
def crear(
    request: Request,
    cuit: str = Form(...),
    razon_social: str = Form(...),
    domicilio: str = Form(""),
    condicion_iva: str = Form("Responsable Inscripto"),
    ingresos_brutos: str = Form(""),
    inicio_actividades: str = Form(""),
    punto_venta: int = Form(1),
    cert: UploadFile = File(...),
    key: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: Usuario = Depends(require_role(RolUsuario.ADMIN)),
):
    """Crea la empresa, guarda sus certificados y su punto de venta."""
    cuit = cuit.strip()
    cert_rel = _guardar_certificado(cert, f"{cuit}.crt")
    key_rel = _guardar_certificado(key, f"{cuit}.key")

    empresa = Empresa(
        cuit=cuit,
        razon_social=razon_social,
        domicilio=domicilio,
        condicion_iva=condicion_iva,
        ingresos_brutos=ingresos_brutos,
        inicio_actividades=inicio_actividades,
        cert_path=cert_rel,
        key_path=key_rel,
        modo=settings.afip_modo,
        activo=True,
    )
    empresa.puntos_venta.append(
        PuntoVenta(numero=punto_venta, descripcion="Principal", activo=True)
    )
    db.add(empresa)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        flash(request, f"Ya existe una empresa con el CUIT {cuit}.", "warning")
        return RedirectResponse(url="/empresas/nueva", status_code=303)
    flash(request, f"Empresa '{razon_social}' creada.", "success")
    return RedirectResponse(url="/empresas", status_code=303)


@router.get("/{empresa_id}/editar")
def editar_form(
    request: Request,
    empresa_id: int,
    db: Session = Depends(get_db),
    user: Usuario = Depends(require_role(RolUsuario.ADMIN)),
):
    empresa = _obtener_empresa(db, empresa_id)
    return render(request, "empresas/form.html", {"empresa": empresa}, user=user)


@router.post("/{empresa_id}")
def actualizar(
    request: Request,
    empresa_id: int,
    cuit: str = Form(...),
    razon_social: str = Form(...),
    domicilio: str = Form(""),
    condicion_iva: str = Form("Responsable Inscripto"),
    ingresos_brutos: str = Form(""),
    inicio_actividades: str = Form(""),
    activo: bool = Form(False),  # checkbox: si no viene marcado, es False
    cert: UploadFile | None = File(None),
    key: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    user: Usuario = Depends(require_role(RolUsuario.ADMIN)),
):
    """Actualiza los datos de la empresa.

    Los certificados son opcionales: solo se reemplaza el archivo que se suba;
    si un campo de archivo queda vacío, se conserva el actual.
    """
    empresa = _obtener_empresa(db, empresa_id)
    cuit = cuit.strip()
    empresa.cuit = cuit
    empresa.razon_social = razon_social
    empresa.domicilio = domicilio
    empresa.condicion_iva = condicion_iva
    empresa.ingresos_brutos = ingresos_brutos
    empresa.inicio_actividades = inicio_actividades
    empresa.activo = activo

    if cert is not None and cert.filename:
        empresa.cert_path = _guardar_certificado(cert, f"{cuit}.crt")
    if key is not None and key.filename:
        empresa.key_path = _guardar_certificado(key, f"{cuit}.key")

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        flash(request, f"Ya existe otra empresa con el CUIT {cuit}.", "warning")
        return RedirectResponse(url=f"/empresas/{empresa_id}/editar", status_code=303)
    flash(request, f"Empresa '{razon_social}' actualizada.", "success")
    return RedirectResponse(url="/empresas", status_code=303)
