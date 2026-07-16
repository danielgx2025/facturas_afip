"""Router del reporte de facturas emitidas (filtro por fecha/cliente/empresa,
exportable en PDF y XLSX)."""

from __future__ import annotations

import re
from datetime import date
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

from app.afip.constants import TIPOS_COMPROBANTE
from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.cliente import Cliente
from app.models.empresa import Empresa
from app.models.usuario import Usuario
from app.services.estado_cuenta import calcular_estado_cuenta
from app.services.excel_service import (
    generar_excel_estado_cuenta,
    generar_excel_listado_clientes,
    generar_excel_reporte_facturas,
)
from app.services.pdf_service import (
    generar_pdf_estado_cuenta,
    generar_pdf_listado_clientes,
    generar_pdf_reporte_facturas,
)
from app.services.reportes import buscar_clientes, buscar_comprobantes, calcular_totales
from app.web import flash, render

router = APIRouter(prefix="/reportes", tags=["reportes"])


def _parse_filtros(
    fecha_inicio: str, fecha_fin: str, cliente_id: str, empresa_id: str
) -> tuple[str, str, int | None, int | None]:
    """Normaliza los filtros: fechas vacías caen al mes en curso; los selects
    vacíos (``""`` que manda el HTML) se convierten a ``None``."""
    hoy = date.today()
    fi = fecha_inicio.strip() or hoy.replace(day=1).isoformat()
    ff = fecha_fin.strip() or hoy.isoformat()
    cliente_id_int = int(cliente_id) if cliente_id.strip().isdigit() else None
    empresa_id_int = int(empresa_id) if empresa_id.strip().isdigit() else None
    return fi, ff, cliente_id_int, empresa_id_int


def _slug(texto: str) -> str:
    """Nombre de archivo seguro (sin espacios/acentos/caracteres especiales)."""
    return re.sub(r"[^A-Za-z0-9]+", "-", texto).strip("-")


def _nombre_archivo(
    fecha_inicio: str,
    fecha_fin: str,
    cliente: Cliente | None,
    empresa: Empresa | None,
    extension: str,
) -> str:
    partes = ["reporte_facturas", fecha_inicio, fecha_fin]
    if cliente:
        partes.append(_slug(cliente.razon_social))
    if empresa:
        partes.append(_slug(empresa.razon_social))
    return "_".join(partes) + f".{extension}"


def _parse_filtros_cuenta(
    fecha_inicio: str, fecha_fin: str, cliente_id: str
) -> tuple[str, str, int | None]:
    """Normaliza los filtros del estado de cuenta (sin filtro de empresa: el
    cliente ya la determina)."""
    hoy = date.today()
    fi = fecha_inicio.strip() or hoy.replace(day=1).isoformat()
    ff = fecha_fin.strip() or hoy.isoformat()
    cliente_id_int = int(cliente_id) if cliente_id.strip().isdigit() else None
    return fi, ff, cliente_id_int


def _nombre_archivo_cuenta(
    fecha_inicio: str, fecha_fin: str, cliente: Cliente, extension: str
) -> str:
    return (
        f"estado_cuenta_{_slug(cliente.razon_social)}_{fecha_inicio}_{fecha_fin}"
        f".{extension}"
    )


def _parse_filtros_clientes(
    texto: str, empresa_id: str, estado: str
) -> tuple[str, int | None, str]:
    """Normaliza los filtros del listado de clientes: ``texto`` se recorta,
    ``empresa_id`` cae a ``None`` si no es un id válido y ``estado`` cae a
    ``"todos"`` si no es uno de los tres valores esperados."""
    texto = texto.strip()
    emp_id = int(empresa_id) if empresa_id.strip().isdigit() else None
    estado = estado if estado in {"activos", "inactivos"} else "todos"
    return texto, emp_id, estado


def _nombre_archivo_clientes(
    texto: str, empresa: Empresa | None, estado: str, extension: str
) -> str:
    partes = ["listado_clientes", estado]
    if empresa:
        partes.append(_slug(empresa.razon_social))
    if texto:
        partes.append(_slug(texto))
    return "_".join(partes) + f".{extension}"


