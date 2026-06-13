"""Router de facturas: emisión, listado y descarga del PDF."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.afip.constants import (
    COMPROBANTES_CON_ASOCIADO,
    FACTURAS,
    TIPOS_COMPROBANTE,
)
from app.afip.exceptions import (
    AfipAuthError,
    AfipConnectionError,
    AfipValidationError,
)
from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.cliente import Cliente
from app.models.comprobante import Comprobante
from app.models.empresa import Empresa
from app.models.producto import Producto
from app.models.usuario import Usuario
from app.services.facturacion import LineaFactura, emitir_factura
from app.services.pdf_service import generar_pdf_comprobante
from app.web import flash, render

router = APIRouter(prefix="/facturas", tags=["facturas"])


@router.get("")
def listar(
    request: Request,
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    comprobantes = (
        db.query(Comprobante).order_by(Comprobante.id.desc()).limit(100).all()
    )
    return render(
        request,
        "facturas/list.html",
        {"comprobantes": comprobantes, "tipos": TIPOS_COMPROBANTE},
        user=user,
    )


@router.get("/nueva")
def nueva_form(
    request: Request,
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    empresas = db.query(Empresa).filter(Empresa.activo.is_(True)).all()
    clientes = db.query(Cliente).filter(Cliente.fecha_baja.is_(None)).all()
    productos = db.query(Producto).filter(Producto.activo.is_(True)).all()
    # Solo facturas con CAE: son las únicas asociables a una NC/ND. El filtro
    # por cliente se hace en el form (data-cliente), por eso el límite generoso.
    asociables = (
        db.query(Comprobante)
        .filter(Comprobante.cae.isnot(None))
        .filter(Comprobante.tipo_cbte.in_(FACTURAS))
        .order_by(Comprobante.id.desc())
        .limit(300)
        .all()
    )
    return render(
        request,
        "facturas/form.html",
        {
            "empresas": empresas,
            "clientes": clientes,
            "productos": productos,
            "tipos": TIPOS_COMPROBANTE,
            "asociables": asociables,
            "tipos_con_asociado": sorted(COMPROBANTES_CON_ASOCIADO),
        },
        user=user,
    )


@router.post("")
def emitir(
    request: Request,
    empresa_id: int = Form(...),
    punto_venta: int = Form(...),
    cliente_id: int = Form(...),
    tipo_cbte: int = Form(...),
    concepto: int = Form(1),
    cbte_asociado_id: str = Form(""),
    item_producto_id: list[int] = Form(default=[]),
    item_precio: list[float] = Form(default=[]),
    item_cantidad: list[float] = Form(default=[]),
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    """Construye las líneas desde los productos y emite el comprobante."""
    # Alinea la lista de precios con la de productos (0 = usar precio de lista).
    precios = list(item_precio) + [0.0] * (len(item_producto_id) - len(item_precio))

    # Armado de líneas a partir de los productos seleccionados.
    lineas: list[LineaFactura] = []
    for prod_id, precio, cantidad in zip(item_producto_id, precios, item_cantidad):
        if not prod_id or cantidad <= 0:
            continue
        producto = db.get(Producto, prod_id)
        if producto is None:
            continue
        # El precio del formulario manda; si quedó vacío o en 0, cae al precio
        # de lista del producto (un total 0 sería rechazado por AFIP).
        precio_unitario = float(precio) if precio > 0 else float(producto.precio_unitario)
        lineas.append(
            LineaFactura(
                descripcion=producto.descripcion,
                cantidad=float(cantidad),
                precio_unitario=precio_unitario,
                alicuota_iva=float(producto.alicuota_iva),
                producto_id=producto.id,
            )
        )

    if not lineas:
        flash(request, "Agregá al menos un producto con cantidad mayor a cero.", "warning")
        return RedirectResponse(url="/facturas/nueva", status_code=303)

    asociado_id = int(cbte_asociado_id) if cbte_asociado_id.strip() else None

    try:
        comprobante = emitir_factura(
            db,
            empresa_id=empresa_id,
            cliente_id=cliente_id,
            tipo_cbte=tipo_cbte,
            punto_venta=punto_venta,
            lineas=lineas,
            concepto=concepto,
            usuario_id=user.id,
            cbte_asociado_id=asociado_id,
        )
    except AfipValidationError as exc:
        detalle = "; ".join(exc.errores) or str(exc)
        flash(request, f"AFIP rechazó el comprobante: {detalle}", "danger")
        return RedirectResponse(url="/facturas/nueva", status_code=303)
    except AfipAuthError as exc:
        flash(request, f"Error de autenticación con AFIP: {exc}", "danger")
        return RedirectResponse(url="/facturas/nueva", status_code=303)
    except AfipConnectionError as exc:
        flash(request, f"Error de conexión con AFIP: {exc}", "danger")
        return RedirectResponse(url="/facturas/nueva", status_code=303)
    except ValueError as exc:
        flash(request, str(exc), "warning")
        return RedirectResponse(url="/facturas/nueva", status_code=303)

    flash(
        request,
        f"Comprobante emitido. CAE {comprobante.cae} "
        f"(vence {comprobante.cae_vencimiento}).",
        "success",
    )
    return RedirectResponse(url="/facturas", status_code=303)


@router.get("/{comprobante_id}/pdf")
def descargar_pdf(
    comprobante_id: int,
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    """Descarga el PDF del comprobante (lo regenera si no existe en disco)."""
    comprobante = db.get(Comprobante, comprobante_id)
    if comprobante is None:
        return RedirectResponse(url="/facturas", status_code=303)

    pdf_path = comprobante.pdf_path
    if not pdf_path or not Path(pdf_path).is_file():
        pdf_path = generar_pdf_comprobante(db, comprobante)
        comprobante.pdf_path = pdf_path
        db.commit()

    return FileResponse(
        pdf_path, media_type="application/pdf", filename=Path(pdf_path).name
    )
