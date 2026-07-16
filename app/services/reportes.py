"""Servicio del reporte de facturas emitidas: consulta y totales agregados."""

from __future__ import annotations

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.models.cliente import Cliente
from app.models.comprobante import Comprobante


def buscar_comprobantes(
    db: Session,
    *,
    fecha_inicio: str,
    fecha_fin: str,
    cliente_id: int | None = None,
    empresa_id: int | None = None,
) -> list[Comprobante]:
    """Comprobantes emitidos en ``[fecha_inicio, fecha_fin]`` (ambos extremos
    inclusive). Incluye todos los tipos (facturas A/B/C + notas de crédito/
    débito), igual criterio que el listado de ``/facturas``.
    """
    consulta = (
        db.query(Comprobante)
        .join(Cliente, Comprobante.cliente_id == Cliente.id)
        .options(joinedload(Comprobante.cliente), joinedload(Comprobante.empresa))
        .filter(Comprobante.fecha >= fecha_inicio, Comprobante.fecha <= fecha_fin)
    )
    if cliente_id:
        consulta = consulta.filter(Comprobante.cliente_id == cliente_id)
    if empresa_id:
        consulta = consulta.filter(Comprobante.empresa_id == empresa_id)
    return consulta.order_by(
        Comprobante.fecha, Comprobante.punto_venta, Comprobante.numero
    ).all()


def buscar_clientes(
    db: Session,
    *,
    texto: str = "",
    empresa_id: int | None = None,
    estado: str = "todos",
) -> list[Cliente]:
    """Clientes para el listado de ``/reportes/clientes``. ``estado`` ya llega
    normalizado a ``"activos" | "inactivos" | "todos"`` desde el router."""
    consulta = db.query(Cliente).options(joinedload(Cliente.empresa))
    if texto:
        patron = f"%{texto}%"
        consulta = consulta.filter(
            or_(Cliente.razon_social.ilike(patron), Cliente.nro_doc.ilike(patron))
        )
    if empresa_id:
        consulta = consulta.filter(Cliente.empresa_id == empresa_id)
    if estado == "activos":
        consulta = consulta.filter(Cliente.fecha_baja.is_(None))
    elif estado == "inactivos":
        consulta = consulta.filter(Cliente.fecha_baja.isnot(None))
    return consulta.order_by(Cliente.razon_social).all()


def calcular_totales(comprobantes: list[Comprobante]) -> dict[str, float]:
    """Suma directa de neto/IVA/total (sin netear notas de crédito: la
    columna "Tipo" ya las distingue en el listado)."""
    return {
        "neto": round(sum(float(c.importe_neto) for c in comprobantes), 2),
        "iva": round(sum(float(c.importe_iva) for c in comprobantes), 2),
        "total": round(sum(float(c.importe_total) for c in comprobantes), 2),
        "cantidad": len(comprobantes),
    }
