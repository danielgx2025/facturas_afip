"""Modelo de punto de venta (habilitado en AFIP por empresa)."""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PuntoVenta(Base):
    __tablename__ = "puntos_venta"
    __table_args__ = (
        UniqueConstraint("empresa_id", "numero", name="uq_empresa_punto_venta"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), index=True)
    numero: Mapped[int] = mapped_column(Integer)  # ej.: 1, 2, 3...
    descripcion: Mapped[str] = mapped_column(String(120), default="")
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    empresa: Mapped["Empresa"] = relationship(back_populates="puntos_venta")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<PuntoVenta {self.numero} (empresa={self.empresa_id})>"
