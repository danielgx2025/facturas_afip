"""Modelo de usuario del sistema web (login multiusuario con roles dinámicos)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.rol import Rol


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(120), unique=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    rol_id: Mapped[int] = mapped_column(ForeignKey("roles.id"))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    rol: Mapped["Rol"] = relationship(back_populates="usuarios")

    def puede(self, permiso: str) -> bool:
        """Indica si el rol del usuario habilita ``permiso``."""
        return self.rol is not None and permiso in (self.rol.permisos or [])

    def __repr__(self) -> str:  # pragma: no cover
        rol = self.rol.nombre if self.rol else "sin rol"
        return f"<Usuario {self.username} ({rol})>"