@router.get("/facturas")
def formulario(
    request: Request,
    fecha_inicio: str = "",
    fecha_fin: str = "",
    cliente_id: str = "",
    empresa_id: str = "",
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    fi, ff, cli_id, emp_id = _parse_filtros(
        fecha_inicio, fecha_fin, cliente_id, empresa_id
    )
    comprobantes = buscar_comprobantes(
        db, fecha_inicio=fi, fecha_fin=ff, cliente_id=cli_id, empresa_id=emp_id
    )
    totales = calcular_totales(comprobantes)
    clientes = (
        db.query(Cliente)
        .filter(Cliente.fecha_baja.is_(None))
        .order_by(Cliente.razon_social)
        .all()
    )
    empresas = (
        db.query(Empresa)
        .filter(Empresa.activo.is_(True))
        .order_by(Empresa.razon_social)
        .all()
    )
    query_string = f"fecha_inicio={fi}&fecha_fin={ff}&cliente_id={cli_id or ''}&empresa_id={emp_id or ''}"
    return render(
        request,
        "reportes/facturas.html",
        {
            "comprobantes": comprobantes,
            "totales": totales,
            "tipos": TIPOS_COMPROBANTE,
            "clientes": clientes,
            "empresas": empresas,
            "fecha_inicio": fi,
            "fecha_fin": ff,
            "cliente_id": cli_id,
            "empresa_id": emp_id,
            "query_string": query_string,
        },
        user=user,
    )


@router.get("/facturas/pdf")
def descargar_pdf(
    fecha_inicio: str = "",
    fecha_fin: str = "",
    cliente_id: str = "",
    empresa_id: str = "",
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
) -> Response:
    fi, ff, cli_id, emp_id = _parse_filtros(
        fecha_inicio, fecha_fin, cliente_id, empresa_id
    )
    comprobantes = buscar_comprobantes(
        db, fecha_inicio=fi, fecha_fin=ff, cliente_id=cli_id, empresa_id=emp_id
    )
    cliente = db.get(Cliente, cli_id) if cli_id else None
    empresa = db.get(Empresa, emp_id) if emp_id else None
    contenido = generar_pdf_reporte_facturas(
        comprobantes, fecha_inicio=fi, fecha_fin=ff, cliente=cliente, empresa=empresa
    )
    nombre = _nombre_archivo(fi, ff, cliente, empresa, "pdf")
    return Response(
        content=contenido,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


@router.get("/facturas/xlsx")
def descargar_xlsx(
    fecha_inicio: str = "",
    fecha_fin: str = "",
    cliente_id: str = "",
    empresa_id: str = "",
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
) -> Response:
    fi, ff, cli_id, emp_id = _parse_filtros(
        fecha_inicio, fecha_fin, cliente_id, empresa_id
    )
    comprobantes = buscar_comprobantes(
        db, fecha_inicio=fi, fecha_fin=ff, cliente_id=cli_id, empresa_id=emp_id
    )
    cliente = db.get(Cliente, cli_id) if cli_id else None
    empresa = db.get(Empresa, emp_id) if emp_id else None
    contenido = generar_excel_reporte_facturas(
        comprobantes, fecha_inicio=fi, fecha_fin=ff, cliente=cliente, empresa=empresa
    )
    nombre = _nombre_archivo(fi, ff, cliente, empresa, "xlsx")
    return Response(
        content=contenido,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


@router.get("/estado-cuenta")
def estado_cuenta_formulario(
    request: Request,
    fecha_inicio: str = "",
    fecha_fin: str = "",
    cliente_id: str = "",
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    fi, ff, cli_id = _parse_filtros_cuenta(fecha_inicio, fecha_fin, cliente_id)
    clientes = (
        db.query(Cliente)
        .filter(Cliente.fecha_baja.is_(None))
        .order_by(Cliente.razon_social)
        .all()
    )
    estado = None
    query_string = ""
    if cli_id:
        cliente = db.get(Cliente, cli_id)
        if cliente is None:
            flash(request, "El cliente seleccionado no existe.", "warning")
        else:
            estado = calcular_estado_cuenta(
                db, cliente=cliente, fecha_inicio=fi, fecha_fin=ff
            )
            query_string = f"fecha_inicio={fi}&fecha_fin={ff}&cliente_id={cli_id}"
    return render(
        request,
        "reportes/estado_cuenta.html",
        {
            "estado": estado,
            "clientes": clientes,
            "tipos": TIPOS_COMPROBANTE,
            "fecha_inicio": fi,
            "fecha_fin": ff,
            "cliente_id": cli_id,
            "query_string": query_string,
        },
        user=user,
    )


@router.get("/estado-cuenta/pdf")
def estado_cuenta_pdf(
    request: Request,
    fecha_inicio: str = "",
    fecha_fin: str = "",
    cliente_id: str = "",
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
) -> Response:
    fi, ff, cli_id = _parse_filtros_cuenta(fecha_inicio, fecha_fin, cliente_id)
    cliente = db.get(Cliente, cli_id) if cli_id else None
    if cliente is None:
        flash(
            request,
            "Debe seleccionar un cliente para descargar el estado de cuenta.",
            "warning",
        )
        return RedirectResponse(url="/reportes/estado-cuenta", status_code=303)
    estado = calcular_estado_cuenta(db, cliente=cliente, fecha_inicio=fi, fecha_fin=ff)
    contenido = generar_pdf_estado_cuenta(estado)
    nombre = _nombre_archivo_cuenta(fi, ff, cliente, "pdf")
    return Response(
        content=contenido,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


@router.get("/estado-cuenta/xlsx")
def estado_cuenta_xlsx(
    request: Request,
    fecha_inicio: str = "",
    fecha_fin: str = "",
    cliente_id: str = "",
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
) -> Response:
    fi, ff, cli_id = _parse_filtros_cuenta(fecha_inicio, fecha_fin, cliente_id)
    cliente = db.get(Cliente, cli_id) if cli_id else None
    if cliente is None:
        flash(
            request,
            "Debe seleccionar un cliente para descargar el estado de cuenta.",
            "warning",
        )
        return RedirectResponse(url="/reportes/estado-cuenta", status_code=303)
    estado = calcular_estado_cuenta(db, cliente=cliente, fecha_inicio=fi, fecha_fin=ff)
    contenido = generar_excel_estado_cuenta(estado)
    nombre = _nombre_archivo_cuenta(fi, ff, cliente, "xlsx")
    return Response(
        content=contenido,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


@router.get("/clientes")
def clientes_formulario(
    request: Request,
    texto: str = "",
    empresa_id: str = "",
    estado: str = "",
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    txt, emp_id, est = _parse_filtros_clientes(texto, empresa_id, estado)
    clientes = buscar_clientes(db, texto=txt, empresa_id=emp_id, estado=est)
    empresas = (
        db.query(Empresa)
        .filter(Empresa.activo.is_(True))
        .order_by(Empresa.razon_social)
        .all()
    )
    query_string = urlencode({"texto": txt, "empresa_id": emp_id or "", "estado": est})
    return render(
        request,
        "reportes/clientes.html",
        {
            "clientes": clientes,
            "empresas": empresas,
            "texto": txt,
            "empresa_id": emp_id,
            "estado": est,
            "query_string": query_string,
        },
        user=user,
    )


@router.get("/clientes/pdf")
def clientes_pdf(
    texto: str = "",
    empresa_id: str = "",
    estado: str = "",
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
) -> Response:
    txt, emp_id, est = _parse_filtros_clientes(texto, empresa_id, estado)
    clientes = buscar_clientes(db, texto=txt, empresa_id=emp_id, estado=est)
    empresa = db.get(Empresa, emp_id) if emp_id else None
    contenido = generar_pdf_listado_clientes(
        clientes, texto=txt, empresa=empresa, estado=est
    )
    nombre = _nombre_archivo_clientes(txt, empresa, est, "pdf")
    return Response(
        content=contenido,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


@router.get("/clientes/xlsx")
def clientes_xlsx(
    texto: str = "",
    empresa_id: str = "",
    estado: str = "",
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
) -> Response:
    txt, emp_id, est = _parse_filtros_clientes(texto, empresa_id, estado)
    clientes = buscar_clientes(db, texto=txt, empresa_id=emp_id, estado=est)
    empresa = db.get(Empresa, emp_id) if emp_id else None
    contenido = generar_excel_listado_clientes(
        clientes, texto=txt, empresa=empresa, estado=est
    )
    nombre = _nombre_archivo_clientes(txt, empresa, est, "xlsx")
    return Response(
        content=contenido,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )
