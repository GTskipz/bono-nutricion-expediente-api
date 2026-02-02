from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

import hashlib
### [CAMBIO INTEGRACION MINIO] Imports necesarios para manejo de streams y sistema operativo
import io
import os
# Importamos el cliente de MinIO configurado en el proyecto
from app.core.minio import minio_client 
### --------------------------------------------------------------------------

from fastapi import HTTPException
from sqlalchemy import func, or_, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.expediente_electronico import ExpedienteElectronico
from app.models.info_general import InfoGeneral
from app.models.documentos_y_anexos import DocumentosYAnexos
from app.models.tracking_evento import TrackingEvento

from app.models.cat_tipo_documento import CatTipoDocumento
from app.models.cat_departamento import CatDepartamento
from app.models.cat_municipio import CatMunicipio
from app.models.cat_validacion import CatValidacion
from app.models.cat_estado_flujo_expediente import CatEstadoFlujoExpediente

from app.schemas.expediente import (
    ExpedienteCreate,
    ExpedienteSearchRequest,
    ExpedienteSearchResponse,
    ExpedienteSearchItem,
    BuscarPor,
)
from app.schemas.tracking_evento import TrackingCreate


# =====================================================
# Helpers (Upload)
# =====================================================

ESTADO_FLUJO_TITULAR_CARGADO = "TITULAR_CARGADO"
ESTADO_FLUJO_DOCS_CARGADOS = "DOCS_CARGADOS"

MAX_MB = 15
MAX_BYTES = MAX_MB * 1024 * 1024


def build_placeholder_ftp_key(expediente_id: int, documento_id: int, filename: str) -> str:
    safe = (filename or "archivo").replace(" ", "_")
    return f"ftp://PENDIENTE/expedientes/{expediente_id}/documentos/{documento_id}/{safe}"


def validar_tab(tab: str) -> str:
    tab = (tab or "").strip().upper()
    if tab not in ("DOCUMENTOS", "ANEXOS"):
        raise HTTPException(status_code=400, detail="tab inválido (DOCUMENTOS | ANEXOS)")
    return tab


def _assert_expediente_exists(db: Session, expediente_id: int) -> None:
    exists = (
        db.query(ExpedienteElectronico.id)
        .filter(ExpedienteElectronico.id == expediente_id)
        .first()
    )
    if not exists:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")


# =====================================================
# CORE: Crear expediente (REUTILIZABLE)
# =====================================================

def crear_expediente_core(payload: ExpedienteCreate, db: Session) -> ExpedienteElectronico:
    anio_carga = payload.anio_carga if getattr(payload, "anio_carga", None) else datetime.utcnow().year
    rub = getattr(payload, "rub", None)
    cui = getattr(payload, "cui_beneficiario", None)

    # =====================================================
    # Obtener estado de flujo inicial (ACTIVO)
    # =====================================================
    estado_activo = (
        db.query(CatEstadoFlujoExpediente)
        .filter(
            CatEstadoFlujoExpediente.codigo == "INICIO",
            CatEstadoFlujoExpediente.activo.is_(True),
        )
        .first()
    )

    if not estado_activo:
        raise HTTPException(
            status_code=500,
            detail="No existe el estado de flujo inicial (codigo=ACTIVO)."
        )

    # =====================================================
    # Pre-validaciones de unicidad
    # =====================================================
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
            raise HTTPException(
                status_code=409,
                detail=f"Ya existe un expediente con ese CUI para el año {anio_carga}."
            )

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
            raise HTTPException(
                status_code=409,
                detail=f"Ya existe un expediente con ese RUB para el año {anio_carga}."
            )

    # =====================================================
    # Crear expediente
    # =====================================================
    exp = ExpedienteElectronico(
        rub=rub,
        nombre_beneficiario=payload.nombre_beneficiario,
        cui_beneficiario=cui,
        departamento_id=payload.departamento_id,
        municipio_id=payload.municipio_id,
        anio_carga=anio_carga,
        estado_flujo_id=estado_activo.id,   # 👈 SETEO CLAVE
        updated_at=datetime.utcnow(),
    )
    db.add(exp)
    db.flush()  # exp.id disponible

    # =====================================================
    # Info general (opcional)
    # =====================================================
    ig = None
    if payload.info_general is not None:
        data_ig = payload.info_general.model_dump(exclude_none=True)

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

    # =====================================================
    # Commit
    # =====================================================
    try:
        db.commit()
    except IntegrityError as ie:
        db.rollback()
        msg = str(ie).lower()
        if "uq_expediente_cui_anio" in msg or ("cui_beneficiario" in msg and "anio_carga" in msg):
            raise HTTPException(
                status_code=409,
                detail=f"Ya existe un expediente con ese CUI para el año {anio_carga}."
            )
        if "uq_expediente_rub_anio" in msg or ("rub" in msg and "anio_carga" in msg):
            raise HTTPException(
                status_code=409,
                detail=f"Ya existe un expediente con ese RUB para el año {anio_carga}."
            )
        if "bpm_instance_id" in msg and "unique" in msg:
            raise HTTPException(
                status_code=409,
                detail="bpm_instance_id ya existe en otro expediente"
            )
        raise HTTPException(
            status_code=500,
            detail=f"Error de integridad al crear expediente: {str(ie)}"
        )

    db.refresh(exp)

    if ig is not None:
        db.refresh(ig)
        exp.info_general = ig

    return exp


