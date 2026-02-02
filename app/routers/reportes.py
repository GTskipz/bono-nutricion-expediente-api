from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.auth import require_auth_context
from app.services.reportes_service import ReportesService

router = APIRouter(prefix="/reportes", tags=["Reportes"])


@router.get("/expedientes/por-departamento")
def get_expedientes_por_departamento(
    db: Session = Depends(get_db),
    _auth = Depends(require_auth_context),
):
    svc = ReportesService(db)
    return svc.expedientes_totales_por_departamento()

@router.get("/expedientes/listado")
def get_expedientes_listado(
    departamento_id: int = Query(..., description="Departamento residencia (info_general.departamento_residencia_id)"),
    texto: str = Query("", description="Buscar por nombre/cui/rub"),
    estado_flujo_codigo: str | None = Query(None, description="Filtro opcional por estado_flujo_codigo"),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    _auth = Depends(require_auth_context),
):
    svc = ReportesService(db)
    return svc.expedientes_listado_por_departamento(
        departamento_id=departamento_id,
        texto=texto,
        estado_flujo_codigo=estado_flujo_codigo,
        page=page,
        limit=limit,
    )
