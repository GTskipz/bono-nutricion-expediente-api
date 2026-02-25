from typing import Optional
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.db import get_db

from app.services.pagos_service import (
    bandeja_expedientes_con_cuenta,
    crear_lote_pago,
    listar_lotes_pago,
    obtener_lote_pago,
    listar_items_lote_pago,
    procesar_lote_pago_simulado,
    generar_excel_lote_pago_export_bytes,
)

from app.schemas.pagos import (
    LotePagoCrearRequest,
    LotePagoCrearResponse,
    LotePagoProcesarResponse,
)

router = APIRouter(prefix="/pagos", tags=["Pagos"])


@router.get("/bandeja")
def bandeja(
    estado_flujo_codigo: str = Query("CUENTA_BANCARIA_CREADA"),
    texto: Optional[str] = Query(None),
    departamento_id: Optional[int] = Query(None),
    municipio_id: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return bandeja_expedientes_con_cuenta(
        db,
        estado_flujo_codigo=estado_flujo_codigo,
        texto=texto,
        departamento_id=departamento_id,
        municipio_id=municipio_id,
        page=page,
        limit=limit,
    )


@router.post("/lotes", response_model=LotePagoCrearResponse)
def crear_lote(payload: LotePagoCrearRequest, db: Session = Depends(get_db)):
    lote_id, total = crear_lote_pago(
        db,
        expediente_ids=payload.expediente_ids,
        anio_fiscal=payload.anio_fiscal,
        mes_fiscal=payload.mes_fiscal,
        monto_por_persona=payload.monto_por_persona,
        tope_anual_persona=payload.tope_anual_persona,
        creado_por=None,  # luego con Keycloak
        observacion=payload.observacion,
    )
    return LotePagoCrearResponse(lote_id=lote_id, total=total)


@router.get("/lotes")
def listar_lotes(
    anio: Optional[int] = Query(None),
    mes: Optional[int] = Query(None, ge=1, le=12),
    estado: Optional[str] = Query(None),
    texto: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return listar_lotes_pago(
        db,
        anio=anio,
        mes=mes,
        estado=estado,
        texto=texto,
        page=page,
        limit=limit,
    )


@router.get("/lotes/{lote_id}")
def obtener_lote(lote_id: int, db: Session = Depends(get_db)):
    return obtener_lote_pago(db, lote_id=lote_id)


@router.get("/lotes/{lote_id}/items")
def listar_items(
    lote_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return listar_items_lote_pago(db, lote_id=lote_id, page=page, limit=limit)


@router.post("/lotes/{lote_id}/procesar", response_model=LotePagoProcesarResponse)
def procesar_lote(lote_id: int, db: Session = Depends(get_db)):
    result = procesar_lote_pago_simulado(db, lote_id=lote_id)
    return LotePagoProcesarResponse(**result)


@router.get("/lotes/{lote_id}/excel")
def descargar_excel_export(lote_id: int, db: Session = Depends(get_db)):
    content = generar_excel_lote_pago_export_bytes(db, lote_id=lote_id)

    filename = f"PAGOS_export_lote_{lote_id}.xlsx"
    return StreamingResponse(
        iter([content]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )