from __future__ import annotations

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Response,
    UploadFile,
    File,
    Form,
)
from sqlalchemy.orm import Session

from app.core.db import get_db

from app.schemas.expediente import (
    ExpedienteCreate,
    ExpedienteOut,
    ExpedienteSearchRequest,
    ExpedienteSearchResponse,
    ExpedienteTitularIn
)
from app.schemas.tracking_evento import TrackingCreate, TrackingOut

from app.services.expedientes_service import (
    crear_expediente_core,
    obtener_expediente,
    obtener_expediente_detalle,
    buscar_expedientes,
    listar_documentos_expediente,
    validar_tab,
    upload_documento_por_id_core,
    upload_documento_por_tipo_core,
    crear_tracking_evento_core,
    listar_tracking_expediente_core,
    set_expediente_bpm_minimo_core,
    actualizar_titular_y_estado_flujo,
    confirmar_documentos_cargados,
    pasar_a_docs_verificados
)

from app.services.documentos.carta_aceptacion import generar_carta_aceptacion_docx_bytes
from app.utils.docx_to_pdf import docx_bytes_to_pdf_bytes

router = APIRouter(prefix="/expedientes", tags=["Expedientes"])


@router.post("", response_model=ExpedienteOut, status_code=201)
def crear_expediente_endpoint(payload: ExpedienteCreate, db: Session = Depends(get_db)):
    try:
        return crear_expediente_core(payload, db)
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error creando expediente: {str(e)}")


@router.get("/{expediente_id}", response_model=ExpedienteOut)
def obtener_expediente_endpoint(expediente_id: int, db: Session = Depends(get_db)):
    return obtener_expediente(db, expediente_id)


@router.post("/search", response_model=ExpedienteSearchResponse)
def buscar_expedientes_endpoint(payload: ExpedienteSearchRequest, db: Session = Depends(get_db)):
    return buscar_expedientes(db, payload)


@router.post("/bandeja", response_model=ExpedienteSearchResponse)
def bandeja_asignados(payload: ExpedienteSearchRequest, db: Session = Depends(get_db)):
    payload.traer_todos = True
    return buscar_expedientes(db, payload)


@router.get("/{expediente_id}/detalle", response_model=ExpedienteOut)
def obtener_expediente_detalle_endpoint(expediente_id: int, db: Session = Depends(get_db)):
    return obtener_expediente_detalle(db, expediente_id)


@router.get("/{expediente_id}/documentos")
def listar_documentos_expediente_endpoint(
    expediente_id: int,
    tab: str = Query("DOCUMENTOS", description="DOCUMENTOS | ANEXOS"),
    db: Session = Depends(get_db),
):
    # validar_tab ya lo aplica el service, pero lo dejamos explícito si quieres:
    tab = validar_tab(tab)
    return listar_documentos_expediente(db, expediente_id, tab)


@router.post("/{expediente_id}/documentos/{documento_id}/upload")
async def upload_documento_por_id(
    expediente_id: int,
    documento_id: int,
    file: UploadFile = File(...),
    observacion: str | None = Form(None),
    descripcion: str | None = Form(None),
    db: Session = Depends(get_db),
):
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="Archivo inválido.")

    content = await file.read()
    return upload_documento_por_id_core(
        db=db,
        expediente_id=expediente_id,
        documento_id=documento_id,
        filename=file.filename,
        content_type=file.content_type or "application/octet-stream",
        content=content,
        observacion=observacion,
        descripcion=descripcion,
    )


@router.post("/{expediente_id}/documentos/upload")
async def upload_documento_por_tipo(
    expediente_id: int,
    file: UploadFile = File(...),
    tab: str = Form("DOCUMENTOS"),
    tipo_documento_id: int = Form(...),
    observacion: str | None = Form(None),
    descripcion: str | None = Form(None),
    db: Session = Depends(get_db),
):
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="Archivo inválido.")

    content = await file.read()
    return upload_documento_por_tipo_core(
        db=db,
        expediente_id=expediente_id,
        tab=tab,
        tipo_documento_id=tipo_documento_id,
        filename=file.filename,
        content_type=file.content_type or "application/octet-stream",
        content=content,
        observacion=observacion,
        descripcion=descripcion,
    )


@router.post("/{expediente_id}/tracking", response_model=TrackingOut, status_code=201)
def crear_tracking_evento(
    expediente_id: int,
    payload: TrackingCreate,
    db: Session = Depends(get_db),
):
    return crear_tracking_evento_core(db, expediente_id, payload)


@router.get("/{expediente_id}/tracking", response_model=list[TrackingOut])
def listar_tracking_expediente(
    expediente_id: int,
    db: Session = Depends(get_db),
):
    return listar_tracking_expediente_core(db, expediente_id)


@router.get("/{expediente_id}/documentos/carta-aceptacion.docx")
def descargar_carta_docx(expediente_id: int, db: Session = Depends(get_db)):
    try:
        content, filename = generar_carta_aceptacion_docx_bytes(expediente_id, db)
        return Response(
            content=content,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{expediente_id}/documentos/carta-aceptacion.pdf")
def descargar_carta_pdf(expediente_id: int, db: Session = Depends(get_db)):
    try:
        docx_bytes, docx_name = generar_carta_aceptacion_docx_bytes(expediente_id, db)
        pdf_bytes = docx_bytes_to_pdf_bytes(docx_bytes)
        pdf_name = docx_name.replace(".docx", ".pdf")

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{pdf_name}"'},
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.post("/{expediente_id}/titular")
def registrar_titular(
    expediente_id: int,
    payload: ExpedienteTitularIn,
    db: Session = Depends(get_db),
):
    try:
        row = actualizar_titular_y_estado_flujo(
            db,
            expediente_id=expediente_id,
            titular_nombre=payload.titular_nombre,
            titular_dpi=payload.titular_dpi,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not row:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")

    return row

@router.post("/{expediente_id}/documentos/confirmar")
def confirmar_docs(expediente_id: int, db: Session = Depends(get_db)):
    try:
        row = confirmar_documentos_cargados(db, expediente_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not row:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")

    return row

@router.post("/{expediente_id}/documentos/verificar")
def verificar_docs(expediente_id: int, db: Session = Depends(get_db)):
    row = pasar_a_docs_verificados(db, expediente_id)
    if not row:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")
    return row