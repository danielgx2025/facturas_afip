"""Configuración central de la aplicación.

Lee las variables de entorno desde ``.env`` mediante ``pydantic-settings`` y
expone un objeto ``settings`` tipado, reutilizable en todo el proyecto.

Las URLs de los web services de AFIP se resuelven automáticamente según
``AFIP_MODO`` (homologación o producción), de modo que el resto del código nunca
las tiene que hardcodear.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Raíz del proyecto (carpeta que contiene "app/").
BASE_DIR = Path(__file__).resolve().parent.parent

# --- URLs oficiales de los web services de AFIP ---
# Homologación = entorno de pruebas SIN validez fiscal.
WSAA_URL_HOMO = "https://wsaahomo.afip.gov.ar/ws/services/LoginCms?wsdl"
WSAA_URL_PROD = "https://wsaa.afip.gov.ar/ws/services/LoginCms?wsdl"
WSFE_URL_HOMO = "https://wswhomo.afip.gov.ar/wsfev1/service.asmx?WSDL"
WSFE_URL_PROD = "https://servicios1.afip.gov.ar/wsfev1/service.asmx?WSDL"
# Padrón — Constancia de Inscripción Alcance 5 (servicio ws_sr_constancia_inscripcion).
PADRON_A5_URL_HOMO = "https://awshomo.afip.gov.ar/sr-padron/webservices/personaServiceA5?wsdl"
PADRON_A5_URL_PROD = "https://aws.afip.gov.ar/sr-padron/webservices/personaServiceA5?wsdl"


class Settings(BaseSettings):
    """Configuración de la aplicación cargada desde el entorno / ``.env``."""

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Base de datos MySQL ---
    db_host: str = "localhost"
    db_port: int = 3306
    db_user: str = "root"
    db_password: str = ""
    db_name: str = "facturas_afip"

    # --- Entorno AFIP ---
    afip_modo: str = Field(default="homologacion")  # "homologacion" | "produccion"
    afip_cache_dir: str = "./.afip_cache"

    # --- Seguridad web ---
    secret_key: str = "cambiar-en-produccion"
    session_max_age: int = 43200  # 12 horas

    # --- Rutas ---
    certs_dir: str = "./certs"
    pdfs_dir: str = "./pdfs"
    log_dir: str = "./logs"

    # --- Admin inicial (para init_db.py) ---
    admin_username: str = "admin"
    admin_email: str = "admin@example.com"
    admin_password: str = "admin"

    # ------------------------------------------------------------------
    # Propiedades derivadas
    # ------------------------------------------------------------------
    @property
    def is_produccion(self) -> bool:
        """True si el modo configurado es producción (validez fiscal real)."""
        return self.afip_modo.strip().lower() == "produccion"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str:
        """Cadena de conexión SQLAlchemy para MySQL vía PyMySQL."""
        return (
            f"mysql+pymysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}?charset=utf8mb4"
        )

    @property
    def wsaa_url(self) -> str:
        """WSDL del WSAA según el modo (homologación / producción)."""
        return WSAA_URL_PROD if self.is_produccion else WSAA_URL_HOMO

    @property
    def wsfe_url(self) -> str:
        """WSDL del WSFEv1 según el modo (homologación / producción)."""
        return WSFE_URL_PROD if self.is_produccion else WSFE_URL_HOMO

    @property
    def padron_url(self) -> str:
        """WSDL del Padrón A5 (Constancia de Inscripción) según el modo."""
        return PADRON_A5_URL_PROD if self.is_produccion else PADRON_A5_URL_HOMO

    # --- Rutas absolutas resueltas ---
    @property
    def certs_path(self) -> Path:
        return (BASE_DIR / self.certs_dir).resolve()

    @property
    def pdfs_path(self) -> Path:
        return (BASE_DIR / self.pdfs_dir).resolve()

    @property
    def log_path(self) -> Path:
        return (BASE_DIR / self.log_dir).resolve()

    @property
    def afip_cache_path(self) -> Path:
        return (BASE_DIR / self.afip_cache_dir).resolve()

    def ensure_directories(self) -> None:
        """Crea las carpetas de trabajo si no existen."""
        for path in (
            self.certs_path,
            self.pdfs_path,
            self.log_path,
            self.afip_cache_path,
        ):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Devuelve la configuración (cacheada como singleton)."""
    return Settings()


# Instancia global reutilizable.
settings = get_settings()
