"""Configuración centralizada de logging.

Registra los eventos en consola y en un archivo rotativo ``logs/afip.log``.
La capa de integración con AFIP usa el logger ``"afip"`` para dejar trazas de
autenticaciones, emisiones, errores y observaciones devueltas por el organismo.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from app.config import settings

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_configured = False


def setup_logging(level: int = logging.INFO) -> None:
    """Configura los handlers de logging (idempotente)."""
    global _configured
    if _configured:
        return

    settings.ensure_directories()
    log_file = settings.log_path / "afip.log"

    formatter = logging.Formatter(_LOG_FORMAT)

    # Archivo rotativo: 5 archivos de 2 MB.
    file_handler = RotatingFileHandler(
        log_file, maxBytes=2 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    _configured = True


def get_logger(name: str = "afip") -> logging.Logger:
    """Devuelve un logger ya configurado."""
    setup_logging()
    return logging.getLogger(name)
