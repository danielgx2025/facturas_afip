"""Modelo de usuario del sistema web (login multiusuario con roles)."""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RolUsuario(str, enum.Enum):
    """Roles disponibles en el sistema."""

    ADMIN = "admin"          # gestiona empresas, certificados y usuarios
    FACTURADOR = "facturador"  # emite y consulta comprobantes


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(120), unique=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    rol: Mapped[RolUsuario] = mapped_column(
        Enum(RolUsuario), default=RolUsuario.FACTURADOR
    )
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Usuario {self.username} ({self.rol.value})>"
