"""Servicio de consulta al Padrón de AFIP (Constancia de Inscripción A5).

Orquesta la consulta de los datos de un contribuyente por CUIT, usando el
certificado de la empresa emisora para autenticar contra el servicio
``ws_sr_constancia_inscripcion``. El resultado precarga el alta de cliente.

El Ticket de Acceso de este servicio se cachea aparte (en ``.afip_cache/``), por
lo que no se reautentica en cada consulta.
"""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.afip.exceptions import AfipValidationError
from app.afip.padron_client import SERVICIO_PADRON, DatosPadron, consultar_constancia
from app.afip.wsaa_client import autenticar
from app.logging_config import get_logger
from app.models.empresa import Empresa

logger = get_logger("padron")


def _normalizar_cuit(cuit: str) -> str:
    """Deja solo los dígitos del CUIT y valida que sean 11."""
    solo_digitos = re.sub(r"\D", "", cuit or "")
    if len(solo_digitos) != 11:
        raise AfipValidationError(
            "El CUIT debe tener 11 dígitos para consultar el padrón de AFIP."
        )
    return solo_digitos


def consultar_cliente_afip(
    db: Session, *, empresa_id: int, cuit: str
) -> DatosPadron:
    """Consulta los datos de un cliente por CUIT en el Padrón de AFIP.

    Args:
        db: sesión de base de datos.
        empresa_id: empresa emisora cuyo certificado se usa para autenticar.
        cuit: CUIT del cliente a consultar.

    Returns:
        Un :class:`DatosPadron` con los datos oficiales del contribuyente.

    Raises:
        AfipValidationError: CUIT inválido o sin datos en AFIP.
        AfipConnectionError / AfipAuthError: problemas de conexión / autenticación.
    """
    cuit_norm = _normalizar_cuit(cuit)

    empresa = db.get(Empresa, empresa_id)
    if empresa is None:
        raise AfipValidationError(f"Empresa {empresa_id} inexistente.")

    # Autenticación específica para el servicio de padrón (TA cacheado aparte).
    ticket = autenticar(
        empresa.cuit,
        empresa.cert_path,
        empresa.key_path,
        servicio=SERVICIO_PADRON,
    )
    return consultar_constancia(ticket, cuit_norm)
