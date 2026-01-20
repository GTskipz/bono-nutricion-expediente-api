from fastapi import APIRouter, Depends
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
