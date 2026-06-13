"""Router de clientes (ABM básico)."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.afip.constants import DOC_CUIT
from app.afip.exceptions import AfipError, AfipValidationError
from app.auth.dependencies import get_current_user
from app.database import get_db
from app.logging_config import get_logger
from app.models.cliente import Cliente
from app.models.empresa import Empresa
from app.models.usuario import Usuario
from app.services.padron import consultar_cliente_afip
from app.web import flash, render

logger = get_logger("routers.clientes")

router = APIRouter(prefix="/clientes", tags=["clientes"])


@router.get("")
def listar(
    request: Request,
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    # Activos primero, dados de baja al final.
    clientes = (
        db.query(Cliente)
        .order_by(Cliente.fecha_baja.isnot(None), Cliente.razon_social)
        .all()
    )
    return render(request, "clientes/list.html", {"clientes": clientes}, user=user)


def _obtener_cliente(db: Session, cliente_id: int) -> Cliente:
    cliente = db.get(Cliente, cliente_id)
    if cliente is None:
        raise HTTPException(status_code=404, detail="Cliente inexistente.")
    return cliente


@router.get("/nuevo")
def nuevo_form(
    request: Request,
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    empresas = db.query(Empresa).filter(Empresa.activo.is_(True)).all()
    return render(request, "clientes/form.html", {"empresas": empresas}, user=user)


@router.get("/consultar-afip")
def consultar_afip(
    empresa_id: int,
    cuit: str,
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    """Consulta el Padrón de AFIP por CUIT y devuelve los datos para el alta.

    Responde JSON: ``{ok: true, ...datos}`` o ``{ok: false, error}``. Pensado
    para ser consumido por el botón "Consultar AFIP" del formulario de cliente.
    """
    try:
        datos = consultar_cliente_afip(db, empresa_id=empresa_id, cuit=cuit)
    except AfipValidationError as exc:
        # CUIT inválido o sin datos en AFIP: error del lado del pedido.
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    except AfipError as exc:
        # Conexión / autenticación (ej.: servicio no delegado al certificado).
        logger.warning("Fallo consulta padrón (empresa %s): %s", empresa_id, exc)
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=502)

    return JSONResponse(
        {
            "ok": True,
            "razon_social": datos.denominacion,
            "condicion_iva": datos.condicion_iva_texto,
            "domicilio": datos.domicilio,
            "tipo_doc": DOC_CUIT,
            "nro_doc": datos.cuit,
            "estado": datos.estado,
        }
    )


@router.post("")
def crear(
    request: Request,
    empresa_id: int = Form(...),
    razon_social: str = Form(...),
    tipo_doc: int = Form(99),
    nro_doc: str = Form("0"),
    condicion_iva: str = Form("Consumidor Final"),
    domicilio: str = Form(""),
    email: str = Form(""),
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    cliente = Cliente(
        empresa_id=empresa_id,
        razon_social=razon_social,
        tipo_doc=tipo_doc,
        nro_doc=nro_doc,
        condicion_iva=condicion_iva,
        domicilio=domicilio,
        email=email,
    )
    db.add(cliente)
    db.commit()
    flash(request, f"Cliente '{razon_social}' creado.", "success")
    return RedirectResponse(url="/clientes", status_code=303)


@router.get("/{cliente_id}/editar")
def editar_form(
    request: Request,
    cliente_id: int,
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    cliente = _obtener_cliente(db, cliente_id)
    empresas = db.query(Empresa).filter(Empresa.activo.is_(True)).all()
    return render(
        request,
        "clientes/form.html",
        {"empresas": empresas, "cliente": cliente},
        user=user,
    )


@router.post("/{cliente_id}")
def actualizar(
    request: Request,
    cliente_id: int,
    razon_social: str = Form(...),
    tipo_doc: int = Form(99),
    nro_doc: str = Form("0"),
    condicion_iva: str = Form("Consumidor Final"),
    domicilio: str = Form(""),
    email: str = Form(""),
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    """Actualiza los datos del cliente (la empresa no se cambia en edición)."""
    cliente = _obtener_cliente(db, cliente_id)
    cliente.razon_social = razon_social
    cliente.tipo_doc = tipo_doc
    cliente.nro_doc = nro_doc
    cliente.condicion_iva = condicion_iva
    cliente.domicilio = domicilio
    cliente.email = email
    db.commit()
    flash(request, f"Cliente '{razon_social}' actualizado.", "success")
    return RedirectResponse(url="/clientes", status_code=303)


@router.post("/{cliente_id}/baja")
def dar_de_baja(
    request: Request,
    cliente_id: int,
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    """Baja lógica: marca la fecha de baja sin borrar el registro."""
    cliente = _obtener_cliente(db, cliente_id)
    cliente.fecha_baja = datetime.now()
    db.commit()
    flash(request, f"Cliente '{cliente.razon_social}' dado de baja.", "warning")
    return RedirectResponse(url="/clientes", status_code=303)


@router.post("/{cliente_id}/reactivar")
def reactivar(
    request: Request,
    cliente_id: int,
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    """Deshace la baja lógica (vuelve a dejar al cliente activo)."""
    cliente = _obtener_cliente(db, cliente_id)
    cliente.fecha_baja = None
    db.commit()
    flash(request, f"Cliente '{cliente.razon_social}' reactivado.", "success")
    return RedirectResponse(url="/clientes", status_code=303)
