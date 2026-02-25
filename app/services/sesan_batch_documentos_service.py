# app/services/sesan_batch_documentos_service.py

from __future__ import annotations

from typing import List, Dict, Any, Tuple, Optional
from datetime import date

from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from app.models.cat_tipo_doc_batch import CatTipoDocBatch
from app.models.sesan_batch_documento import SesanBatchDocumento


# ======================================================
# Catálogo: Tipos de documento batch
# ======================================================

def listar_tipos_doc_batch(db: Session, solo_activos: bool = True) -> List[CatTipoDocBatch]:
    """
    Lista tipos de documento del batch, ordenados por (orden, id).
    """
    q = db.query(CatTipoDocBatch)
    if solo_activos:
        q = q.filter(CatTipoDocBatch.activo.is_(True))
    return q.order_by(CatTipoDocBatch.orden.asc(), CatTipoDocBatch.id.asc()).all()


def contar_tipos_requeridos_activos(db: Session) -> int:
    """
    Cuenta cuántos tipos están marcados como requeridos y activos.
    """
    return (
        db.query(func.count(CatTipoDocBatch.id))
        .filter(CatTipoDocBatch.activo.is_(True), CatTipoDocBatch.requerido.is_(True))
        .scalar()
    ) or 0


# ======================================================
# Placeholders: crear registros pendientes al crear batch
# ======================================================

def crear_placeholders_docs_requeridos(db: Session, batch_id: int) -> int:
    """
    Crea registros en sesan_batch_documento para todos los tipos requeridos activos.
    NO sube archivos; deja placeholders (storage_key NULL).

    Requiere que en DB/model:
      - fecha_documento sea NULLable
      - storage_provider sea NULLable
      - storage_key sea NULLable

    Retorna la cantidad de placeholders creados.
    """
    tipos = (
        db.query(CatTipoDocBatch)
        .filter(CatTipoDocBatch.activo.is_(True), CatTipoDocBatch.requerido.is_(True))
        .order_by(CatTipoDocBatch.orden.asc(), CatTipoDocBatch.id.asc())
        .all()
    )

    created = 0
    for t in tipos:
        exists = (
            db.query(SesanBatchDocumento.id)
            .filter(
                SesanBatchDocumento.batch_id == batch_id,
                SesanBatchDocumento.tipo_doc_id == t.id,
            )
            .first()
        )
        if exists:
            continue

        db.add(
            SesanBatchDocumento(
                batch_id=batch_id,
                tipo_doc_id=t.id,
                # ✅ placeholder: sin fecha ni archivo
                fecha_documento=None,
                archivo_nombre_original=None,
                archivo_mime_type=None,
                archivo_size_bytes=None,
                storage_provider=None,
                storage_key=None,
                checksum_sha256=None,
            )
        )
        created += 1

    db.commit()
    return created


# ======================================================
# Documentos: consultas por batch
# ======================================================

def listar_documentos_batch(db: Session, batch_id: int) -> List[SesanBatchDocumento]:
    """
    Lista documentos (incluye placeholders) para un batch.
    """
    return (
        db.query(SesanBatchDocumento)
        .filter(SesanBatchDocumento.batch_id == batch_id)
        .order_by(SesanBatchDocumento.tipo_doc_id.asc(), SesanBatchDocumento.id.asc())
        .all()
    )


def obtener_documento_batch(db: Session, batch_id: int, tipo_doc_id: int) -> Optional[SesanBatchDocumento]:
    """
    Obtiene un documento específico por (batch_id, tipo_doc_id).
    """
    return (
        db.query(SesanBatchDocumento)
        .filter(
            SesanBatchDocumento.batch_id == batch_id,
            SesanBatchDocumento.tipo_doc_id == tipo_doc_id,
        )
        .first()
    )


# ======================================================
# Upsert: actualizar placeholder cuando suben archivo
# ======================================================

