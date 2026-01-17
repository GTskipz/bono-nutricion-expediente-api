from __future__ import annotations
from uuid import UUID
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
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from datetime import datetime
import hashlib

from app.core.db import get_db

from app.schemas.expediente import (
    ExpedienteCreate,
    ExpedienteOut,
    ExpedienteSearchRequest,
    ExpedienteSearchResponse,
    ExpedienteSearchItem,
    BuscarPor,
)

from app.models.expediente_electronico import ExpedienteElectronico
from app.models.info_general import InfoGeneral
from app.models.documentos_y_anexos import DocumentosYAnexos
from app.models.tracking_evento import TrackingEvento
from app.schemas.tracking_evento import TrackingCreate, TrackingOut

# Catálogos territorio
from app.models.cat_tipo_documento import CatTipoDocumento
from app.models.cat_departamento import CatDepartamento
from app.models.cat_municipio import CatMunicipio
from app.models.cat_validacion import CatValidacion

from fastapi.responses import FileResponse
from app.services.documentos.carta_aceptacion import generar_carta_aceptacion_docx_bytes
from app.utils.docx_to_pdf import docx_bytes_to_pdf_bytes

router = APIRouter(prefix="/expedientes", tags=["Expedientes"])


# =====================================================
# Helpers (Upload)
# =====================================================

MAX_MB = 15
MAX_BYTES = MAX_MB * 1024 * 1024


def build_placeholder_ftp_key(expediente_id: int, documento_id: int, filename: str) -> str:
    """
    storage_key: por ahora reservamos la "ruta" donde quedaría en FTP.
    Luego aquí se reemplaza por la llave/URL real devuelta por el uploader FTP.
    """
    safe = (filename or "archivo").replace(" ", "_")
    return f"ftp://PENDIENTE/expedientes/{expediente_id}/documentos/{documento_id}/{safe}"


def validar_tab(tab: str) -> str:
    tab = (tab or "").strip().upper()
    if tab not in ("DOCUMENTOS", "ANEXOS"):
        raise HTTPException(status_code=400, detail="tab inválido (DOCUMENTOS | ANEXOS)")
    return tab


# =====================================================
# CORE: Crear expediente (REUTILIZABLE)
# =====================================================

