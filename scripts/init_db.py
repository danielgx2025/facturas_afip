"""Inicializa la base de datos.

- Crea todas las tablas (si no existen).
- Crea el usuario administrador inicial (datos tomados del ``.env``).
- Crea una empresa emisora demo con un punto de venta, apuntando a los
  certificados de homologación ubicados en ``certs/``.

Uso:
    python scripts/init_db.py

Requisitos previos:
    - La base de datos MySQL indicada en ``.env`` debe existir. Crearla con:
        CREATE DATABASE facturas_afip CHARACTER SET utf8mb4;
"""

from __future__ import annotations

import sys
from pathlib import Path

# Permite ejecutar el script directamente (python scripts/init_db.py).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.auth.security import hash_password  # noqa: E402
from app.config import settings  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.logging_config import get_logger  # noqa: E402
from app.models import Empresa, PuntoVenta, RolUsuario, Usuario  # noqa: E402

# Importante: importar app.models (arriba) registra TODOS los modelos en
# Base.metadata antes de create_all.

logger = get_logger("init_db")


def crear_tablas() -> None:
    """Crea el esquema completo en la base de datos."""
    Base.metadata.create_all(bind=engine)
    logger.info("Tablas creadas/verificadas en '%s'.", settings.db_name)


def crear_admin() -> None:
    """Crea el usuario administrador si todavía no existe."""
    with SessionLocal() as db:
        existe = (
            db.query(Usuario)
            .filter(Usuario.username == settings.admin_username)
            .first()
        )
        if existe:
            logger.info("El usuario admin '%s' ya existe.", settings.admin_username)
            return
        admin = Usuario(
            username=settings.admin_username,
            email=settings.admin_email,
            hashed_password=hash_password(settings.admin_password),
            rol=RolUsuario.ADMIN,
            activo=True,
        )
        db.add(admin)
        db.commit()
        logger.info("Usuario admin '%s' creado.", settings.admin_username)


def crear_empresa_demo() -> None:
    """Crea una empresa emisora demo + punto de venta (homologación).

    NOTA: por defecto NO se llama desde main(). La empresa real se registra con
    sus certificados reales mediante scripts/preparar_certificado.py (a partir de
    un .p12) o desde la pantalla web de Empresas. Esta función queda disponible
    solo como referencia/seed manual con datos ficticios.
    """
    with SessionLocal() as db:
        if db.query(Empresa).first():
            logger.info("Ya existe al menos una empresa; no se crea la demo.")
            return
        empresa = Empresa(
            cuit="20111111112",  # <-- REEMPLAZAR por tu CUIT de homologación
            razon_social="Empresa Demo S.A.",
            domicilio="Calle Falsa 123 - CABA",
            condicion_iva="Responsable Inscripto",
            ingresos_brutos="",
            inicio_actividades="2020-01-01",
            cert_path="empresa_demo.crt",  # relativo a certs/
            key_path="empresa_demo.key",   # relativo a certs/
            modo="homologacion",
            activo=True,
        )
        empresa.puntos_venta.append(
            PuntoVenta(numero=1, descripcion="Punto de venta principal", activo=True)
        )
        db.add(empresa)
        db.commit()
        logger.info("Empresa demo creada (CUIT %s).", empresa.cuit)


def main() -> None:
    settings.ensure_directories()
    crear_tablas()
    crear_admin()
    # La empresa emisora se registra con scripts/preparar_certificado.py
    # (desde el .p12) o desde la web. No se crea una empresa demo ficticia.
    logger.info("Inicialización completada.")


if __name__ == "__main__":
    main()
