"""Cliente WSFEv1: emisión de comprobantes electrónicos y solicitud de CAE.

Envuelve la clase ``WSFEv1`` de pyafipws con una interfaz tipada y un manejo de
errores homogéneo. Soporta facturas A/B/C y notas de crédito/débito (estas
últimas requieren informar el comprobante asociado).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pyafipws.wsfev1 import WSFEv1

from app.afip.constants import COMPROBANTES_CON_ASOCIADO
from app.afip.exceptions import AfipConnectionError, AfipValidationError
from app.afip.wsaa_client import TicketAcceso
from app.config import settings
from app.logging_config import get_logger

logger = get_logger("afip.wsfe")


@dataclass
class AlicuotaIva:
    """Una línea de IVA agrupada por alícuota."""

    iva_id: int       # id de AFIP (5=21%, 4=10.5%, 3=0%, 6=27%)
    base_imp: float   # base imponible (neto) de esa alícuota
    importe: float    # importe de IVA calculado


@dataclass
class CmpAsociado:
    """Comprobante asociado (obligatorio en notas de crédito/débito)."""

    tipo: int
    punto_venta: int
    numero: int
    cuit: str | None = None    # CUIT del emisor del comprobante asociado
    fecha: str | None = None   # "YYYY-MM-DD"


@dataclass
class SolicitudCAE:
    """Datos necesarios para solicitar un CAE a AFIP."""

    concepto: int
    tipo_doc: int
    nro_doc: str
    tipo_cbte: int
    punto_venta: int
    cbte_nro: int
    fecha: str               # "YYYY-MM-DD"
    imp_neto: float
    imp_iva: float
    imp_total: float
    ivas: list[AlicuotaIva] = field(default_factory=list)
    imp_tot_conc: float = 0.0   # no gravado
    imp_op_ex: float = 0.0      # exento
    imp_trib: float = 0.0       # otros tributos
    moneda_id: str = "PES"
    moneda_ctz: float = 1.0
    # Condición frente al IVA del receptor (RG 5616, obligatorio).
    condicion_iva_receptor_id: int | None = None
    asociados: list[CmpAsociado] = field(default_factory=list)
    # Solo conceptos 2 (servicios) y 3 (ambos) requieren estas fechas.
    fecha_serv_desde: str | None = None
    fecha_serv_hasta: str | None = None
    fecha_vto_pago: str | None = None


@dataclass
class ResultadoCAE:
    """Respuesta de AFIP a la solicitud de CAE."""

    resultado: str            # "A" (aprobado) | "R" (rechazado)
    cae: str
    vencimiento: str          # "YYYY-MM-DD"
    numero: int
    observaciones: list[str] = field(default_factory=list)
    reproceso: str = ""


def _fmt_fecha(fecha: str | None) -> str | None:
    """Convierte 'YYYY-MM-DD' al formato 'YYYYMMDD' que espera AFIP."""
    if not fecha:
        return None
    return fecha.replace("-", "")


def _conectar(ticket: TicketAcceso) -> WSFEv1:
    """Crea y conecta un cliente WSFEv1 autenticado con el Ticket de Acceso."""
    wsfe = WSFEv1()
    wsfe.Cuit = ticket.cuit
    wsfe.Token = ticket.token
    wsfe.Sign = ticket.sign
    try:
        conectado = wsfe.Conectar(
            cache=str(settings.afip_cache_path), wsdl=settings.wsfe_url
        )
    except Exception as exc:
        logger.exception("Error conectando a WSFEv1 (CUIT %s).", ticket.cuit)
        raise AfipConnectionError(
            f"No se pudo conectar con WSFEv1 de AFIP: {exc}"
        ) from exc

    if not conectado:
        raise AfipConnectionError("No se pudo establecer conexión con WSFEv1.")
    return wsfe


def proximo_numero(ticket: TicketAcceso, tipo_cbte: int, punto_venta: int) -> int:
    """Devuelve el próximo número de comprobante (último autorizado + 1)."""
    wsfe = _conectar(ticket)
    ultimo = wsfe.CompUltimoAutorizado(tipo_cbte, punto_venta)
    return int(ultimo or 0) + 1


def emitir_comprobante(
    ticket: TicketAcceso, solicitud: SolicitudCAE
) -> ResultadoCAE:
    """Arma el comprobante y solicita el CAE a AFIP.

    Raises:
        AfipValidationError: AFIP rechazó el comprobante (con detalle de errores).
        AfipConnectionError: problema de conexión durante la operación.
    """
    wsfe = _conectar(ticket)

    # --- Armado del comprobante ---
    wsfe.CrearFactura(
        concepto=solicitud.concepto,
        tipo_doc=solicitud.tipo_doc,
        nro_doc=solicitud.nro_doc,
        tipo_cbte=solicitud.tipo_cbte,
        punto_vta=solicitud.punto_venta,
        cbt_desde=solicitud.cbte_nro,
        cbt_hasta=solicitud.cbte_nro,
        imp_total=solicitud.imp_total,
        imp_tot_conc=solicitud.imp_tot_conc,
        imp_neto=solicitud.imp_neto,
        imp_iva=solicitud.imp_iva,
        imp_trib=solicitud.imp_trib,
        imp_op_ex=solicitud.imp_op_ex,
        fecha_cbte=_fmt_fecha(solicitud.fecha),
        fecha_venc_pago=_fmt_fecha(solicitud.fecha_vto_pago),
        fecha_serv_desde=_fmt_fecha(solicitud.fecha_serv_desde),
        fecha_serv_hasta=_fmt_fecha(solicitud.fecha_serv_hasta),
        moneda_id=solicitud.moneda_id,
        moneda_ctz=solicitud.moneda_ctz,
        condicion_iva_receptor_id=solicitud.condicion_iva_receptor_id,
    )

    # Detalle de IVA por alícuota. Las facturas C (Monotributo) no llevan IVA.
    for iva in solicitud.ivas:
        wsfe.AgregarIva(iva.iva_id, iva.base_imp, iva.importe)

    # Comprobantes asociados (obligatorio para notas de crédito/débito).
    if solicitud.tipo_cbte in COMPROBANTES_CON_ASOCIADO:
        if not solicitud.asociados:
            raise AfipValidationError(
                "Las notas de crédito/débito requieren un comprobante asociado."
            )
        for asoc in solicitud.asociados:
            wsfe.AgregarCmpAsoc(
                asoc.tipo,
                asoc.punto_venta,
                asoc.numero,
                cuit=asoc.cuit,
                fecha=_fmt_fecha(asoc.fecha),
            )

    # --- Solicitud del CAE ---
    try:
        wsfe.CAESolicitar()
    except Exception as exc:
        logger.exception(
            "Error solicitando CAE (CUIT %s, tipo %s).",
            ticket.cuit,
            solicitud.tipo_cbte,
        )
        raise AfipConnectionError(
            f"Error al solicitar el CAE: {exc}"
        ) from exc

    errores = list(getattr(wsfe, "Errores", []) or [])
    observaciones = list(getattr(wsfe, "Observaciones", []) or [])

    # AFIP devolvió errores explícitos.
    if errores:
        logger.error(
            "AFIP rechazó el comprobante (CUIT %s): %s", ticket.cuit, errores
        )
        raise AfipValidationError(
            "AFIP rechazó el comprobante.",
            errores=errores,
            observaciones=observaciones,
        )

    # Sin CAE o resultado rechazado.
    if wsfe.Resultado != "A" or not wsfe.CAE:
        logger.error(
            "Comprobante no aprobado (CUIT %s, resultado=%s): %s",
            ticket.cuit,
            wsfe.Resultado,
            observaciones,
        )
        raise AfipValidationError(
            "El comprobante no fue aprobado por AFIP.",
            errores=errores,
            observaciones=observaciones,
        )

    # Vencimiento del CAE: pyafipws lo devuelve como "YYYYMMDD".
    venc = wsfe.Vencimiento or ""
    if len(venc) == 8 and venc.isdigit():
        venc = f"{venc[0:4]}-{venc[4:6]}-{venc[6:8]}"

    logger.info(
        "CAE obtenido (CUIT %s, %s-%08d): %s",
        ticket.cuit,
        solicitud.punto_venta,
        solicitud.cbte_nro,
        wsfe.CAE,
    )
    return ResultadoCAE(
        resultado=wsfe.Resultado,
        cae=wsfe.CAE,
        vencimiento=venc,
        numero=solicitud.cbte_nro,
        observaciones=observaciones,
        reproceso=getattr(wsfe, "Reproceso", "") or "",
    )
