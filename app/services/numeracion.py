"""Servicio de numeración de comprobantes.

Consulta a AFIP el último comprobante autorizado para un tipo y punto de venta,
y devuelve el siguiente número. La numeración la lleva AFIP (no la base local),
por lo que siempre se consulta en línea antes de emitir.
"""

from __future__ import annotations

from app.afip import wsfe_client
from app.afip.wsaa_client import autenticar
from app.models.empresa import Empresa


def siguiente_numero(empresa: Empresa, tipo_cbte: int, punto_venta: int) -> int:
    """Autentica y devuelve el próximo número para (tipo, punto de venta)."""
    ticket = autenticar(empresa.cuit, empresa.cert_path, empresa.key_path)
    return wsfe_client.proximo_numero(ticket, tipo_cbte, punto_venta)
