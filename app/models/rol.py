"""Modelo de rol: permisos dinámicos por sección.

Reemplaza al antiguo Enum ``RolUsuario`` fijo. Cada rol guarda en ``permisos``
la lista de claves de sección que habilita (ver ``app.auth.permisos.PERMISOS``).
El rol marcado ``sistema=True`` (el ``admin`` sembrado) está protegido: no se
puede eliminar ni renombrar ni quitarle el permiso de gestión de usuarios.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.usuario import Usuario


class Rol(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    descripcion: Mapped[str] = mapped_column(String(255), default="")
    # Lista de claves de permiso (JSON). Al editar se reasigna la lista completa,
    # así SQLAlchemy detecta el cambio sin necesidad de MutableList.
    permisos: Mapped[list[str]] = mapped_column(JSON, default=list)
    # Rol protegido (no se borra/renombra ni pierde el permiso de usuarios).
    sistema: Mapped[bool] = mapped_column(Boolean, default=False)

    usuarios: Mapped[list["Usuario"]] = relationship(back_populates="rol")

    def tiene_permiso(self, permiso: str) -> bool:
        return permiso in (self.permisos or [])

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Rol {self.nombre} ({len(self.permisos or [])} permisos)>"
