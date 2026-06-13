"""Utilidades compartidas de la capa web: plantillas Jinja2 y mensajes flash."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.templating import Jinja2Templates

from app.config import settings

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))


def flash(request: Request, message: str, category: str = "info") -> None:
    """Agrega un mensaje flash a la sesión (se muestra en el próximo render)."""
    request.session.setdefault("_flashes", []).append(
        {"message": message, "category": category}
    )


def _pop_flashes(request: Request) -> list[dict[str, str]]:
    return request.session.pop("_flashes", [])


def render(
    request: Request,
    name: str,
    context: dict[str, Any] | None = None,
    user: Any = None,
    status_code: int = 200,
):
    """Renderiza una plantilla con el contexto común (usuario, flashes, modo)."""
    ctx: dict[str, Any] = {
        "flashes": _pop_flashes(request),
        "user": user,
        "modo_afip": settings.afip_modo,
        "is_produccion": settings.is_produccion,
    }
    if context:
        ctx.update(context)
    return templates.TemplateResponse(
        request=request, name=name, context=ctx, status_code=status_code
    )
