"""Cliente WSAA: autenticación digital con AFIP.

El WSAA (Web Service de Autenticación y Autorización) recibe el certificado y la
clave privada de la empresa y devuelve un **Ticket de Acceso (TA)** con un
``Token`` y un ``Sign`` que habilitan al resto de los web services (WSFEv1, etc.).

El TA tiene una validez de ~12 horas; por eso pyafipws lo **cachea en disco** y
lo reutiliza mientras siga vigente, evitando autenticar en cada factura.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pyafipws.wsaa import WSAA

from app.afip.exceptions import AfipAuthError, AfipConnectionError
from app.config import settings
from app.logging_config import get_logger

logger = get_logger("afip.wsaa")

# Servicio para el que se solicita el TA. Para facturación electrónica: "wsfe".
SERVICIO_WSFE = "wsfe"


@dataclass(frozen=True)
class TicketAcceso:
    """Resultado de la autenticación: Token + Sign para usar en WSFEv1."""

    token: str
    sign: str
    cuit: str


def _resolver_certificados(cert_rel: str, key_rel: str) -> tuple[Path, Path]:
    """Resuelve y valida las rutas del certificado y la clave de la empresa."""
    cert_path = settings.certs_path / cert_rel
    key_path = settings.certs_path / key_rel

    if not cert_path.is_file():
        raise AfipAuthError(
            f"No se encontró el certificado '{cert_path}'. "
            "Verificá que el archivo .crt exista en la carpeta certs/."
        )
    if not key_path.is_file():
        raise AfipAuthError(
            f"No se encontró la clave privada '{key_path}'. "
            "Verificá que el archivo .key exista en la carpeta certs/."
        )
    return cert_path, key_path


def autenticar(
    cuit: str,
    cert_rel: str,
    key_rel: str,
    servicio: str = SERVICIO_WSFE,
) -> TicketAcceso:
    """Obtiene un Ticket de Acceso (Token + Sign) de AFIP.

    Args:
        cuit: CUIT del emisor (solo dígitos).
        cert_rel: ruta del .crt relativa a ``certs/``.
        key_rel: ruta del .key relativa a ``certs/``.
        servicio: web service destino (por defecto ``"wsfe"``).

    Returns:
        Un :class:`TicketAcceso` con token y sign válidos.

    Raises:
        AfipAuthError: certificado/clave inválidos o relación no delegada.
        AfipConnectionError: no se pudo contactar al WSAA.
    """
    cert_path, key_path = _resolver_certificados(cert_rel, key_rel)
    settings.ensure_directories()

    # --- Inicialización del cliente pyafipws ---
    wsaa = WSAA()
    try:
        # Autenticar() arma el "Ticket de Requerimiento de Acceso" (TRA), lo
        # firma con la clave privada (CMS) y lo envía al WSAA. pyafipws cachea
        # el TA resultante en ``cache`` y lo reutiliza mientras siga vigente.
        ta_xml = wsaa.Autenticar(
            servicio,                       # servicio: "wsfe"
            str(cert_path),                 # ruta al certificado .crt
            str(key_path),                  # ruta a la clave privada .key
            wsdl=settings.wsaa_url,          # homologación o producción (config)
            cache=str(settings.afip_cache_path),
            debug=False,
        )
    except Exception as exc:  # pyafipws levanta excepciones genéricas
        logger.exception("Error de conexión con WSAA (CUIT %s).", cuit)
        raise AfipConnectionError(
            f"No se pudo conectar con el WSAA de AFIP: {exc}"
        ) from exc

    # pyafipws expone el detalle del fallo en .Excepcion / .Traceback.
    if not ta_xml or not wsaa.Token or not wsaa.Sign:
        detalle = getattr(wsaa, "Excepcion", "") or "respuesta vacía del WSAA"
        logger.error("Fallo de autenticación WSAA (CUIT %s): %s", cuit, detalle)
        raise AfipAuthError(
            "No se pudo autenticar con AFIP. Verificá que el certificado no esté "
            "vencido y que la relación esté delegada para el servicio 'wsfe'. "
            f"Detalle: {detalle}"
        )

    logger.info("Autenticación WSAA exitosa (CUIT %s, servicio %s).", cuit, servicio)
    return TicketAcceso(token=wsaa.Token, sign=wsaa.Sign, cuit=cuit)