def obtener_expediente(db: Session, expediente_id: int) -> ExpedienteElectronico:
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


def obtener_expediente_detalle(db: Session, expediente_id: int) -> ExpedienteElectronico:
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


# =====================================================
# SEARCH (BANDEJA)
# =====================================================

def buscar_expedientes(db: Session, payload: ExpedienteSearchRequest) -> ExpedienteSearchResponse:
    texto = (payload.texto or "").strip()

    if not payload.traer_todos and texto == "":
        return ExpedienteSearchResponse(data=[], page=payload.page, limit=payload.limit, total=0)

    buscar_nombre = BuscarPor.NOMBRE in payload.buscar_por
    buscar_dpi = BuscarPor.DPI in payload.buscar_por

    filters = []

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

            # ✅ Estado de flujo (catálogo)
            CatEstadoFlujoExpediente.codigo.label("estado_flujo_codigo"),
            CatEstadoFlujoExpediente.nombre.label("estado_flujo_nombre"),

            # ✅ Territorio
            CatDepartamento.nombre.label("departamento"),
            CatMunicipio.nombre.label("municipio"),
        )
        .outerjoin(
            CatEstadoFlujoExpediente,
            CatEstadoFlujoExpediente.id == ExpedienteElectronico.estado_flujo_id,
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

            # ✅ Nuevo en response (asegúrate que exista en el schema)
            estado_flujo_codigo=getattr(r, "estado_flujo_codigo", None),
            estado_flujo_nombre=getattr(r, "estado_flujo_nombre", None),

            departamento=r.departamento,
            municipio=r.municipio,
        )
        for r in rows
    ]

    return ExpedienteSearchResponse(data=data, page=payload.page, limit=payload.limit, total=total)

def listar_documentos_expediente(db: Session, expediente_id: int, tab: str) -> List[Dict[str, Any]]:
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
# UPLOADS (router leerá bytes; service actualiza DB)
# =====================================================

def _validate_file_bytes(content: bytes) -> int:
    size = len(content or b"")
    if size == 0:
        raise HTTPException(status_code=400, detail="Archivo vacío.")
    if size > MAX_BYTES:
        raise HTTPException(status_code=413, detail=f"Archivo excede {MAX_MB}MB.")
    return size


