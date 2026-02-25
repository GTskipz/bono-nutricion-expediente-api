from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.services.bandejas_service import buscar_expedientes_por_estado_flujo

router = APIRouter(prefix="/expedientes/bandejas", tags=["Bandejas"])


@router.get("")
def bandeja_generica(
    # ✅ Uno de estos dos es obligatorio
    estado_flujo_id: Optional[int] = Query(None, description="ID del estado de flujo (ej: 4)"),
    estado_flujo_codigo: Optional[str] = Query(None, description='Código (ej: "DOCS_VERIFICADOS")'),

    # filtros
    texto: Optional[str] = Query(None),
    departamento_id: Optional[int] = Query(None),
    municipio_id: Optional[int] = Query(None),

    # paging
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return buscar_expedientes_por_estado_flujo(
        db,
        estado_flujo_id=estado_flujo_id,
        estado_flujo_codigo=estado_flujo_codigo,
        texto=texto,
        departamento_id=departamento_id,
        municipio_id=municipio_id,
        page=page,
        limit=limit,
    )