def crear_expediente_core(payload: ExpedienteCreate, db: Session) -> ExpedienteElectronico:
    """
    Crea expediente_electronico y, si viene, crea info_general 1:1.

    IMPORTANTE:
    - Los DOCUMENTOS obligatorios NO se crean aquí: los crea el TRIGGER en BD (si está activo).
    - docs_required_status lo mantiene el TRIGGER.
    - validacion_id: si no viene, se asigna por defecto codigo=INVALIDO

    ✅ Este método existe para que SESAN (carga masiva) pueda reutilizar la misma creación
    sin duplicar lógica de inserts.

    ✅ FIX MIS:
    - Si payload.anio_carga NO viene (o viene vacío), se usa el año actual (UTC).
    - Se incluye rub (Registro Único de Beneficiario) si viene en el payload.
    - Regla: no repetir CUI por año y no repetir RUB por año (si viene).
    """
    anio_carga = payload.anio_carga if getattr(payload, "anio_carga", None) else datetime.utcnow().year
    rub = getattr(payload, "rub", None)
    cui = getattr(payload, "cui_beneficiario", None)

    # ===============================
    # Pre-validaciones de unicidad (antes del INSERT)
    # ===============================
    if cui:
        exists_cui = (
            db.query(ExpedienteElectronico.id)
            .filter(
                ExpedienteElectronico.cui_beneficiario == cui,
                ExpedienteElectronico.anio_carga == anio_carga,
            )
            .first()
        )
        if exists_cui:
            raise HTTPException(status_code=409, detail=f"Ya existe un expediente con ese CUI para el año {anio_carga}.")

    if rub:
        exists_rub = (
            db.query(ExpedienteElectronico.id)
            .filter(
                ExpedienteElectronico.rub == rub,
                ExpedienteElectronico.anio_carga == anio_carga,
            )
            .first()
        )
        if exists_rub:
            raise HTTPException(status_code=409, detail=f"Ya existe un expediente con ese RUB para el año {anio_carga}.")

    # 1) crear expediente
    exp = ExpedienteElectronico(
        rub=rub,
        nombre_beneficiario=payload.nombre_beneficiario,
        cui_beneficiario=cui,
        departamento_id=payload.departamento_id,
        municipio_id=payload.municipio_id,
        anio_carga=anio_carga,
        updated_at=datetime.utcnow(),
    )
    db.add(exp)
    db.flush()  # exp.id disponible (antes de commit)

    # 2) crear info_general 1:1 (solo si viene)
    ig = None
    if payload.info_general is not None:
        data_ig = payload.info_general.model_dump(exclude_none=True)

        # ✅ Default validación: INVALIDO
        if data_ig.get("validacion_id") is None:
            inval = (
                db.query(CatValidacion)
                .filter(
                    CatValidacion.codigo == "INVALIDO",
                    CatValidacion.activo.is_(True),
                )
                .first()
            )
            if not inval:
                raise HTTPException(
                    status_code=500,
                    detail="No existe el catálogo de validación por defecto (codigo=INVALIDO).",
                )
            data_ig["validacion_id"] = inval.id

        ig = InfoGeneral(expediente_id=exp.id, **data_ig)
        db.add(ig)

    try:
        db.commit()
    except IntegrityError as ie:
        db.rollback()
        msg = str(ie).lower()
        # cubre UNIQUE (cui_beneficiario, anio_carga) y UNIQUE (rub, anio_carga)
        if "uq_expediente_cui_anio" in msg or ("cui_beneficiario" in msg and "anio_carga" in msg):
            raise HTTPException(status_code=409, detail=f"Ya existe un expediente con ese CUI para el año {anio_carga}.")
        if "uq_expediente_rub_anio" in msg or ("rub" in msg and "anio_carga" in msg):
            raise HTTPException(status_code=409, detail=f"Ya existe un expediente con ese RUB para el año {anio_carga}.")
        if "bpm_instance_id" in msg and "unique" in msg:
            raise HTTPException(status_code=409, detail="bpm_instance_id ya existe en otro expediente")
        raise HTTPException(status_code=500, detail=f"Error de integridad al crear expediente: {str(ie)}")

    # refrescar: trae docs_required_status (si el trigger lo setea en insert)
    db.refresh(exp)

    # adjuntar info_general para respuesta (si fue creado)
    if ig is not None:
        db.refresh(ig)
        exp.info_general = ig

    return exp


# =====================================================
# Crear / Obtener expediente
# =====================================================

@router.post("", response_model=ExpedienteOut, status_code=201)
def crear_expediente(payload: ExpedienteCreate, db: Session = Depends(get_db)):
    """
    Endpoint público: crea expediente usando el CORE reutilizable.
    """
    try:
        return crear_expediente_core(payload, db)
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error creando expediente: {str(e)}")


@router.get("/{expediente_id}", response_model=ExpedienteOut)
def obtener_expediente(expediente_id: int, db: Session = Depends(get_db)):
    exp = (
        db.query(ExpedienteElectronico)
        .filter(ExpedienteElectronico.id == expediente_id)
        .first()
    )
    if not exp:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")

    ig = db.query(InfoGeneral).filter(InfoGeneral.expediente_id == exp.id).first()
    exp.info_general = ig

    return exp


# =====================================================
# SEARCH (BANDEJA)
# =====================================================

