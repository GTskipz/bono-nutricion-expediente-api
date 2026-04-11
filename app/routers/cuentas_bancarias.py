from io import BytesIO
from typing import Optional
from fastapi import APIRouter, Depends, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.db import get_db

from app.services.banco_archivo_service import descargar_archivo_operacion
from app.services.cuentas_bancarias_service import (
    bandeja_expedientes_por_estado_flujo,
    crear_lote_apertura,
    eliminar_lote_apertura_cuenta,
    listar_lotes_apertura,
    obtener_lote_apertura,
    listar_items_lote,
    procesar_lote_apertura_simulado,
    generar_excel_lote_export_bytes,
    procesar_respuesta_banco_excel,
    validar_excel_respuesta_banco,
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
    estado_flujo_id: int = Query(...),
    texto: Optional[str] = Query(None),
    departamento_id: Optional[int] = Query(None),
    municipio_id: Optional[int] = Query(None),
    page: int = Query(1),
    limit: int = Query(20),
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
        creado_por=None,
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
    page: int = Query(1),
    limit: int = Query(20),
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
# DETALLE LOTE
# ==========================================================
@router.get("/lotes/{lote_id}")
def obtener_lote(lote_id: int, db: Session = Depends(get_db)):
    return obtener_lote_apertura(db, lote_id=lote_id)


# ==========================================================
# ITEMS LOTE
# ==========================================================
@router.get("/lotes/{lote_id}/items")
def listar_items(
    lote_id: int,
    page: int = Query(1),
    limit: int = Query(50),
    db: Session = Depends(get_db),
):
    return listar_items_lote(
        db,
        lote_id=lote_id,
        page=page,
        limit=limit,
    )


# ==========================================================
# PROCESAR LOTE (LEGACY)
# ==========================================================
@router.post("/lotes/{lote_id}/procesar", response_model=LoteProcesarResponse)
def procesar_lote(lote_id: int, db: Session = Depends(get_db)):

    result = procesar_lote_apertura_simulado(db, lote_id=lote_id)

    return LoteProcesarResponse(**result)


# ==========================================================
# DESCARGAR EXCEL
# ==========================================================
@router.get("/lotes/{lote_id}/excel")
def descargar_excel_lote(lote_id: int, db: Session = Depends(get_db)):

    content = generar_excel_lote_export_bytes(db, lote_id=lote_id)

    filename = f"LOTE_APERTURA_EXPORT_{lote_id}.xlsx"

    return StreamingResponse(
        iter([content]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ==========================================================
# SUBIR RESPUESTA BANCO
# ==========================================================
@router.post("/lotes/{lote_id}/respuesta")
async def subir_respuesta_banco(
    lote_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):

    file_bytes = await file.read()

    # VALIDACIÓN DEL EXCEL
    validar_excel_respuesta_banco(file_bytes)

    # procesar lote
    return procesar_respuesta_banco_excel(
        db,
        lote_id=lote_id,
        file_bytes=file_bytes,
        filename=file.filename,  # 👈 necesario para guardar en MinIO
    )

@router.get("/lotes/{lote_id}/archivo-respuesta")
def descargar_respuesta_banco(
    lote_id: int,
    db: Session = Depends(get_db),
):

    result = descargar_archivo_operacion(
        db,
        lote_id=lote_id,
        tipo_archivo="RESPUESTA",
    )

    return StreamingResponse(
        BytesIO(result["data"]),
        media_type=result["mime_type"],
        headers={
            "Content-Disposition": f'attachment; filename="{result["filename"]}"'
        },
    )

@router.delete("/lotes/{lote_id}")
def eliminar_lote(
    lote_id: int,
    db: Session = Depends(get_db),
):
    return eliminar_lote_apertura_cuenta(
        db,
        lote_id=lote_id,
    )