"""Script de ejemplo: emite una Factura B básica contra AFIP.

Pensado para validar de punta a punta la cadena (WSAA -> WSFEv1 -> CAE -> PDF)
contra el entorno de HOMOLOGACIÓN antes de tocar la capa web.

Uso:
    python scripts/emitir_factura_ejemplo.py

Requisitos previos:
    1. Haber corrido scripts/init_db.py (crea la empresa demo).
    2. Tener en certs/ los archivos .crt y .key de la empresa, y AFIP_MODO=homologacion.
    3. La relación 'wsfe' debe estar delegada al CUIT en el portal de AFIP.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Permite ejecutar el script directamente.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.afip.constants import (  # noqa: E402
    DOC_CONSUMIDOR_FINAL,
    FACTURA_B,
)
from app.afip.exceptions import (  # noqa: E402
    AfipAuthError,
    AfipConnectionError,
    AfipValidationError,
)
from app.config import settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models.cliente import Cliente  # noqa: E402
from app.models.empresa import Empresa  # noqa: E402
from app.models.punto_venta import PuntoVenta  # noqa: E402
from app.services.facturacion import LineaFactura, emitir_factura  # noqa: E402


def _obtener_cliente_consumidor_final(db, empresa_id: int) -> Cliente:
    """Devuelve (o crea) un cliente 'Consumidor Final' para la demo."""
    cliente = (
        db.query(Cliente)
        .filter(
            Cliente.empresa_id == empresa_id,
            Cliente.tipo_doc == DOC_CONSUMIDOR_FINAL,
        )
        .first()
    )
    if cliente is None:
        cliente = Cliente(
            empresa_id=empresa_id,
            razon_social="Consumidor Final",
            tipo_doc=DOC_CONSUMIDOR_FINAL,
            nro_doc="0",
            condicion_iva="Consumidor Final",
        )
        db.add(cliente)
        db.commit()
        db.refresh(cliente)
    return cliente


def main() -> int:
    print(f"== Emisión de Factura B de ejemplo (modo: {settings.afip_modo}) ==\n")

    with SessionLocal() as db:
        empresa = db.query(Empresa).filter(Empresa.activo.is_(True)).first()
        if empresa is None:
            print("ERROR: no hay empresas cargadas. Corré primero scripts/init_db.py.")
            return 1

        punto = (
            db.query(PuntoVenta)
            .filter(PuntoVenta.empresa_id == empresa.id, PuntoVenta.activo.is_(True))
            .first()
        )
        if punto is None:
            print("ERROR: la empresa no tiene punto de venta configurado.")
            return 1

        cliente = _obtener_cliente_consumidor_final(db, empresa.id)

        # Detalle de la factura: dos líneas con IVA 21 %.
        lineas = [
            LineaFactura(
                descripcion="Servicio de desarrollo de software",
                cantidad=1,
                precio_unitario=10000.00,
                alicuota_iva=21.0,
            ),
            LineaFactura(
                descripcion="Soporte técnico mensual",
                cantidad=2,
                precio_unitario=2500.00,
                alicuota_iva=21.0,
            ),
        ]

        print(f"Emisor : {empresa.razon_social} (CUIT {empresa.cuit})")
        print(f"Receptor: {cliente.razon_social}")
        print(f"Punto de venta: {punto.numero}\n")

        try:
            comprobante = emitir_factura(
                db,
                empresa_id=empresa.id,
                cliente_id=cliente.id,
                tipo_cbte=FACTURA_B,
                punto_venta=punto.numero,
                lineas=lineas,
                concepto=1,  # productos/servicios
            )
        except AfipAuthError as exc:
            print(f"\n[AUTENTICACIÓN] {exc}")
            return 2
        except AfipValidationError as exc:
            print(f"\n[VALIDACIÓN AFIP] {exc}")
            for e in exc.errores:
                print(f"  - error: {e}")
            for o in exc.observaciones:
                print(f"  - obs.: {o}")
            return 3
        except AfipConnectionError as exc:
            print(f"\n[CONEXIÓN] {exc}")
            return 4

    # --- Resultado ---
    print("\n¡Comprobante emitido con éxito!")
    print(f"  Tipo/Número : B {comprobante.punto_venta:04d}-{comprobante.numero:08d}")
    print(f"  Neto        : ${comprobante.importe_neto}")
    print(f"  IVA         : ${comprobante.importe_iva}")
    print(f"  Total       : ${comprobante.importe_total}")
    print(f"  CAE         : {comprobante.cae}")
    print(f"  Vencimiento : {comprobante.cae_vencimiento}")
    if comprobante.pdf_path:
        print(f"  PDF         : {comprobante.pdf_path}")
    print("\n(Recordá: en homologación el comprobante NO tiene validez fiscal.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
