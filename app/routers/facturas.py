"""Router de facturas: emisión, listado y descarga del PDF."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session, selectinload

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
from app.logging_config import get_logger
from app.models.cliente import Cliente
from app.models.comprobante import Comprobante
from app.models.empresa import Empresa
from app.models.producto import Producto
from app.models.usuario import Usuario
from app.services.facturacion import LineaFactura, emitir_factura
from app.services.pdf_service import generar_pdf_comprobante
from app.web import flash, render

router = APIRouter(prefix="/facturas", tags=["facturas"])
logger = get_logger("routers.facturas")


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


def _contexto_formulario(db: Session) -> dict:
    """Arma los combos del form de emisión (empresas, clientes, productos,
    asociables, puntos de venta). Lo usan tanto el alta (GET /nueva) como el
    re-render tras un error de emisión (POST /facturas)."""
    empresas = (
        db.query(Empresa)
        .filter(Empresa.activo.is_(True))
        .options(selectinload(Empresa.puntos_venta))
        .all()
    )
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
    # Puntos de venta activos por empresa, para poblar el combo dependiente
    # en el form (ver facturas/form.html) sin pegarle a un endpoint aparte.
    puntos_venta_por_empresa = {
        e.id: [
            {"numero": pv.numero, "descripcion": pv.descripcion}
            for pv in e.puntos_venta
            if pv.activo
        ]
        for e in empresas
    }
    return {
        "empresas": empresas,
        "clientes": clientes,
        "productos": productos,
        "tipos": TIPOS_COMPROBANTE,
        "asociables": asociables,
        "tipos_con_asociado": sorted(COMPROBANTES_CON_ASOCIADO),
        "puntos_venta_por_empresa": puntos_venta_por_empresa,
    }


def _filas_item(
    item_producto_id: list[int], item_precio: list[float], item_cantidad: list[float]
) -> list[dict]:
    """Empareja las 3 listas paralelas del form en filas, para repoblar la
    tabla de ítems tras un error de emisión (mismo padding que el armado de
    líneas)."""
    precios = list(item_precio) + [0.0] * (len(item_producto_id) - len(item_precio))
    cantidades = list(item_cantidad) + [0.0] * (
        len(item_producto_id) - len(item_cantidad)
    )
    return [
        {"producto_id": p, "precio": pr, "cantidad": c}
        for p, pr, c in zip(item_producto_id, precios, cantidades)
    ]


@router.get("/nueva")
def nueva_form(
    request: Request,
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    return render(request, "facturas/form.html", _contexto_formulario(db), user=user)


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
    asociado_id = int(cbte_asociado_id) if cbte_asociado_id.strip() else None

    datos_previos = {
        "empresa_id": empresa_id,
        "punto_venta": punto_venta,
        "cliente_id": cliente_id,
        "tipo_cbte": tipo_cbte,
        "concepto": concepto,
        "cbte_asociado_id": asociado_id,
        # Nombre "filas" (no "items"): en un dict, dp.items resolvería al
        # método dict.items() vía getattr antes de caer al acceso por clave
        # que usa Jinja, rompiendo el {% for item in dp.items %} del template.
        "filas": _filas_item(item_producto_id, item_precio, item_cantidad),
    }

    def _reintentar(mensaje: str, categoria: str):
        """Muestra el error sin perder lo cargado: re-renderiza el mismo form
        con los combos frescos + los valores que el usuario había puesto."""
        db.rollback()  # defensivo: no debería haber writes pendientes en este punto
        flash(request, mensaje, categoria)
        contexto = _contexto_formulario(db)
        contexto["datos_previos"] = datos_previos
        return render(
            request, "facturas/form.html", contexto, user=user, status_code=422
        )

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
        precio_unitario = (
            float(precio) if precio > 0 else float(producto.precio_unitario)
        )
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
        return _reintentar(
            "Agregá al menos un producto con cantidad mayor a cero.", "warning"
        )

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
        return _reintentar(f"AFIP rechazó el comprobante: {detalle}", "danger")
    except AfipAuthError as exc:
        return _reintentar(f"Error de autenticación con AFIP: {exc}", "danger")
    except AfipConnectionError as exc:
        return _reintentar(f"Error de conexión con AFIP: {exc}", "danger")
    except ValueError as exc:
        return _reintentar(str(exc), "warning")
    except Exception:
        logger.exception(
            "Error inesperado al emitir comprobante (empresa=%s, cliente=%s, tipo=%s).",
            empresa_id,
            cliente_id,
            tipo_cbte,
        )
        return _reintentar(
            "Ocurrió un error inesperado al emitir el comprobante. "
            "Si el problema persiste, contactá al administrador.",
            "danger",
        )

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
