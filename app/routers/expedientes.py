from __future__ import annotations
from sqlite3 import IntegrityError

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

from app.schemas.expediente_contacto import (
    ExpedienteContactoIn,
    ExpedienteContactoOut,
)
from app.services.expediente_contacto_service import (
    get_contacto_expediente,
    upsert_contacto_expediente,
)

from app.services.documentos.carta_aceptacion import generar_carta_aceptacion_docx_bytes
from app.utils.docx_to_pdf import docx_bytes_to_pdf_bytes

from app.bpm.bpm_service_task_titular import BpmServiceTaskTitular
from app.bpm.bpm_service_task_expediente_digital import BpmServiceTaskExpedienteDigital



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
async def registrar_titular(
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
            personalizado=payload.personalizado,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not row:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")

    # ✅ BPM (sin tocar BD)
    try:
        bpm = BpmServiceTaskTitular(db)
        await bpm.procesar_titular(
            expediente_id=expediente_id,
            nombre_titular=payload.titular_nombre,
            dpi_titular=payload.titular_dpi,
            tiene_copia_recibo=True,
            tiene_copia_dpi=True,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error enviando titular a BPM: {str(e)}")

    return row

@router.post("/{expediente_id}/documentos/confirmar")
async def confirmar_docs(expediente_id: int, db: Session = Depends(get_db)):
    # 1) BD (ya hace commit adentro)
    try:
        row = confirmar_documentos_cargados(db, expediente_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not row:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")

    # 2) BPM (construye links relativos desde documentos_y_anexos y hace PUT)
    try:
        bpm = BpmServiceTaskExpedienteDigital(db)
        await bpm.enviar_expediente_digital(
            expediente_id=expediente_id,
            observaciones_exp="Documentos enviados a verificación",
            expediente_completo=True,     # si quieres, luego lo calculamos automáticamente
            strict_links=True,            # si falta un doc requerido, falla con 400/502 según manejes
        )
    except ValueError as e:
        # típicamente: faltan documentos requeridos (strict_links=True)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error enviando expediente digital a BPM: {str(e)}")

    return row

@router.post("/{expediente_id}/documentos/verificar")
def verificar_docs(expediente_id: int, db: Session = Depends(get_db)):
    row = pasar_a_docs_verificados(db, expediente_id)
    if not row:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")
    return row

@router.get("/{expediente_id}/contacto", response_model=ExpedienteContactoOut | None)
def obtener_contacto(expediente_id: int, db: Session = Depends(get_db)):

    return get_contacto_expediente(db, expediente_id)


@router.put("/{expediente_id}/contacto", response_model=ExpedienteContactoOut)
def guardar_contacto(
    expediente_id: int,
    payload: ExpedienteContactoIn,
    db: Session = Depends(get_db),
):

    try:
        row = upsert_contacto_expediente(db, expediente_id, payload)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="El municipio no pertenece al departamento seleccionado.",
        )

    if not row:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")

    return row