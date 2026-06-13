"""Modelo de ítem (línea de detalle) de un comprobante."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ComprobanteItem(Base):
    __tablename__ = "comprobante_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    comprobante_id: Mapped[int] = mapped_column(
        ForeignKey("comprobantes.id"), index=True
    )
    producto_id: Mapped[int | None] = mapped_column(
        ForeignKey("productos.id"), nullable=True
    )

    descripcion: Mapped[str] = mapped_column(String(255))
    cantidad: Mapped[float] = mapped_column(Numeric(14, 2), default=1)
    precio_unitario: Mapped[float] = mapped_column(Numeric(14, 2), default=0)  # neto
    alicuota_iva: Mapped[float] = mapped_column(Numeric(5, 2), default=21)
    subtotal: Mapped[float] = mapped_column(Numeric(14, 2), default=0)  # neto (cant*pu)

    comprobante: Mapped["Comprobante"] = relationship(back_populates="items")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Item {self.descripcion} x{self.cantidad}>"
