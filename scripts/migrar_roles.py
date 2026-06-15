"""Migración one-off: de rol Enum fijo a roles dinámicos con permisos.

Convierte una base existente (con ``usuarios.rol`` como Enum string) al nuevo
esquema de roles dinámicos:

1. Crea la tabla ``roles`` (vía create_all; no toca columnas de ``usuarios``).
2. Siembra los roles base (admin/facturador) — reutiliza ``init_db.crear_roles_base``.
3. Agrega ``usuarios.rol_id`` si falta.
4. Backfilltea ``rol_id`` desde la columna vieja ``rol``.
5. Agrega la FK, vuelve ``rol_id`` NOT NULL y elimina la columna ``rol``.

Es **idempotente**: se puede correr varias veces sin efectos adversos. No es
necesario en bases nuevas (``init_db.py`` ya crea el esquema correcto).

Uso:
    python scripts/migrar_roles.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Permite importar tanto el paquete app como el módulo hermano init_db.
_RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_RAIZ))
sys.path.insert(0, str(_RAIZ / "scripts"))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import (  # noqa: E402
    InternalError,
    OperationalError,
    ProgrammingError,
)

from app.config import settings  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.logging_config import get_logger  # noqa: E402
from app.models import Rol  # noqa: E402
from init_db import crear_roles_base  # noqa: E402

logger = get_logger("migrar_roles")


def _columna_existe(conn, tabla: str, columna: str) -> bool:
    res = conn.execute(text(f"SHOW COLUMNS FROM {tabla} LIKE '{columna}'"))
    return res.first() is not None


def migrar() -> None:
    settings.ensure_directories()

    # 1) Tabla roles (create_all no agrega columnas a usuarios ya existente).
    Base.metadata.create_all(bind=engine)
    # 2) Roles base.
    crear_roles_base()

    with SessionLocal() as db:
        roles = {r.nombre: r.id for r in db.query(Rol).all()}
    admin_id = roles.get("admin")
    facturador_id = roles.get("facturador")
    if admin_id is None:
        logger.error("No se pudo crear/encontrar el rol 'admin'. Abortando.")
        return

    with engine.begin() as conn:
        tiene_rol_id = _columna_existe(conn, "usuarios", "rol_id")
        tiene_rol = _columna_existe(conn, "usuarios", "rol")

        # 3) Agregar rol_id si falta.
        if not tiene_rol_id:
            conn.execute(text("ALTER TABLE usuarios ADD COLUMN rol_id INT NULL"))
            logger.info("Columna usuarios.rol_id agregada.")

        # 4) Backfill desde la columna vieja 'rol'.
        if tiene_rol:
            conn.execute(
                text(
                    "UPDATE usuarios SET rol_id = :rid "
                    "WHERE rol = 'admin' AND rol_id IS NULL"
                ),
                {"rid": admin_id},
            )
            if facturador_id is not None:
                conn.execute(
                    text(
                        "UPDATE usuarios SET rol_id = :rid "
                        "WHERE rol = 'facturador' AND rol_id IS NULL"
                    ),
                    {"rid": facturador_id},
                )

        # Caso borde / seguridad: cualquier usuario sin rol queda como admin.
        conn.execute(
            text("UPDATE usuarios SET rol_id = :rid WHERE rol_id IS NULL"),
            {"rid": admin_id},
        )

    # 5) FK + NOT NULL + drop de la columna vieja (cada uno idempotente).
    with engine.begin() as conn:
        try:
            conn.execute(
                text(
                    "ALTER TABLE usuarios ADD CONSTRAINT fk_usuarios_rol "
                    "FOREIGN KEY (rol_id) REFERENCES roles(id)"
                )
            )
            logger.info("FK fk_usuarios_rol creada.")
        except (OperationalError, InternalError, ProgrammingError):
            logger.info("La FK fk_usuarios_rol ya existía; se omite.")

    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE usuarios MODIFY COLUMN rol_id INT NOT NULL"))
        if _columna_existe(conn, "usuarios", "rol"):
            conn.execute(text("ALTER TABLE usuarios DROP COLUMN rol"))
            logger.info("Columna vieja usuarios.rol eliminada.")

    logger.info("Migración de roles completada.")


if __name__ == "__main__":
    migrar()
