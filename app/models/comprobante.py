"""Modelo de comprobante emitido (factura / nota de crédito / nota de débito).

Guarda la cabecera, los totales y la respuesta de AFIP (CAE y vencimiento). Para
notas de crédito/débito, ``cbte_asociado_id`` referencia al comprobante original.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Comprobante(Base):
    __tablename__ = "comprobantes"

    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), index=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"))
    usuario_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id"), nullable=True
    )

    # Datos del comprobante en términos AFIP.
    tipo_cbte: Mapped[int] = mapped_column(Integer)   # 1=Fact A, 6=Fact B, 11=Fact C...
    punto_venta: Mapped[int] = mapped_column(Integer)
    numero: Mapped[int] = mapped_column(Integer)
    concepto: Mapped[int] = mapped_column(Integer, default=1)  # 1=Prod 2=Serv 3=Ambos
    fecha: Mapped[str] = mapped_column(String(10))  # "YYYY-MM-DD"

    # Importes.
    importe_neto: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    importe_iva: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    importe_total: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    moneda: Mapped[str] = mapped_column(String(3), default="PES")
    cotizacion: Mapped[float] = mapped_column(Numeric(14, 6), default=1)

    # Respuesta de AFIP.
    cae: Mapped[str | None] = mapped_column(String(20), nullable=True)
    cae_vencimiento: Mapped[str | None] = mapped_column(String(10), nullable=True)
    resultado: Mapped[str | None] = mapped_column(String(1), nullable=True)  # "A"/"R"

    # Para notas de crédito / débito: comprobante asociado.
    cbte_asociado_id: Mapped[int | None] = mapped_column(
        ForeignKey("comprobantes.id"), nullable=True
    )

    pdf_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    items: Mapped[list["ComprobanteItem"]] = relationship(
        back_populates="comprobante", cascade="all, delete-orphan"
    )
    cliente: Mapped["Cliente"] = relationship()
    empresa: Mapped["Empresa"] = relationship()

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Comprobante tipo={self.tipo_cbte} "
            f"{self.punto_venta:04d}-{self.numero:08d} CAE={self.cae}>"
        )
