"""Servicio del reporte de estado de cuenta por cliente: saldo anterior +
movimientos del período con saldo acumulado corriente.

Solo considera comprobantes aprobados por AFIP (con CAE) — igual criterio que
app.services.estadisticas: un comprobante rechazado/sin autorizar no es deuda
real. Notas de crédito restan, facturas y notas de débito suman.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import case, func
from sqlalchemy.orm import Session, joinedload

from app.afip.constants import NOTAS_CREDITO
from app.models.cliente import Cliente
from app.models.comprobante import Comprobante


@dataclass
class MovimientoCuenta:
    comprobante: Comprobante
    importe: float  # NC: negativo; Factura/ND: positivo
    saldo: float  # saldo corriente (arrastra saldo_anterior)


@dataclass
class EstadoCuenta:
    cliente: Cliente
    fecha_inicio: str
    fecha_fin: str
    saldo_anterior: float
    movimientos: list[MovimientoCuenta]
    saldo_final: float

    @property
    def cantidad_movimientos(self) -> int:
        return len(self.movimientos)


def _saldo_a_fecha(db: Session, *, cliente_id: int, antes_de: str) -> float:
    """Neto (facturas/ND suman, NC restan) de los comprobantes aprobados del
    cliente con fecha anterior a ``antes_de``."""
    total_firmado = func.sum(
        case(
            (Comprobante.tipo_cbte.in_(NOTAS_CREDITO), -Comprobante.importe_total),
            else_=Comprobante.importe_total,
        )
    )
    total = (
        db.query(total_firmado)
        .filter(
            Comprobante.cliente_id == cliente_id,
            Comprobante.cae.isnot(None),
            Comprobante.fecha < antes_de,
        )
        .scalar()
    )
    return round(float(total or 0), 2)


def calcular_estado_cuenta(
    db: Session, *, cliente: Cliente, fecha_inicio: str, fecha_fin: str
) -> EstadoCuenta:
    """Arma el estado de cuenta: saldo anterior + movimientos en
    ``[fecha_inicio, fecha_fin]`` (ambos inclusive) ordenados
    cronológicamente, con saldo acumulado corriente línea a línea."""
    saldo_anterior = _saldo_a_fecha(db, cliente_id=cliente.id, antes_de=fecha_inicio)

    comprobantes = (
        db.query(Comprobante)
        .options(joinedload(Comprobante.cliente), joinedload(Comprobante.empresa))
        .filter(
            Comprobante.cliente_id == cliente.id,
            Comprobante.cae.isnot(None),
            Comprobante.fecha >= fecha_inicio,
            Comprobante.fecha <= fecha_fin,
        )
        .order_by(Comprobante.fecha, Comprobante.punto_venta, Comprobante.numero)
        .all()
    )

    saldo = saldo_anterior
    movimientos: list[MovimientoCuenta] = []
    for c in comprobantes:
        importe = (
            -float(c.importe_total)
            if c.tipo_cbte in NOTAS_CREDITO
            else float(c.importe_total)
        )
        saldo = round(saldo + importe, 2)
        movimientos.append(
            MovimientoCuenta(comprobante=c, importe=round(importe, 2), saldo=saldo)
        )

    return EstadoCuenta(
        cliente=cliente,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        saldo_anterior=saldo_anterior,
        movimientos=movimientos,
        saldo_final=saldo,
    )
