"""Modelo de empresa emisora (multiempresa: varios CUIT).

Cada empresa apunta a su par de certificados ``.crt`` / ``.key``. En la base solo
se guarda la RUTA al archivo; los certificados viven fuera del control de
versiones (carpeta ``certs/``), nunca dentro de la base de datos.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Empresa(Base):
    __tablename__ = "empresas"

    id: Mapped[int] = mapped_column(primary_key=True)
    cuit: Mapped[str] = mapped_column(String(11), unique=True, index=True)
    razon_social: Mapped[str] = mapped_column(String(255))
    domicilio: Mapped[str] = mapped_column(String(255), default="")
    # Condición frente al IVA del EMISOR (ej.: "Responsable Inscripto", "Monotributo").
    condicion_iva: Mapped[str] = mapped_column(String(50), default="Responsable Inscripto")
    ingresos_brutos: Mapped[str] = mapped_column(String(50), default="")
    inicio_actividades: Mapped[str] = mapped_column(String(10), default="")

    # Rutas (relativas a certs/) a los certificados de la empresa.
    cert_path: Mapped[str] = mapped_column(String(255))
    key_path: Mapped[str] = mapped_column(String(255))

    # "homologacion" | "produccion" (a nivel empresa; el modo global está en .env).
    modo: Mapped[str] = mapped_column(String(20), default="homologacion")
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    puntos_venta: Mapped[list["PuntoVenta"]] = relationship(
        back_populates="empresa", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Empresa {self.razon_social} (CUIT {self.cuit})>"
