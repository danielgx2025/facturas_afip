"""Prepara un certificado AFIP a partir de un archivo .p12 (PKCS#12).

Un archivo ``.p12`` empaqueta el certificado y la clave privada juntos (a veces
con contraseña). pyafipws necesita ambos por separado en formato PEM
(``.crt`` y ``.key``). Este script los extrae usando la librería ``cryptography``
(no requiere ``openssl`` instalado) y registra/actualiza la empresa emisora.

Uso:
    python scripts/preparar_certificado.py --p12 "ruta\\daniel.p12"
    python scripts/preparar_certificado.py --p12 "..." --password CLAVE --razon-social "Mi Empresa"
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Permite ejecutar el script directamente.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.serialization import pkcs12  # noqa: E402
from cryptography.x509.oid import NameOID  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.logging_config import get_logger  # noqa: E402
from app.models import Empresa, PuntoVenta  # noqa: E402

logger = get_logger("preparar_certificado")

DEFAULT_P12 = r"E:\AFIP\CertificadosLombardich\Certificados_Homo\daniel.p12"


def _subject_attr(cert, oid) -> str:
    """Devuelve el primer valor del atributo del subject, o cadena vacía."""
    valores = cert.subject.get_attributes_for_oid(oid)
    return valores[0].value if valores else ""


def _extraer_cuit(cert) -> str:
    """Obtiene el CUIT (11 dígitos) desde el subject del certificado."""
    # AFIP lo coloca en serialNumber como "CUIT 20XXXXXXXXX".
    serial = _subject_attr(cert, NameOID.SERIAL_NUMBER)
    cn = _subject_attr(cert, NameOID.COMMON_NAME)
    for fuente in (serial, cn):
        match = re.search(r"(\d{11})", fuente or "")
        if match:
            return match.group(1)
    raise ValueError(
        "No se pudo determinar el CUIT desde el certificado "
        f"(serialNumber='{serial}', CN='{cn}'). Pasá el CUIT manualmente."
    )


def _razon_social(cert) -> str:
    """Razón social tomada del subject (organización o CN)."""
    return (
        _subject_attr(cert, NameOID.ORGANIZATION_NAME)
        or _subject_attr(cert, NameOID.COMMON_NAME)
        or "Empresa Homologacion"
    )


def extraer_pem(p12_path: Path, password: str | None) -> tuple[str, str, str]:
    """Extrae cert+clave del .p12 a PEM y registra/actualiza la empresa.

    Returns:
        (cuit, razon_social, ruta_carpeta_certs)
    """
    datos = p12_path.read_bytes()
    pwd_bytes = password.encode("utf-8") if password else None
    clave, certificado, _ = pkcs12.load_key_and_certificates(datos, pwd_bytes)

    if certificado is None or clave is None:
        raise ValueError("El .p12 no contiene certificado y/o clave privada.")

    cuit = _extraer_cuit(certificado)
    razon = _razon_social(certificado)

    settings.ensure_directories()
    cert_rel = f"{cuit}.crt"
    key_rel = f"{cuit}.key"
    cert_out = settings.certs_path / cert_rel
    key_out = settings.certs_path / key_rel

    # Certificado público en PEM.
    cert_out.write_bytes(certificado.public_bytes(serialization.Encoding.PEM))
    # Clave privada en PEM sin cifrar (formato clásico de AFIP).
    key_out.write_bytes(
        clave.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    logger.info("Certificado extraído: %s", cert_out)
    logger.info("Clave privada extraída: %s", key_out)

    return cuit, razon, cert_rel, key_rel


def registrar_empresa(
    cuit: str, razon: str, cert_rel: str, key_rel: str
) -> None:
    """Crea o actualiza la empresa emisora con sus certificados."""
    Base.metadata.create_all(bind=engine)  # por si las tablas aún no existen
    with SessionLocal() as db:
        empresa = db.query(Empresa).filter(Empresa.cuit == cuit).first()
        if empresa is None:
            empresa = Empresa(
                cuit=cuit,
                razon_social=razon,
                condicion_iva="Responsable Inscripto",
                cert_path=cert_rel,
                key_path=key_rel,
                modo=settings.afip_modo,
                activo=True,
            )
            empresa.puntos_venta.append(
                PuntoVenta(numero=1, descripcion="Principal", activo=True)
            )
            db.add(empresa)
            accion = "creada"
        else:
            empresa.cert_path = cert_rel
            empresa.key_path = key_rel
            empresa.modo = settings.afip_modo
            empresa.activo = True
            if not empresa.puntos_venta:
                empresa.puntos_venta.append(
                    PuntoVenta(numero=1, descripcion="Principal", activo=True)
                )
            accion = "actualizada"
        db.commit()
        logger.info("Empresa %s %s (CUIT %s).", razon, accion, cuit)


def main() -> int:
    parser = argparse.ArgumentParser(description="Extrae cert/clave de un .p12 AFIP.")
    parser.add_argument("--p12", default=DEFAULT_P12, help="Ruta al archivo .p12")
    parser.add_argument("--password", default=None, help="Contraseña del .p12 (si tiene)")
    parser.add_argument(
        "--razon-social", default=None, help="Sobrescribe la razón social del cert"
    )
    args = parser.parse_args()

    p12_path = Path(args.p12)
    if not p12_path.is_file():
        print(f"ERROR: no se encontró el archivo .p12 en '{p12_path}'.")
        return 1

    try:
        cuit, razon, cert_rel, key_rel = extraer_pem(p12_path, args.password)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR al procesar el .p12: {exc}")
        return 2

    if args.razon_social:
        razon = args.razon_social

    registrar_empresa(cuit, razon, cert_rel, key_rel)

    print("\nCertificado preparado correctamente:")
    print(f"  CUIT          : {cuit}")
    print(f"  Razón social  : {razon}")
    print(f"  Certificado   : {settings.certs_path / cert_rel}")
    print(f"  Clave privada : {settings.certs_path / key_rel}")
    print("\nEmpresa registrada/actualizada en la base. Ya podés emitir comprobantes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
