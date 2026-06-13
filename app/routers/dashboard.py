"""Router del dashboard de facturación (gráficos por cliente, mensualizados)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.empresa import Empresa
from app.models.usuario import Usuario
from app.services.estadisticas import totales_por_cliente_mensual
from app.web import render

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("")
def index(
    request: Request,
    empresa_id: str = "",
    periodo: str = "anual",
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    """Dashboard: totales por cliente (torta) y por mes (barras apiladas).

    ``empresa_id`` llega como string porque el form GET envía el select vacío
    (``?empresa_id=``) y FastAPI no convierte "" a None en un int opcional.
    ``periodo`` es el período calendario en curso (mensual/trimestral/semestral/
    anual); el servicio cae a "anual" ante un valor no reconocido.
    """
    empresa_id_int = int(empresa_id) if empresa_id.strip().isdigit() else None

    datos = totales_por_cliente_mensual(db, empresa_id=empresa_id_int, periodo=periodo)
    empresas = db.query(Empresa).filter(Empresa.activo.is_(True)).all()
    return render(
        request,
        "dashboard/index.html",
        {
            "datos": datos,
            "empresas": empresas,
            "empresa_id": empresa_id_int,
            "periodo": periodo,
        },
        user=user,
    )