def upload_documento_por_id_core(
    db: Session,
    expediente_id: int,
    documento_id: int,
    filename: str,
    content_type: str,
    content: bytes,
    observacion: Optional[str] = None,
    descripcion: Optional[str] = None,
) -> Dict[str, Any]:
    _assert_expediente_exists(db, expediente_id)

    doc = db.query(DocumentosYAnexos).filter(DocumentosYAnexos.id == documento_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado (no existe id).")

    if doc.expediente_id != expediente_id:
        raise HTTPException(status_code=400, detail="El documento no pertenece a este expediente.")

    if not filename:
        raise HTTPException(status_code=400, detail="Archivo inválido.")

    size = _validate_file_bytes(content)
    mime = content_type or "application/octet-stream"
    checksum = hashlib.sha256(content).hexdigest()

    # --- [CAMBIO INTEGRACION MINIO] Inicio de lógica de carga real ---
    # Antes se usaba: ftp_key = build_placeholder_ftp_key(expediente_id, documento_id, filename)
    # Ahora subimos a MinIO:

    try:
        bucket_name = os.getenv("MINIO_BUCKET", "almacenamiento-mis")
        
        # Sanitizar nombre de archivo y construir ruta lógica
        safe_filename = filename.replace(" ", "_")
        # Ruta: expedientes/{id}/{tab}/reemplazos/{filename}
        # Nota: Usamos 'reemplazos' o directo el ID si prefieres mantener historial, 
        # aquí mantenemos la estructura simple.
        storage_key = f"expedientes/{expediente_id}/{doc.tab.lower()}/upd_{doc.id}_{safe_filename}"
        
        if not minio_client:
             raise HTTPException(status_code=500, detail="Servicio de almacenamiento no disponible")

        # Preparar stream
        data_stream = io.BytesIO(content)
        
        # Subir a MinIO
        minio_client.put_object(
            bucket_name,
            storage_key,
            data_stream,
            length=size,
            content_type=mime
        )
        
        # Asignar valores reales para la BD
        doc.storage_provider = "MINIO"
        doc.storage_key = storage_key
        doc.estado = "ADJUNTADO"

    except Exception as e:
        print(f"Error subiendo documento por ID a MinIO: {e}")
        raise HTTPException(status_code=500, detail="Error guardando el archivo físico en el servidor.")
    
    # --- [CAMBIO INTEGRACION MINIO] Fin de lógica de carga ---

    doc.filename = filename
    doc.mime_type = mime
    doc.size_bytes = size
    doc.checksum_sha256 = checksum
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


def upload_documento_por_tipo_core(
    db: Session,
    expediente_id: int,
    tab: str,
    tipo_documento_id: int,
    filename: str,
    content_type: str,
    content: bytes,
    observacion: Optional[str] = None,
    descripcion: Optional[str] = None,
) -> Dict[str, Any]:
    _assert_expediente_exists(db, expediente_id)

    tab = validar_tab(tab)

    tipo = db.query(CatTipoDocumento).filter(CatTipoDocumento.id == tipo_documento_id).first()
    if not tipo:
        raise HTTPException(status_code=400, detail="tipo_documento_id inválido (no existe en catálogo)")

    if not filename:
        raise HTTPException(status_code=400, detail="Archivo inválido.")

    size = _validate_file_bytes(content)
    mime = content_type or "application/octet-stream"
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

    # --- [CAMBIO INTEGRACION MINIO] Inicio de lógica de carga real ---
    # Antes se usaba: ftp_key = build_placeholder_ftp_key(...)
    # Ahora subimos a MinIO:

    try:
        bucket_name = os.getenv("MINIO_BUCKET", "almacenamiento-mis")
        
        # Construcción de ruta lógica: expedientes/{id}/{tab}/{codigo_tipo}_{filename}
        safe_filename = filename.replace(" ", "_")
        # Usamos el código del tipo de documento para orden (ej: DPI_MADRE_foto.jpg)
        codigo_prefix = tipo.codigo if tipo.codigo else f"T{tipo_documento_id}"
        storage_key = f"expedientes/{expediente_id}/{tab.lower()}/{codigo_prefix}_{safe_filename}"
        
        if not minio_client:
             raise HTTPException(status_code=500, detail="Servicio de almacenamiento no disponible")

        # Preparar stream de bytes
        data_stream = io.BytesIO(content)
        
        # Ejecutar subida (put_object)
        minio_client.put_object(
            bucket_name,
            storage_key,
            data_stream,
            length=size,
            content_type=mime
        )
        
        # Asignar punteros reales a la BD
        doc.storage_provider = "MINIO"
        doc.storage_key = storage_key
        doc.estado = "ADJUNTADO"

    except Exception as e:
        print(f"Error subiendo documento por TIPO a MinIO: {e}")
        # En caso de fallo crítico de IO, reportamos error 500
        raise HTTPException(status_code=500, detail="Error guardando el archivo físico en el servidor.")

    # --- [CAMBIO INTEGRACION MINIO] Fin de lógica de carga ---

    doc.filename = filename
    doc.mime_type = mime
    doc.size_bytes = size
    doc.checksum_sha256 = checksum
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

def crear_tracking_evento_core(db: Session, expediente_id: int, payload: TrackingCreate) -> TrackingEvento:
    _assert_expediente_exists(db, expediente_id)

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


def listar_tracking_expediente_core(db: Session, expediente_id: int) -> List[TrackingEvento]:
    _assert_expediente_exists(db, expediente_id)

    return (
        db.query(TrackingEvento)
        .filter(TrackingEvento.expediente_id == expediente_id)
        .order_by(TrackingEvento.fecha_evento.desc(), TrackingEvento.created_at.desc())
        .all()
    )


def set_expediente_bpm_minimo_core(
    db: Session,
    *,
    expediente_id: int,
    spiff_instance: dict,
) -> None:
    db.execute(
        text("""
            UPDATE expediente_electronico
            SET
              bpm_instance_id       = :iid,
              bpm_status            = :st,
              bpm_current_task_name = :task,
              bpm_process_key       = :pkey,
              bpm_last_sync_at      = :sync_at,
              updated_at            = :upd_at
            WHERE id = :eid
        """),
        {
            "eid": expediente_id,
            "iid": str(spiff_instance.get("id")),
            "st": spiff_instance.get("status"),
            "task": spiff_instance.get("last_milestone_bpmn_name"),
            "pkey": spiff_instance.get("process_model_identifier"),
            "sync_at": datetime.utcnow(),
            "upd_at": datetime.utcnow(),
        },
    )

def actualizar_titular_y_estado_flujo(
    db: Session,
    expediente_id: int,
    titular_nombre: str,
    titular_dpi: str,
):
    # 1) Obtener el estado TITULAR_CARGADO
    estado = db.execute(
        text("""
            SELECT id, codigo, nombre
            FROM cat_estado_flujo_expediente
            WHERE codigo = :codigo
              AND activo = TRUE
            LIMIT 1
        """),
        {"codigo": ESTADO_FLUJO_TITULAR_CARGADO},
    ).mappings().first()

    if not estado:
        raise ValueError("Estado de flujo TITULAR_CARGADO no existe o está inactivo")

    # 2) Actualizar expediente
    row = db.execute(
        text("""
            UPDATE expediente_electronico
               SET titular_nombre = :titular_nombre,
                   titular_dpi = :titular_dpi,
                   estado_flujo_id = :estado_flujo_id,
                   updated_at = NOW()
             WHERE id = :id
         RETURNING id, titular_nombre, titular_dpi, estado_flujo_id
        """),
        {
            "id": expediente_id,
            "titular_nombre": titular_nombre.strip(),
            "titular_dpi": titular_dpi.strip(),
            "estado_flujo_id": estado["id"],
        },
    ).mappings().first()

    if not row:
        return None

    db.commit()

    return {
        "expediente_id": row["id"],
        "titular_nombre": row["titular_nombre"],
        "titular_dpi": row["titular_dpi"],
        "estado_flujo_id": row["estado_flujo_id"],
        "estado_flujo_codigo": estado["codigo"],
        "estado_flujo_nombre": estado["nombre"],
    }

def confirmar_documentos_cargados(db: Session, expediente_id: int):
    # 1) Resolver estado destino
    estado = db.execute(
        text("""
            SELECT id, codigo, nombre
            FROM cat_estado_flujo_expediente
            WHERE codigo = :codigo AND activo = TRUE
            LIMIT 1
        """),
        {"codigo": ESTADO_FLUJO_DOCS_CARGADOS},
    ).mappings().first()

    if not estado:
        raise ValueError("Estado de flujo DOCS_CARGADOS no existe o está inactivo")

    # 2) (Opcional) Validación mínima (si quieres bloquear avanzar sin docs)
    #    Si ya tienes validación en otro lugar, déjalo comentado:
    #
    # has_docs = db.execute(
    #     text("SELECT 1 FROM documentos_y_anexos WHERE expediente_id = :id LIMIT 1"),
    #     {"id": expediente_id},
    # ).first()
    # if not has_docs:
    #     raise ValueError("No hay documentos vinculados para confirmar")

    # 3) Actualizar expediente
    row = db.execute(
        text("""
            UPDATE expediente_electronico
               SET estado_flujo_id = :estado_flujo_id,
                   updated_at = NOW()
             WHERE id = :id
         RETURNING id, estado_flujo_id
        """),
        {"id": expediente_id, "estado_flujo_id": estado["id"]},
    ).mappings().first()

    if not row:
        return None

    db.commit()

    return {
        "expediente_id": row["id"],
        "estado_flujo_id": row["estado_flujo_id"],
        "estado_flujo_codigo": estado["codigo"],
        "estado_flujo_nombre": estado["nombre"],
    }


def pasar_a_docs_verificados(db: Session, expediente_id: int):
    row = db.execute(
        text("""
            UPDATE expediente_electronico
            SET estado_flujo_id = (
                SELECT id
                FROM cat_estado_flujo_expediente
                WHERE codigo = 'DOCS_VERIFICADOS'
                LIMIT 1
            ),
            updated_at = NOW()
            WHERE id = :id
            RETURNING id, estado_flujo_id
        """),
        {"id": expediente_id},
    ).mappings().first()

    if not row:
        return None

    db.commit()
    return dict(row)