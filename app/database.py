"""Capa de acceso a datos: engine, sesión y base declarativa de SQLAlchemy."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

# ``pool_pre_ping`` evita errores por conexiones MySQL que el servidor cerró
# por inactividad (típico "MySQL server has gone away").
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    echo=False,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """Base declarativa común a todos los modelos ORM."""


def get_db() -> Generator[Session, None, None]:
    """Dependencia de FastAPI: provee una sesión y la cierra al finalizar."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