def upsert_documento_batch(
    db: Session,
    *,
    batch_id: int,
    tipo_doc_id: int,
    fecha_documento: date,
    archivo_nombre_original: Optional[str],
    archivo_mime_type: Optional[str],
    archivo_size_bytes: Optional[int],
    storage_provider: str,
    storage_key: str,
    checksum_sha256: Optional[str] = None,
) -> SesanBatchDocumento:
    """
    Inserta o actualiza un documento del batch respetando UNIQUE(batch_id, tipo_doc_id).

    Caso normal:
      - ya existe placeholder -> se actualiza y queda "cargado".
    Caso extremo:
      - no existe placeholder -> se crea el registro y se llena todo.
    """
    doc = obtener_documento_batch(db, batch_id, tipo_doc_id)

    if not doc:
        doc = SesanBatchDocumento(batch_id=batch_id, tipo_doc_id=tipo_doc_id)
        db.add(doc)

    doc.fecha_documento = fecha_documento
    doc.archivo_nombre_original = archivo_nombre_original
    doc.archivo_mime_type = archivo_mime_type
    doc.archivo_size_bytes = archivo_size_bytes
    doc.storage_provider = storage_provider
    doc.storage_key = storage_key
    doc.checksum_sha256 = checksum_sha256

    db.commit()
    db.refresh(doc)
    return doc


# ======================================================
# Validación: requeridos antes de procesar batch
# ======================================================

def contar_docs_requeridos_cargados(db: Session, batch_id: int, exigir_fecha: bool = False) -> int:
    """
    Cuenta los documentos requeridos activos que ya tienen archivo cargado (storage_key NOT NULL).
    Si exigir_fecha=True, también exige fecha_documento NOT NULL.
    """
    filters = [
        SesanBatchDocumento.batch_id == batch_id,
        CatTipoDocBatch.activo.is_(True),
        CatTipoDocBatch.requerido.is_(True),
        SesanBatchDocumento.storage_key.isnot(None),
    ]
    if exigir_fecha:
        filters.append(SesanBatchDocumento.fecha_documento.isnot(None))

    return (
        db.query(func.count(SesanBatchDocumento.id))
        .join(CatTipoDocBatch, CatTipoDocBatch.id == SesanBatchDocumento.tipo_doc_id)
        .filter(*filters)
        .scalar()
    ) or 0


def listar_tipos_requeridos_faltantes(db: Session, batch_id: int, exigir_fecha: bool = False) -> List[CatTipoDocBatch]:
    """
    Lista tipos requeridos activos que todavía NO están cargados.
    Se considera "cargado" cuando storage_key IS NOT NULL.
    Si exigir_fecha=True, también requiere fecha_documento IS NOT NULL.
    """
    # Outer join para capturar tanto:
    # - placeholders (existen pero sin storage_key)
    # - casos raros donde no exista registro
    join_cond = and_(
        SesanBatchDocumento.tipo_doc_id == CatTipoDocBatch.id,
        SesanBatchDocumento.batch_id == batch_id,
    )

    q = (
        db.query(CatTipoDocBatch)
        .outerjoin(SesanBatchDocumento, join_cond)
        .filter(
            CatTipoDocBatch.activo.is_(True),
            CatTipoDocBatch.requerido.is_(True),
        )
    )

    # Faltante si:
    # - no hay registro (storage_key será NULL por outer join)
    # - hay placeholder sin storage_key
    q = q.filter(SesanBatchDocumento.storage_key.is_(None))

    if exigir_fecha:
        q = q.filter(SesanBatchDocumento.fecha_documento.is_(None))

    return q.order_by(CatTipoDocBatch.orden.asc(), CatTipoDocBatch.id.asc()).all()


def validar_docs_requeridos_batch(db: Session, batch_id: int, exigir_fecha: bool = False) -> Tuple[bool, Dict[str, Any]]:
    """
    Valida regla de negocio:
    NO se puede procesar un batch si no existen todos los documentos requeridos activos
    con archivo cargado (storage_key NOT NULL).

    Retorna:
      (ok, detail)
    """
    total_req = contar_tipos_requeridos_activos(db)
    presentes = contar_docs_requeridos_cargados(db, batch_id, exigir_fecha=exigir_fecha)

    if total_req == 0:
        # No bloqueamos si no hay requeridos activos (aunque normalmente debería existir)
        return True, {"total_requeridos": 0, "presentes_requeridos": presentes, "faltantes": 0}

    if presentes >= total_req:
        return True, {"total_requeridos": total_req, "presentes_requeridos": presentes, "faltantes": 0}

    faltantes = listar_tipos_requeridos_faltantes(db, batch_id, exigir_fecha=exigir_fecha)

    return False, {
        "total_requeridos": total_req,
        "presentes_requeridos": presentes,
        "faltantes": max(total_req - presentes, 0),
        "missing_types": [{"id": t.id, "codigo": t.codigo, "nombre": t.nombre} for t in faltantes],
    }
