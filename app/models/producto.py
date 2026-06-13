"""Modelo de producto / servicio facturable."""

from __future__ import annotations

from sqlalchemy import Boolean, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Producto(Base):
    __tablename__ = "productos"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    descripcion: Mapped[str] = mapped_column(String(255))
    # Precio unitario NETO (sin IVA).
    precio_unitario: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    # Alícuota de IVA en porcentaje (0, 10.5, 21, 27).
    alicuota_iva: Mapped[float] = mapped_column(Numeric(5, 2), default=21)
    unidad_medida: Mapped[str] = mapped_column(String(20), default="unidad")
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Producto {self.codigo} {self.descripcion}>"
