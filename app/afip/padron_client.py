"""Cliente Padrón A5: Constancia de Inscripción (servicio ws_sr_constancia_inscripcion).

Envuelve la clase ``WSSrPadronA5`` de pyafipws con una interfaz tipada y un manejo
de errores homogéneo (misma jerarquía que el resto de la capa AFIP). Permite
consultar los datos oficiales de un contribuyente por CUIT para precargar el alta
de cliente: denominación, condición frente al IVA, domicilio y estado.

Requiere un Ticket de Acceso obtenido para el servicio
``ws_sr_constancia_inscripcion`` (NO ``wsfe``); el certificado de la empresa debe
estar delegado para ese servicio en el "Administrador de Relaciones" de AFIP.
"""

from __future__ import annotations

import configparser
from dataclasses import dataclass, field

# Shim de compatibilidad: ws_sr_padron de pyafipws importa ``SafeConfigParser``,
# que fue removido de configparser en Python 3.12+ (era un alias de ConfigParser).
# Hay que restituirlo ANTES de importar el módulo, igual que el shim de distutils.
if not hasattr(configparser, "SafeConfigParser"):
    configparser.SafeConfigParser = configparser.ConfigParser  # type: ignore[attr-defined]

from pyafipws.ws_sr_padron import SoapFault, WSSrPadronA5  # noqa: E402  (tras el shim)

from app.afip.constants import condicion_iva_receptor_texto
from app.afip.exceptions import AfipConnectionError, AfipValidationError
from app.afip.wsaa_client import TicketAcceso
from app.config import settings
from app.logging_config import get_logger

logger = get_logger("afip.padron")

# Servicio de AFIP para el que se solicita el TA (Constancia de Inscripción A5).
SERVICIO_PADRON = "ws_sr_constancia_inscripcion"


@dataclass
class DatosPadron:
    """Datos del contribuyente devueltos por la Constancia de Inscripción."""

    cuit: str
    denominacion: str           # razón social o "apellido, nombre"
    tipo_persona: str           # "FISICA" | "JURIDICA"
    estado: str                 # típicamente "ACTIVO"
    condicion_iva_id: int       # id de AFIP (1=RI, 4=Exento, 5=CF, 6=MT)
    condicion_iva_texto: str    # texto para el cliente (coincide con el <select>)
    domicilio: str              # domicilio fiscal armado
    direccion: str = ""
    localidad: str = ""
    provincia: str = ""
    cod_postal: str = ""
    actividades: list = field(default_factory=list)
    impuestos: list = field(default_factory=list)


def _conectar(ticket: TicketAcceso) -> WSSrPadronA5:
    """Crea y conecta un cliente Padrón A5 autenticado con el Ticket de Acceso."""
    ws = WSSrPadronA5()
    ws.Cuit = ticket.cuit          # CUIT representada (emisor que consulta)
    ws.Token = ticket.token
    ws.Sign = ticket.sign
    try:
        conectado = ws.Conectar(
            cache=str(settings.afip_cache_path), wsdl=settings.padron_url
        )
    except Exception as exc:
        logger.exception("Error conectando al Padrón A5 (CUIT %s).", ticket.cuit)
        raise AfipConnectionError(
            f"No se pudo conectar con el Padrón de AFIP: {exc}"
        ) from exc

    if not conectado:
        raise AfipConnectionError("No se pudo establecer conexión con el Padrón de AFIP.")
    return ws


def _fault_a_error(cuit: str, faultstring: str) -> AfipValidationError:
    """Traduce una falla SOAP de negocio del Padrón a un error de validación.

    El caso más común es "No existe persona con ese Id": el CUIT no figura en el
    padrón (en homologación, por ser una base de prueba). Es un "no encontrado",
    no un problema de conexión.
    """
    if "no existe persona" in faultstring.lower():
        mensaje = f"No se encontraron datos para el CUIT {cuit} en el padrón de AFIP."
        if not settings.is_produccion:
            mensaje += (
                " (En homologación el padrón sólo tiene CUIT de prueba; "
                "los CUIT reales suelen dar este mensaje.)"
            )
        return AfipValidationError(mensaje, errores=[faultstring])
    # Otra falla de negocio devuelta por AFIP: se muestra tal cual.
    return AfipValidationError(faultstring, errores=[faultstring])


def consultar_constancia(ticket: TicketAcceso, cuit: str) -> DatosPadron:
    """Consulta la Constancia de Inscripción de un CUIT y devuelve sus datos.

    Args:
        ticket: Ticket de Acceso para el servicio ``ws_sr_constancia_inscripcion``.
        cuit: CUIT a consultar (solo dígitos).

    Returns:
        Un :class:`DatosPadron` con los datos oficiales del contribuyente.

    Raises:
        AfipValidationError: el CUIT no existe o AFIP devolvió errores.
        AfipConnectionError: problema de conexión durante la consulta.
    """
    ws = _conectar(ticket)

    try:
        ok = ws.Consultar(cuit)
    except SoapFault as exc:
        # Falla de negocio devuelta por AFIP (ej.: persona inexistente). NO es un
        # problema de conexión: se reclasifica como validación / no encontrado.
        msg = str(getattr(exc, "faultstring", "") or exc)
        logger.warning("Padrón rechazó la consulta (CUIT %s): %s", cuit, msg)
        raise _fault_a_error(cuit, msg) from exc
    except Exception as exc:
        logger.exception("Error consultando el Padrón A5 (CUIT %s).", cuit)
        raise AfipConnectionError(
            f"Error al consultar el Padrón de AFIP: {exc}"
        ) from exc

    errores = list(getattr(ws, "errores", []) or [])
    excepcion = getattr(ws, "Excepcion", "") or ""

    # AFIP no encontró el contribuyente o devolvió errores de la constancia.
    if not ok or errores or excepcion:
        detalle = excepcion or "; ".join(
            er.get("error", str(er)) if isinstance(er, dict) else str(er)
            for er in errores
        )
        logger.warning("Padrón sin datos para CUIT %s: %s", cuit, detalle)
        raise AfipValidationError(
            f"AFIP no devolvió datos para el CUIT {cuit}. {detalle}".strip(),
            errores=[detalle] if detalle else [],
        )

    cat_iva = getattr(ws, "cat_iva", "")
    datos = DatosPadron(
        cuit=str(getattr(ws, "cuit", "") or cuit),
        denominacion=getattr(ws, "denominacion", "") or "",
        tipo_persona=getattr(ws, "tipo_persona", "") or "",
        estado=getattr(ws, "estado", "") or "",
        condicion_iva_id=int(cat_iva) if str(cat_iva).isdigit() else 0,
        condicion_iva_texto=condicion_iva_receptor_texto(cat_iva),
        domicilio=getattr(ws, "domicilio", "") or "",
        direccion=getattr(ws, "direccion", "") or "",
        localidad=getattr(ws, "localidad", "") or "",
        provincia=getattr(ws, "provincia", "") or "",
        cod_postal=str(getattr(ws, "cod_postal", "") or ""),
        actividades=list(getattr(ws, "actividades", []) or []),
        impuestos=list(getattr(ws, "impuestos", []) or []),
    )
    logger.info(
        "Padrón consultado (CUIT %s): %s, %s, %s.",
        cuit,
        datos.denominacion,
        datos.estado,
        datos.condicion_iva_texto,
    )
    return datos