@router.post("/search", response_model=ExpedienteSearchResponse)
def buscar_expedientes(payload: ExpedienteSearchRequest, db: Session = Depends(get_db)):
    texto = (payload.texto or "").strip()

    # Regla MIS: si no traer_todos y no hay texto => NO devolver todo
    if not payload.traer_todos and texto == "":
        return ExpedienteSearchResponse(data=[], page=payload.page, limit=payload.limit, total=0)

    buscar_nombre = BuscarPor.NOMBRE in payload.buscar_por
    buscar_dpi = BuscarPor.DPI in payload.buscar_por

    filters = []

    # Filtro por texto (solo si NO traer_todos)
    if not payload.traer_todos:
        text_filters = []

        if buscar_nombre:
            text_filters.append(ExpedienteElectronico.nombre_beneficiario.ilike(f"%{texto}%"))

        if buscar_dpi:
            text_filters.append(ExpedienteElectronico.cui_beneficiario.like(f"{texto}%"))

        if not text_filters:
            return ExpedienteSearchResponse(data=[], page=payload.page, limit=payload.limit, total=0)

        filters.append(or_(*text_filters))

    total_q = db.query(func.count(ExpedienteElectronico.id))
    if filters:
        total_q = total_q.filter(*filters)
    total = total_q.scalar() or 0

    offset = (payload.page - 1) * payload.limit

    q = (
        db.query(
            ExpedienteElectronico.id,
            ExpedienteElectronico.created_at,
            ExpedienteElectronico.nombre_beneficiario,
            ExpedienteElectronico.cui_beneficiario,
            ExpedienteElectronico.estado_expediente,
            ExpedienteElectronico.bpm_status,
            ExpedienteElectronico.bpm_current_task_name,
            CatDepartamento.nombre.label("departamento"),
            CatMunicipio.nombre.label("municipio"),
        )
        .outerjoin(CatDepartamento, CatDepartamento.id == ExpedienteElectronico.departamento_id)
        .outerjoin(CatMunicipio, CatMunicipio.id == ExpedienteElectronico.municipio_id)
    )

    if filters:
        q = q.filter(*filters)

    rows = (
        q.order_by(ExpedienteElectronico.created_at.desc())
        .offset(offset)
        .limit(payload.limit)
        .all()
    )

    data = [
        ExpedienteSearchItem(
            id=r.id,
            created_at=r.created_at,
            nombre_beneficiario=r.nombre_beneficiario,
            cui_beneficiario=r.cui_beneficiario,
            estado_expediente=r.estado_expediente,
            bpm_status=r.bpm_status,
            bpm_current_task_name=r.bpm_current_task_name,
            departamento=r.departamento,
            municipio=r.municipio,
        )
        for r in rows
    ]

    return ExpedienteSearchResponse(
        data=data,
        page=payload.page,
        limit=payload.limit,
        total=total,
    )


@router.post("/bandeja", response_model=ExpedienteSearchResponse)
def bandeja_asignados(payload: ExpedienteSearchRequest, db: Session = Depends(get_db)):
    """
    Bandeja de casos asignados (temporal).
    """
    payload.traer_todos = True
    return buscar_expedientes(payload, db)


@router.get("/{expediente_id}/detalle", response_model=ExpedienteOut)
def obtener_expediente_detalle(expediente_id: int, db: Session = Depends(get_db)):
    row = (
        db.query(
            ExpedienteElectronico,
            CatDepartamento.nombre.label("departamento"),
            CatMunicipio.nombre.label("municipio"),
        )
        .outerjoin(CatDepartamento, CatDepartamento.id == ExpedienteElectronico.departamento_id)
        .outerjoin(CatMunicipio, CatMunicipio.id == ExpedienteElectronico.municipio_id)
        .filter(ExpedienteElectronico.id == expediente_id)
        .first()
    )

    if not row:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")

    exp, departamento, municipio = row

    ig = db.query(InfoGeneral).filter(InfoGeneral.expediente_id == exp.id).first()
    exp.info_general = ig

    exp.departamento = departamento
    exp.municipio = municipio

    docs = getattr(exp, "docs_required_status", None)
    exp.docs_required_state = "COMPLETO" if isinstance(docs, dict) and docs.get("completo") is True else "PENDIENTE"

    return exp


