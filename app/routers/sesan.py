from fastapi import APIRouter, Depends, UploadFile, File, Form, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.services.sesan_service import SesanService

router = APIRouter(prefix="/sesan", tags=["SESAN"])


@router.post("/batch", status_code=201)
def crear_batch_sesan(
    db: Session = Depends(get_db),
    nombre_lote: str = Form(...),
    anio_carga: int = Form(...),
    mes_carga: int | None = Form(None),
    descripcion: str | None = Form(None),
    origen: str = Form("SESAN"),
    usuario_carga: str | None = Form(None),
    file: UploadFile = File(...),
):
    return SesanService(db).crear_batch(
        nombre_lote=nombre_lote,
        anio_carga=anio_carga,
        mes_carga=mes_carga,
        descripcion=descripcion,
        origen=origen,
        usuario_carga=usuario_carga,
        file=file,
    )


@router.get("/batches")
def listar_batches_por_anio(
    anio: int = Query(...),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return SesanService(db).listar_batches_por_anio(anio=anio, page=page, limit=limit)


@router.get("/anios")
def listar_anios_sesan(db: Session = Depends(get_db)):
    return SesanService(db).listar_anios()


@router.get("/batch/{batch_id}/rows")
def listar_filas_batch(
    batch_id: int,
    estado: str | None = Query(None, description="PENDIENTE | ERROR | PROCESADO | IGNORADO"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return SesanService(db).listar_filas_batch(
        batch_id=batch_id,
        estado=estado,
        page=page,
        limit=limit,
    )


@router.post("/batch/{batch_id}/procesar-pendientes")
def procesar_pendientes_batch(
    batch_id: int,
    limit: int = Query(200, ge=1, le=2000),
    db: Session = Depends(get_db),
):
    return SesanService(db).procesar_pendientes_batch(batch_id=batch_id, limit=limit)


@router.post("/row/{row_id}/procesar")
def procesar_row(
    row_id: int,
    db: Session = Depends(get_db),
):
    return SesanService(db).procesar_row(row_id=row_id)


@router.post("/batch/{batch_id}/reintentar-errores")
def reintentar_errores_batch(
    batch_id: int,
    limit: int = Query(2000, ge=1, le=50000),
    db: Session = Depends(get_db),
):
    return SesanService(db).reintentar_errores_batch(batch_id=batch_id, limit=limit)


@router.post("/row/{row_id}/reintentar")
def reintentar_row(
    row_id: int,
    db: Session = Depends(get_db),
):
    return SesanService(db).reintentar_row(row_id=row_id)


@router.post("/row/{row_id}/ignorar")
def ignorar_row(
    row_id: int,
    motivo: str = Form(...),
    usuario: str | None = Form(None),
    db: Session = Depends(get_db),
):
    return SesanService(db).ignorar_row(row_id=row_id, motivo=motivo, usuario=usuario)
