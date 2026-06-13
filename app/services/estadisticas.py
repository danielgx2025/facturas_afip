"""Servicio de estadísticas para el dashboard de facturación.

Agrega los comprobantes aprobados (con CAE) por mes y por cliente, con criterio
contable: facturas y notas de débito suman, **notas de crédito restan**. La fecha
del comprobante se guarda como string ``"YYYY-MM-DD"``, por lo que el mes se
obtiene con ``substr(fecha, 1, 7)``.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.afip.constants import NOTAS_CREDITO
from app.models.cliente import Cliente
from app.models.comprobante import Comprobante

# Máximo de porciones en la torta; el resto se agrupa como "Otros".
TOP_CLIENTES_TORTA = 10


def _rango_periodo(periodo: str, hoy: date | None = None) -> tuple[str, str]:
    """Rango calendario del período en curso: ``(desde, hasta_exclusivo)``.

    ``hasta_exclusivo`` es el primer día del período siguiente, para filtrar con
    ``fecha >= desde AND fecha < hasta`` sin calcular fines de mes.
    Valores de ``periodo``: ``mensual`` | ``trimestral`` | ``semestral`` |
    ``anual`` (default ante un valor no reconocido).
    """
    hoy = hoy or date.today()
    anio, mes = hoy.year, hoy.month

    if periodo == "mensual":
        mes_inicio, meses_duracion = mes, 1
    elif periodo == "trimestral":
        mes_inicio, meses_duracion = ((mes - 1) // 3) * 3 + 1, 3
    elif periodo == "semestral":
        mes_inicio, meses_duracion = (1 if mes <= 6 else 7), 6
    else:  # anual (default)
        mes_inicio, meses_duracion = 1, 12

    mes_fin = mes_inicio + meses_duracion  # primer mes del período siguiente
    anio_fin = anio + (mes_fin - 1) // 12
    mes_fin = (mes_fin - 1) % 12 + 1
    return f"{anio:04d}-{mes_inicio:02d}-01", f"{anio_fin:04d}-{mes_fin:02d}-01"


def totales_por_cliente_mensual(
    db: Session,
    *,
    empresa_id: int | None = None,
    periodo: str = "anual",
) -> dict:
    """Totales facturados por cliente y por mes, listos para Chart.js.

    Args:
        db: sesión de base de datos.
        empresa_id: limitar a una empresa emisora (None = todas).
        periodo: período calendario en curso (``mensual`` | ``trimestral`` |
            ``semestral`` | ``anual``).

    Returns:
        ``{"meses": [...], "clientes": [...], "series": {cliente: [tot/mes]},
        "torta": {"labels": [...], "data": [...]}, "total_periodo": float,
        "cantidad_comprobantes": int, "cantidad_clientes": int}``
        Meses ordenados; cada serie alineada con ``meses``. Clientes ordenados
        por total del período (descendente).
    """
    mes = func.substr(Comprobante.fecha, 1, 7).label("mes")
    # Las notas de crédito restan; facturas y notas de débito suman.
    total_firmado = func.sum(
        case(
            (Comprobante.tipo_cbte.in_(NOTAS_CREDITO), -Comprobante.importe_total),
            else_=Comprobante.importe_total,
        )
    ).label("total")
    cantidad = func.count(Comprobante.id).label("cantidad")

    consulta = (
        db.query(mes, Cliente.razon_social.label("cliente"), total_firmado, cantidad)
        .join(Cliente, Comprobante.cliente_id == Cliente.id)
        .filter(Comprobante.cae.isnot(None))
    )
    if empresa_id:
        consulta = consulta.filter(Comprobante.empresa_id == empresa_id)
    desde, hasta = _rango_periodo(periodo)
    consulta = consulta.filter(Comprobante.fecha >= desde, Comprobante.fecha < hasta)

    filas = consulta.group_by(mes, Cliente.razon_social).order_by(mes).all()

    meses = sorted({f.mes for f in filas})
    por_cliente_mes: dict[str, dict[str, float]] = defaultdict(dict)
    total_cliente: dict[str, float] = defaultdict(float)
    cantidad_total = 0
    for f in filas:
        total = float(f.total)
        # Un cliente puede repetirse en el mismo mes si comparte razón social
        # entre empresas: se acumula.
        por_cliente_mes[f.cliente][f.mes] = (
            por_cliente_mes[f.cliente].get(f.mes, 0.0) + total
        )
        total_cliente[f.cliente] += total
        cantidad_total += int(f.cantidad)

    clientes = sorted(total_cliente, key=lambda c: total_cliente[c], reverse=True)
    series = {
        c: [round(por_cliente_mes[c].get(m, 0.0), 2) for m in meses] for c in clientes
    }

    # Torta: top N + "Otros".
    top = clientes[:TOP_CLIENTES_TORTA]
    labels = list(top)
    data = [round(total_cliente[c], 2) for c in top]
    resto = clientes[TOP_CLIENTES_TORTA:]
    if resto:
        labels.append("Otros")
        data.append(round(sum(total_cliente[c] for c in resto), 2))

    return {
        "meses": meses,
        "clientes": clientes,
        "series": series,
        "torta": {"labels": labels, "data": data},
        "total_periodo": round(sum(total_cliente.values()), 2),
        "cantidad_comprobantes": cantidad_total,
        "cantidad_clientes": len(clientes),
    }
