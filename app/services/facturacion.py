"""Servicio de facturación: orquesta la emisión de un comprobante.

Flujo:
    1. Toma empresa, cliente y líneas (productos) desde la base de datos.
    2. Calcula neto, IVA (agrupado por alícuota) y total.
    3. Autentica contra AFIP (WSAA, con TA cacheado) y obtiene el próximo número.
    4. Solicita el CAE (WSFEv1).
    5. Si AFIP aprueba, persiste el comprobante con su CAE y genera el PDF.

Si AFIP rechaza o hay error de conexión, se propaga la excepción correspondiente
(``AfipValidationError`` / ``AfipConnectionError`` / ``AfipAuthError``) y NO se
persiste un comprobante inválido.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.afip import wsfe_client
from app.afip.constants import (
    COMPROBANTES_CON_ASOCIADO,
    FACTURAS,
    LETRA_COMPROBANTE,
    condicion_iva_receptor_id,
    iva_id_desde_porcentaje,
)
from app.afip.exceptions import AfipError
from app.afip.wsaa_client import autenticar
from app.afip.wsfe_client import AlicuotaIva, CmpAsociado, SolicitudCAE
from app.logging_config import get_logger
from app.models.cliente import Cliente
from app.models.comprobante import Comprobante
from app.models.comprobante_item import ComprobanteItem
from app.models.empresa import Empresa

logger = get_logger("facturacion")


@dataclass
class LineaFactura:
    """Una línea de la factura a emitir."""

    descripcion: str
    cantidad: float
    precio_unitario: float      # neto, sin IVA
    alicuota_iva: float = 21.0  # porcentaje
    producto_id: int | None = None


def _redondear(valor: float) -> float:
    return round(float(valor), 2)


def _es_factura_c(tipo_cbte: int) -> bool:
    """True si el comprobante es letra C (Monotributo: no discrimina IVA)."""
    return LETRA_COMPROBANTE.get(tipo_cbte) == "C"


def _calcular_totales(
    lineas: list[LineaFactura], tipo_cbte: int
) -> tuple[float, float, float, list[AlicuotaIva]]:
    """Calcula neto, IVA total, total y el detalle de IVA por alícuota."""
    neto_total = 0.0
    # Agrupa base imponible por alícuota.
    base_por_alicuota: dict[float, float] = defaultdict(float)

    for linea in lineas:
        subtotal = _redondear(linea.cantidad * linea.precio_unitario)
        neto_total += subtotal
        base_por_alicuota[float(linea.alicuota_iva)] += subtotal

    neto_total = _redondear(neto_total)

    # Las facturas C no discriminan IVA.
    if _es_factura_c(tipo_cbte):
        return neto_total, 0.0, neto_total, []

    ivas: list[AlicuotaIva] = []
    iva_total = 0.0
    for alicuota, base in base_por_alicuota.items():
        importe = _redondear(base * alicuota / 100.0)
        iva_total += importe
        ivas.append(
            AlicuotaIva(
                iva_id=iva_id_desde_porcentaje(alicuota),
                base_imp=_redondear(base),
                importe=importe,
            )
        )

    iva_total = _redondear(iva_total)
    total = _redondear(neto_total + iva_total)
    return neto_total, iva_total, total, ivas


def emitir_factura(
    db: Session,
    *,
    empresa_id: int,
    cliente_id: int,
    tipo_cbte: int,
    punto_venta: int,
    lineas: list[LineaFactura],
    concepto: int = 1,
    usuario_id: int | None = None,
    cbte_asociado_id: int | None = None,
    generar_pdf: bool = True,
) -> Comprobante:
    """Emite un comprobante electrónico y lo persiste con su CAE.

    Raises:
        ValueError: datos inconsistentes (empresa/cliente inexistente, sin líneas).
        AfipError (y subclases): fallos de autenticación, validación o conexión.
    """
    if not lineas:
        raise ValueError("El comprobante debe tener al menos una línea.")

    empresa = db.get(Empresa, empresa_id)
    if empresa is None:
        raise ValueError(f"Empresa {empresa_id} inexistente.")
    cliente = db.get(Cliente, cliente_id)
    if cliente is None:
        raise ValueError(f"Cliente {cliente_id} inexistente.")
    if cliente.fecha_baja is not None:
        raise ValueError(
            f"El cliente '{cliente.razon_social}' está dado de baja; "
            "no se le pueden emitir comprobantes."
        )

    neto, iva, total, ivas = _calcular_totales(lineas, tipo_cbte)

    # Comprobante asociado (notas de crédito/débito).
    asociados: list[CmpAsociado] = []
    if cbte_asociado_id is not None:
        if tipo_cbte not in COMPROBANTES_CON_ASOCIADO:
            raise ValueError(
                "Solo las notas de crédito/débito llevan comprobante asociado."
            )
        asociado = db.get(Comprobante, cbte_asociado_id)
        if asociado is None:
            raise ValueError(f"Comprobante asociado {cbte_asociado_id} inexistente.")
        if asociado.tipo_cbte not in FACTURAS:
            raise ValueError("El comprobante asociado debe ser una factura.")
        if asociado.cliente_id != cliente_id:
            raise ValueError("El comprobante asociado pertenece a otro cliente.")
        asociados.append(
            CmpAsociado(
                tipo=asociado.tipo_cbte,
                punto_venta=asociado.punto_venta,
                numero=asociado.numero,
                cuit=asociado.empresa.cuit,
                fecha=asociado.fecha,
            )
        )

    fecha_hoy = date.today().isoformat()

    # 1) Autenticación (TA cacheado).
    ticket = autenticar(empresa.cuit, empresa.cert_path, empresa.key_path)

    # 2) Próximo número que asigna AFIP.
    numero = wsfe_client.proximo_numero(ticket, tipo_cbte, punto_venta)

    # 3) Armado de la solicitud y pedido de CAE.
    solicitud = SolicitudCAE(
        concepto=concepto,
        tipo_doc=cliente.tipo_doc,
        nro_doc=str(cliente.nro_doc),
        tipo_cbte=tipo_cbte,
        punto_venta=punto_venta,
        cbte_nro=numero,
        fecha=fecha_hoy,
        imp_neto=neto,
        imp_iva=iva,
        imp_total=total,
        ivas=ivas,
        condicion_iva_receptor_id=condicion_iva_receptor_id(cliente.condicion_iva),
        asociados=asociados,
        # Para conceptos de servicios (2) o ambos (3), AFIP exige fechas de servicio.
        fecha_serv_desde=fecha_hoy if concepto in (2, 3) else None,
        fecha_serv_hasta=fecha_hoy if concepto in (2, 3) else None,
        fecha_vto_pago=fecha_hoy if concepto in (2, 3) else None,
    )

    try:
        resultado = wsfe_client.emitir_comprobante(ticket, solicitud)
    except AfipError:
        logger.exception(
            "Fallo al emitir comprobante (empresa=%s, cliente=%s, tipo=%s).",
            empresa_id,
            cliente_id,
            tipo_cbte,
        )
        raise

    # 4) Persistencia del comprobante aprobado.
    comprobante = Comprobante(
        empresa_id=empresa_id,
        cliente_id=cliente_id,
        usuario_id=usuario_id,
        tipo_cbte=tipo_cbte,
        punto_venta=punto_venta,
        numero=resultado.numero,
        concepto=concepto,
        fecha=fecha_hoy,
        importe_neto=neto,
        importe_iva=iva,
        importe_total=total,
        moneda="PES",
        cotizacion=1,
        cae=resultado.cae,
        cae_vencimiento=resultado.vencimiento,
        resultado=resultado.resultado,
        cbte_asociado_id=cbte_asociado_id,
    )
    for linea in lineas:
        comprobante.items.append(
            ComprobanteItem(
                producto_id=linea.producto_id,
                descripcion=linea.descripcion,
                cantidad=linea.cantidad,
                precio_unitario=linea.precio_unitario,
                alicuota_iva=linea.alicuota_iva,
                subtotal=_redondear(linea.cantidad * linea.precio_unitario),
            )
        )
    db.add(comprobante)
    db.commit()
    db.refresh(comprobante)

    # 5) Generación del PDF (con QR fiscal). Si falla, el comprobante ya es válido.
    if generar_pdf:
        try:
            from app.services.pdf_service import generar_pdf_comprobante

            pdf_path = generar_pdf_comprobante(db, comprobante)
            comprobante.pdf_path = pdf_path
            db.commit()
        except Exception:  # el PDF es secundario; no invalida el CAE
            logger.exception(
                "El comprobante %s obtuvo CAE pero falló la generación del PDF.",
                comprobante.id,
            )

    return comprobante
