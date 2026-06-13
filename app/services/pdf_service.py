"""Generación del PDF del comprobante con el QR fiscal de AFIP.

El QR sigue la especificación de AFIP (RG 4892): un JSON con los datos del
comprobante, codificado en base64 y embebido en la URL
``https://www.afip.gob.ar/fe/qr/?p=<base64>``.
"""

from __future__ import annotations

import base64
import json
from io import BytesIO

import qrcode
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy.orm import Session

from app.afip.constants import LETRA_COMPROBANTE, TIPOS_COMPROBANTE
from app.config import settings
from app.logging_config import get_logger
from app.models.comprobante import Comprobante

logger = get_logger("pdf")

QR_BASE_URL = "https://www.afip.gob.ar/fe/qr/?p="


def _construir_qr_afip(comprobante: Comprobante) -> BytesIO:
    """Construye el QR fiscal de AFIP y lo devuelve como PNG en memoria."""
    empresa = comprobante.empresa
    cliente = comprobante.cliente

    datos = {
        "ver": 1,
        "fecha": comprobante.fecha,
        "cuit": int(empresa.cuit),
        "ptoVta": comprobante.punto_venta,
        "tipoCmp": comprobante.tipo_cbte,
        "nroCmp": comprobante.numero,
        "importe": float(comprobante.importe_total),
        "moneda": comprobante.moneda,
        "ctz": float(comprobante.cotizacion),
        "tipoDocRec": cliente.tipo_doc,
        "nroDocRec": int(cliente.nro_doc or 0),
        "tipoCodAut": "E",  # E = CAE
        "codAut": int(comprobante.cae) if comprobante.cae else 0,
    }
    json_str = json.dumps(datos, separators=(",", ":"))
    b64 = base64.b64encode(json_str.encode("utf-8")).decode("ascii")
    url = QR_BASE_URL + b64

    img = qrcode.make(url)
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


def _nombre_archivo(comprobante: Comprobante) -> str:
    letra = LETRA_COMPROBANTE.get(comprobante.tipo_cbte, "X")
    return (
        f"{comprobante.empresa.cuit}_{letra}"
        f"{comprobante.punto_venta:04d}-{comprobante.numero:08d}.pdf"
    )


def generar_pdf_comprobante(db: Session, comprobante: Comprobante) -> str:
    """Genera el PDF del comprobante y devuelve la ruta absoluta del archivo."""
    settings.ensure_directories()
    output_path = settings.pdfs_path / _nombre_archivo(comprobante)

    empresa = comprobante.empresa
    cliente = comprobante.cliente
    letra = LETRA_COMPROBANTE.get(comprobante.tipo_cbte, "X")
    tipo_nombre = TIPOS_COMPROBANTE.get(comprobante.tipo_cbte, "Comprobante")

    styles = getSampleStyleSheet()
    style_normal = styles["Normal"]
    style_small = styles["Normal"].clone("small")
    style_small.fontSize = 8
    style_title = styles["Title"]

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
    )
    elementos: list = []

    # --- Encabezado: emisor + recuadro de letra ---
    cabecera = Table(
        [
            [
                Paragraph(
                    f"<b>{empresa.razon_social}</b><br/>"
                    f"CUIT: {empresa.cuit}<br/>"
                    f"{empresa.domicilio}<br/>"
                    f"{empresa.condicion_iva}",
                    style_normal,
                ),
                Paragraph(f"<b>{letra}</b>", style_title),
                Paragraph(
                    f"<b>{tipo_nombre}</b><br/>"
                    f"N°: {comprobante.punto_venta:04d}-{comprobante.numero:08d}<br/>"
                    f"Fecha: {comprobante.fecha}",
                    style_normal,
                ),
            ]
        ],
        colWidths=[80 * mm, 20 * mm, 80 * mm],
    )
    cabecera.setStyle(
        TableStyle(
            [
                ("BOX", (1, 0), (1, 0), 1, colors.black),
                ("ALIGN", (1, 0), (1, 0), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    elementos.append(cabecera)
    elementos.append(Spacer(1, 6 * mm))

    # --- Datos del receptor ---
    elementos.append(
        Paragraph(
            f"<b>Cliente:</b> {cliente.razon_social} &nbsp;&nbsp; "
            f"<b>Doc:</b> {cliente.nro_doc} &nbsp;&nbsp; "
            f"<b>Cond. IVA:</b> {cliente.condicion_iva}",
            style_normal,
        )
    )
    if cliente.domicilio:
        elementos.append(Paragraph(f"<b>Domicilio:</b> {cliente.domicilio}", style_small))
    elementos.append(Spacer(1, 4 * mm))

    # --- Detalle de ítems ---
    filas = [["Descripción", "Cant.", "P. Unit.", "Alíc. IVA", "Subtotal"]]
    for item in comprobante.items:
        filas.append(
            [
                item.descripcion,
                f"{item.cantidad}",
                f"${item.precio_unitario}",
                f"{item.alicuota_iva}%",
                f"${item.subtotal}",
            ]
        )
    tabla = Table(filas, colWidths=[80 * mm, 20 * mm, 25 * mm, 20 * mm, 25 * mm])
    tabla.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#343a40")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("ALIGN", (0, 0), (0, -1), "LEFT"),
            ]
        )
    )
    elementos.append(tabla)
    elementos.append(Spacer(1, 4 * mm))

    # --- Totales (en facturas B no se discrimina IVA al cliente, pero lo mostramos) ---
    totales = Table(
        [
            ["Neto Gravado:", f"${comprobante.importe_neto}"],
            ["IVA:", f"${comprobante.importe_iva}"],
            ["TOTAL:", f"${comprobante.importe_total}"],
        ],
        colWidths=[40 * mm, 35 * mm],
        hAlign="RIGHT",
    )
    totales.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("FONTNAME", (0, 2), (-1, 2), "Helvetica-Bold"),
                ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
            ]
        )
    )
    elementos.append(totales)
    elementos.append(Spacer(1, 6 * mm))

    # --- QR fiscal + CAE ---
    qr_buffer = _construir_qr_afip(comprobante)
    qr_img = Image(qr_buffer, width=30 * mm, height=30 * mm)
    pie = Table(
        [
            [
                qr_img,
                Paragraph(
                    f"<b>CAE N°:</b> {comprobante.cae}<br/>"
                    f"<b>Vencimiento CAE:</b> {comprobante.cae_vencimiento}",
                    style_normal,
                ),
            ]
        ],
        colWidths=[35 * mm, 100 * mm],
    )
    pie.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    elementos.append(pie)

    if not settings.is_produccion:
        elementos.append(Spacer(1, 4 * mm))
        elementos.append(
            Paragraph(
                "<b>COMPROBANTE EMITIDO EN HOMOLOGACIÓN - SIN VALIDEZ FISCAL</b>",
                style_small,
            )
        )

    doc.build(elementos)
    logger.info("PDF generado: %s", output_path)
    return str(output_path)
