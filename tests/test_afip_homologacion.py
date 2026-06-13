"""Prueba de humo contra el entorno de HOMOLOGACIÓN de AFIP.

Verifica que se pueda autenticar (WSAA) y consultar el último comprobante
autorizado (WSFEv1). Requiere:
    - pyafipws instalado,
    - una empresa cargada con certificados válidos de homologación,
    - AFIP_MODO=homologacion.

Se marca como "skip" automáticamente si no hay empresa o certificados, para no
romper la suite en entornos sin credenciales.

Ejecutar con:  pytest -s tests/test_afip_homologacion.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.afip import wsfe_client  # noqa: E402
from app.afip.constants import FACTURA_B  # noqa: E402
from app.afip.wsaa_client import autenticar  # noqa: E402
from app.config import settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models.empresa import Empresa  # noqa: E402


def _empresa_con_certificados() -> Empresa | None:
    with SessionLocal() as db:
        for empresa in db.query(Empresa).filter(Empresa.activo.is_(True)).all():
            cert = settings.certs_path / empresa.cert_path
            key = settings.certs_path / empresa.key_path
            if cert.is_file() and key.is_file():
                db.expunge(empresa)
                return empresa
    return None


def test_autenticar_y_ultimo_autorizado():
    if settings.is_produccion:
        pytest.skip("La prueba de humo solo corre en homologación.")

    empresa = _empresa_con_certificados()
    if empresa is None:
        pytest.skip("No hay empresa con certificados disponibles para la prueba.")

    ticket = autenticar(empresa.cuit, empresa.cert_path, empresa.key_path)
    assert ticket.token and ticket.sign

    numero = wsfe_client.proximo_numero(ticket, FACTURA_B, punto_venta=1)
    assert numero >= 1
