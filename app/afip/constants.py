"""Constantes y catálogos de AFIP (códigos legibles).

Centraliza los códigos numéricos que usan los web services para no tener
"números mágicos" desperdigados por el código.
"""

from __future__ import annotations

# --- Tipos de comprobante (WSFEv1) ---
# A = entre Responsables Inscriptos | B = a Consumidor Final / Exento
# C = emisor Monotributo / Exento
FACTURA_A = 1
NOTA_DEBITO_A = 2
NOTA_CREDITO_A = 3
FACTURA_B = 6
NOTA_DEBITO_B = 7
NOTA_CREDITO_B = 8
FACTURA_C = 11
NOTA_DEBITO_C = 12
NOTA_CREDITO_C = 13

TIPOS_COMPROBANTE: dict[int, str] = {
    FACTURA_A: "Factura A",
    NOTA_DEBITO_A: "Nota de Débito A",
    NOTA_CREDITO_A: "Nota de Crédito A",
    FACTURA_B: "Factura B",
    NOTA_DEBITO_B: "Nota de Débito B",
    NOTA_CREDITO_B: "Nota de Crédito B",
    FACTURA_C: "Factura C",
    NOTA_DEBITO_C: "Nota de Débito C",
    NOTA_CREDITO_C: "Nota de Crédito C",
}

# Facturas (pueden ser el comprobante asociado de una NC/ND).
FACTURAS = {FACTURA_A, FACTURA_B, FACTURA_C}

# Notas de crédito y débito (requieren comprobante asociado).
NOTAS_CREDITO = {NOTA_CREDITO_A, NOTA_CREDITO_B, NOTA_CREDITO_C}
NOTAS_DEBITO = {NOTA_DEBITO_A, NOTA_DEBITO_B, NOTA_DEBITO_C}
COMPROBANTES_CON_ASOCIADO = NOTAS_CREDITO | NOTAS_DEBITO

# Letra del comprobante (para el PDF / QR).
LETRA_COMPROBANTE: dict[int, str] = {
    FACTURA_A: "A", NOTA_DEBITO_A: "A", NOTA_CREDITO_A: "A",
    FACTURA_B: "B", NOTA_DEBITO_B: "B", NOTA_CREDITO_B: "B",
    FACTURA_C: "C", NOTA_DEBITO_C: "C", NOTA_CREDITO_C: "C",
}

# --- Conceptos ---
CONCEPTO_PRODUCTOS = 1
CONCEPTO_SERVICIOS = 2
CONCEPTO_PRODUCTOS_Y_SERVICIOS = 3

# --- Tipos de documento del receptor ---
DOC_CUIT = 80
DOC_CUIL = 86
DOC_DNI = 96
DOC_CONSUMIDOR_FINAL = 99

# --- Alícuotas de IVA: id de AFIP -> porcentaje ---
IVA_0 = 3
IVA_10_5 = 4
IVA_21 = 5
IVA_27 = 6

ALICUOTA_IVA_ID: dict[float, int] = {
    0.0: IVA_0,
    10.5: IVA_10_5,
    21.0: IVA_21,
    27.0: IVA_27,
}

# --- Condición frente al IVA del receptor (RG 5616, obligatorio) ---
# IDs del web service (método FEParamGetCondicionIvaReceptor).
COND_IVA_RECEPTOR_RI = 1            # Responsable Inscripto
COND_IVA_RECEPTOR_EXENTO = 4       # Sujeto Exento
COND_IVA_RECEPTOR_CF = 5           # Consumidor Final
COND_IVA_RECEPTOR_MONOTRIBUTO = 6  # Responsable Monotributo
COND_IVA_RECEPTOR_NO_CATEGORIZADO = 7

# Mapea el texto guardado en el cliente al id de AFIP.
CONDICION_IVA_RECEPTOR: dict[str, int] = {
    "responsable inscripto": COND_IVA_RECEPTOR_RI,
    "exento": COND_IVA_RECEPTOR_EXENTO,
    "consumidor final": COND_IVA_RECEPTOR_CF,
    "monotributo": COND_IVA_RECEPTOR_MONOTRIBUTO,
    "no categorizado": COND_IVA_RECEPTOR_NO_CATEGORIZADO,
}

# Mapeo inverso (id de AFIP -> texto). El texto debe coincidir con las opciones
# del <select> de condición IVA en el alta de cliente. Lo usa la consulta al
# Padrón para traducir el `cat_iva` que devuelve AFIP a la condición del cliente.
CONDICION_IVA_RECEPTOR_TEXTO: dict[int, str] = {
    COND_IVA_RECEPTOR_RI: "Responsable Inscripto",
    COND_IVA_RECEPTOR_EXENTO: "Exento",
    COND_IVA_RECEPTOR_CF: "Consumidor Final",
    COND_IVA_RECEPTOR_MONOTRIBUTO: "Monotributo",
}

# --- Moneda ---
MONEDA_PESOS = "PES"
MONEDA_DOLAR = "DOL"


def iva_id_desde_porcentaje(porcentaje: float) -> int:
    """Traduce un porcentaje de IVA (ej. 21.0) al id que espera AFIP."""
    try:
        return ALICUOTA_IVA_ID[round(float(porcentaje), 1)]
    except KeyError as exc:  # pragma: no cover
        raise ValueError(f"Alícuota de IVA no soportada: {porcentaje}") from exc


def condicion_iva_receptor_id(texto: str | None) -> int:
    """Traduce la condición de IVA del cliente (texto) al id de AFIP (RG 5616).

    Si no se reconoce, asume Consumidor Final (5), que es el caso más común.
    """
    return CONDICION_IVA_RECEPTOR.get(
        (texto or "").strip().lower(), COND_IVA_RECEPTOR_CF
    )


def condicion_iva_receptor_texto(cat_iva: int | str | None) -> str:
    """Traduce el id de condición de IVA de AFIP (``cat_iva``) al texto del cliente.

    Acepta int o str (pyafipws a veces devuelve el id como texto). Si no se
    reconoce, asume "Consumidor Final".
    """
    try:
        clave = int(cat_iva)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "Consumidor Final"
    return CONDICION_IVA_RECEPTOR_TEXTO.get(clave, "Consumidor Final")
