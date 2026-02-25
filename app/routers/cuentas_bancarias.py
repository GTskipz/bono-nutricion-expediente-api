from typing import Optional
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.db import get_db

from app.services.cuentas_bancarias_service import (
    bandeja_expedientes_por_estado_flujo,
    crear_lote_apertura,
    listar_lotes_apertura,
    obtener_lote_apertura,
    listar_items_lote,
    procesar_lote_apertura_simulado,
    generar_excel_lote_export_bytes,
)

from app.schemas.cuentas_bancarias import (
    LoteCrearRequest,
    LoteCrearResponse,
    LoteProcesarResponse,
)

router = APIRouter(prefix="/cuentas", tags=["Cuentas Bancarias"])


# ==========================================================
# BANDEJA EXPEDIENTES
# ==========================================================
@router.get("/bandeja")
def bandeja(
    estado_flujo_id: int = Query(..., description="Ej: 4 (DOCS_VERIFICADOS)"),
    texto: Optional[str] = Query(None),
    departamento_id: Optional[int] = Query(None),
    municipio_id: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return bandeja_expedientes_por_estado_flujo(
        db,
        estado_flujo_id=estado_flujo_id,
        texto=texto,
        departamento_id=departamento_id,
        municipio_id=municipio_id,
        page=page,
        limit=limit,
    )


# ==========================================================
# CREAR LOTE
# ==========================================================
@router.post("/lotes", response_model=LoteCrearResponse)
def crear_lote(payload: LoteCrearRequest, db: Session = Depends(get_db)):
    lote_id, total = crear_lote_apertura(
        db,
        expediente_ids=payload.expediente_ids,
        creado_por=None,  # luego conectar con Keycloak
        observacion=payload.observacion,
        proveedor_servicio=payload.proveedor_servicio,
    )
    return LoteCrearResponse(lote_id=lote_id, total=total)


# ==========================================================
# LISTAR LOTES
# ==========================================================
@router.get("/lotes")
def listar_lotes(
    anio: Optional[int] = Query(None),
    estado: Optional[str] = Query(None),
    texto: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return listar_lotes_apertura(
        db,
        anio=anio,
        estado=estado,
        texto=texto,
        page=page,
        limit=limit,
    )


# ==========================================================
# OBTENER DETALLE DE LOTE (RESUMEN)
# ==========================================================
@router.get("/lotes/{lote_id}")
def obtener_lote(lote_id: int, db: Session = Depends(get_db)):
    return obtener_lote_apertura(db, lote_id=lote_id)


# ==========================================================
# LISTAR ITEMS DE UN LOTE
# ==========================================================
@router.get("/lotes/{lote_id}/items")
def listar_items(
    lote_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return listar_items_lote(
        db,
        lote_id=lote_id,
        page=page,
        limit=limit,
    )


# ==========================================================
# PROCESAR LOTE (SIMULADO)
# ==========================================================
@router.post("/lotes/{lote_id}/procesar", response_model=LoteProcesarResponse)
def procesar_lote(lote_id: int, db: Session = Depends(get_db)):
    result = procesar_lote_apertura_simulado(db, lote_id=lote_id)
    return LoteProcesarResponse(**result)


# ==========================================================
# DESCARGAR EXCEL EXPORT DEL LOTE
# ==========================================================
@router.get("/lotes/{lote_id}/excel")
def descargar_excel_lote(lote_id: int, db: Session = Depends(get_db)):
    content = generar_excel_lote_export_bytes(db, lote_id=lote_id)

    filename = f"LOTE_APERTURA_EXPORT_{lote_id}.xlsx"

    return StreamingResponse(
        iter([content]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        },
    )