@router.get("/{expediente_id}/documentos")
def listar_documentos_expediente(
    expediente_id: int,
    tab: str = Query("DOCUMENTOS", description="DOCUMENTOS | ANEXOS"),
    db: Session = Depends(get_db),
):
    tab = validar_tab(tab)

    rows = (
        db.query(
            DocumentosYAnexos.id,
            DocumentosYAnexos.estado,
            DocumentosYAnexos.filename,
            DocumentosYAnexos.updated_at,
            DocumentosYAnexos.observacion,
            DocumentosYAnexos.tipo_documento_id,
            CatTipoDocumento.nombre.label("tipo_documento_nombre"),
            CatTipoDocumento.codigo.label("tipo_documento_codigo"),
            CatTipoDocumento.es_obligatorio.label("es_obligatorio"),
            CatTipoDocumento.orden.label("orden"),
        )
        .outerjoin(CatTipoDocumento, CatTipoDocumento.id == DocumentosYAnexos.tipo_documento_id)
        .filter(DocumentosYAnexos.expediente_id == expediente_id)
        .filter(DocumentosYAnexos.tab == tab)
        .order_by(CatTipoDocumento.orden.asc().nullslast(), DocumentosYAnexos.created_at.asc())
        .all()
    )

    return [
        {
            "id": r.id,
            "estado": r.estado,
            "filename": r.filename,
            "updated_at": r.updated_at,
            "observacion": r.observacion,
            "tipo_documento_id": r.tipo_documento_id,
            "tipo_documento_nombre": r.tipo_documento_nombre,
            "tipo_documento_codigo": r.tipo_documento_codigo,
            "es_obligatorio": r.es_obligatorio,
            "orden": r.orden,
        }
        for r in rows
    ]


# =====================================================
# UPLOAD 1: por documento_id (si ya existe)
# =====================================================

@router.post("/{expediente_id}/documentos/{documento_id}/upload")
async def upload_documento_por_id(
    expediente_id: int,
    documento_id: int,
    file: UploadFile = File(...),
    observacion: str | None = Form(None),
    descripcion: str | None = Form(None),
    db: Session = Depends(get_db),
):
    exp_exists = (
        db.query(ExpedienteElectronico.id)
        .filter(ExpedienteElectronico.id == expediente_id)
        .first()
    )
    if not exp_exists:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")

    doc = (
        db.query(DocumentosYAnexos)
        .filter(DocumentosYAnexos.id == documento_id)
        .first()
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado (no existe id).")

    if doc.expediente_id != expediente_id:
        raise HTTPException(status_code=400, detail="El documento no pertenece a este expediente.")

    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="Archivo inválido.")

    content = await file.read()
    size = len(content)

    if size == 0:
        raise HTTPException(status_code=400, detail="Archivo vacío.")
    if size > MAX_BYTES:
        raise HTTPException(status_code=413, detail=f"Archivo excede {MAX_MB}MB.")

    mime = file.content_type or "application/octet-stream"
    checksum = hashlib.sha256(content).hexdigest()

    ftp_key = build_placeholder_ftp_key(expediente_id, documento_id, file.filename)

    doc.estado = "ADJUNTADO"
    doc.filename = file.filename
    doc.mime_type = mime
    doc.size_bytes = size
    doc.checksum_sha256 = checksum
    doc.storage_provider = "FTP"
    doc.storage_key = ftp_key
    doc.subido_por = "pendiente"
    doc.observacion = observacion
    doc.descripcion = descripcion
    doc.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(doc)

    return {
        "ok": True,
        "id": doc.id,
        "expediente_id": doc.expediente_id,
        "tab": doc.tab,
        "tipo_documento_id": doc.tipo_documento_id,
        "estado": doc.estado,
        "filename": doc.filename,
        "mime_type": doc.mime_type,
        "size_bytes": doc.size_bytes,
        "storage_provider": doc.storage_provider,
        "storage_key": doc.storage_key,
        "checksum_sha256": doc.checksum_sha256,
        "updated_at": doc.updated_at,
    }


