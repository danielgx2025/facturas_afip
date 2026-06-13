"""Modelo de cliente / receptor del comprobante."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Cliente(Base):
    __tablename__ = "clientes"

    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), index=True)
    razon_social: Mapped[str] = mapped_column(String(255))

    # Tipo de documento según AFIP (80=CUIT, 86=CUIL, 96=DNI, 99=Consumidor Final).
    tipo_doc: Mapped[int] = mapped_column(Integer, default=99)
    nro_doc: Mapped[str] = mapped_column(String(20), default="0")

    # Condición frente al IVA del RECEPTOR (texto para el PDF; AFIP lo pide en
    # RG 5616 vía "condicion_iva_receptor_id" en WSFEv1 reciente).
    condicion_iva: Mapped[str] = mapped_column(String(50), default="Consumidor Final")
    domicilio: Mapped[str] = mapped_column(String(255), default="")
    email: Mapped[str] = mapped_column(String(120), default="")

    # Baja lógica: NULL = activo; con fecha = dado de baja en esa fecha.
    fecha_baja: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, default=None
    )

    @property
    def activo(self) -> bool:
        return self.fecha_baja is None

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Cliente {self.razon_social} ({self.nro_doc})>"
