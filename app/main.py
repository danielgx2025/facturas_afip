"""Punto de entrada de la aplicación web (FastAPI).

Crea la app, configura logging, middleware de sesión, archivos estáticos,
plantillas Jinja2 y monta los routers. Ejecutar con:

    uvicorn app.main:app --reload
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.auth.dependencies import NotAuthenticatedError
from app.config import settings
from app.logging_config import setup_logging
from app.routers import auth, clientes, dashboard, empresas, facturas, productos

setup_logging()
settings.ensure_directories()

app = FastAPI(title="Sistema de Facturación Electrónica AFIP", version="1.0.0")

# Sesiones firmadas por cookie (login web).
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    max_age=settings.session_max_age,
    same_site="lax",
    https_only=settings.is_produccion,
)

# Archivos estáticos (CSS/JS/Bootstrap).
_STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

@app.exception_handler(NotAuthenticatedError)
async def not_authenticated_handler(
    request: Request, exc: NotAuthenticatedError
) -> RedirectResponse:
    """Sin sesión activa: redirige al formulario de login."""
    return RedirectResponse(url="/login", status_code=303)


# Routers de la aplicación.
app.include_router(auth.router)
app.include_router(empresas.router)
app.include_router(clientes.router)
app.include_router(productos.router)
app.include_router(facturas.router)
app.include_router(dashboard.router)


@app.get("/", include_in_schema=False)
def index(request: Request) -> RedirectResponse:
    """Redirige al panel si hay sesión, o al login en caso contrario."""
    if request.session.get("user_id"):
        return RedirectResponse(url="/facturas", status_code=303)
    return RedirectResponse(url="/login", status_code=303)


@app.get("/health", include_in_schema=False)
def health() -> dict[str, str]:
    """Endpoint simple de verificación de estado."""
    return {"status": "ok", "modo_afip": settings.afip_modo}