# =====================================================
# UPLOAD 2: fallback si no hay id / trigger no creó registros
# =====================================================

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
    exp_exists = (
        db.query(ExpedienteElectronico.id)
        .filter(ExpedienteElectronico.id == expediente_id)
        .first()
    )
    if not exp_exists:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")

    tab = validar_tab(tab)

    tipo = db.query(CatTipoDocumento).filter(CatTipoDocumento.id == tipo_documento_id).first()
    if not tipo:
        raise HTTPException(status_code=400, detail="tipo_documento_id inválido (no existe en catálogo)")

    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="Archivo inválido.")

    content = await file.read()
    size = len(content)

    if size == 0:
        raise HTTPException(status_code=400, detail="Archivo vacío.")
    if size > MAX_BYTES:
        raise HTTPException(status_code=413, detail=f"Archivo excede {MAX_MB}MB.")

    mime = file.content_type or "application/octet-stream"
    checksum = hashlib.sha256(content).hexdigest()

    doc = (
        db.query(DocumentosYAnexos)
        .filter(DocumentosYAnexos.expediente_id == expediente_id)
        .filter(DocumentosYAnexos.tab == tab)
        .filter(DocumentosYAnexos.tipo_documento_id == tipo_documento_id)
        .first()
    )

    if not doc:
        doc = DocumentosYAnexos(
            expediente_id=expediente_id,
            tab=tab,
            tipo_documento_id=tipo_documento_id,
            estado="NO_ADJUNTADO",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(doc)
        db.flush()

    ftp_key = build_placeholder_ftp_key(expediente_id, doc.id, file.filename)

    doc.estado = "ADJUNTADO"
    doc.filename = file.filename
    doc.mime_type = mime
    doc.size_bytes = size
    doc.checksum_sha256 = checksum
    doc.storage_provider = "FTP"
    doc.storage_key = ftp_key
    doc.subido_por = "pendiente"
    doc.observacion = observacion
    doc.descripcion = descripcion
    doc.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(doc)

    return {
        "ok": True,
        "id": doc.id,
        "expediente_id": doc.expediente_id,
        "tab": doc.tab,
        "tipo_documento_id": doc.tipo_documento_id,
        "estado": doc.estado,
        "filename": doc.filename,
        "mime_type": doc.mime_type,
        "size_bytes": doc.size_bytes,
        "storage_provider": doc.storage_provider,
        "storage_key": doc.storage_key,
        "checksum_sha256": doc.checksum_sha256,
        "updated_at": doc.updated_at,
    }


# =====================================================
# TRACKING
# =====================================================

@router.post(
    "/{expediente_id}/tracking",
    response_model=TrackingOut,
    status_code=201
)
def crear_tracking_evento(
    expediente_id: int,
    payload: TrackingCreate,
    db: Session = Depends(get_db),
):
    exists = (
        db.query(ExpedienteElectronico.id)
        .filter(ExpedienteElectronico.id == expediente_id)
        .first()
    )
    if not exists:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")

    evento = TrackingEvento(
        expediente_id=expediente_id,
        fecha_evento=payload.fecha_evento or datetime.utcnow(),
        titulo=payload.titulo,
        usuario=payload.usuario,
        observacion=payload.observacion,
        origen=payload.origen,
        tipo_evento=payload.tipo_evento,
    )

    db.add(evento)
    db.commit()
    db.refresh(evento)
    return evento


@router.get(
    "/{expediente_id}/tracking",
    response_model=list[TrackingOut]
)
def listar_tracking_expediente(
    expediente_id: int,
    db: Session = Depends(get_db),
):
    exists = (
        db.query(ExpedienteElectronico.id)
        .filter(ExpedienteElectronico.id == expediente_id)
        .first()
    )
    if not exists:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")

    eventos = (
        db.query(TrackingEvento)
        .filter(TrackingEvento.expediente_id == expediente_id)
        .order_by(
            TrackingEvento.fecha_evento.desc(),
            TrackingEvento.created_at.desc(),
        )
        .all()
    )

    return eventos

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