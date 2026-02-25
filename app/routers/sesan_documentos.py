from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, date
from io import BytesIO
import hashlib
import os
import re

from app.core.minio import minio_client
from app.core.db import get_db

router = APIRouter(prefix="/sesan-documentos", tags=["SESAN - Documentos"])

# =========================
# Helpers
# =========================
def _get_bucket() -> str:
    return os.getenv("MINIO_BUCKET", "almacenamiento-mis")


def _parse_date_yyyy_mm_dd(v: str) -> date:
    try:
        return date.fromisoformat(v)  # YYYY-MM-DD
    except Exception:
        raise HTTPException(status_code=422, detail="fecha_documento inválida. Formato esperado: YYYY-MM-DD.")


def _safe_filename(name: str) -> str:
    if not name:
        return "archivo.dat"
    name = name.strip()
    name = re.sub(r"[^\w\.\-]+", "_", name)
    return name[:180]


def _build_storage_key(doc_id: int, original_name: str) -> str:
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    safe = _safe_filename(original_name)
    return f"sesan/batch_documentos/{doc_id}/{ts}_{safe}"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ====================================================
# POST: Subir/Reemplazar doc batch (Backend -> MinIO -> Update DB)
# ====================================================
@router.post("/batch-documento/{doc_id}/upload")
async def upload_batch_documento(
    doc_id: int,
    fecha_documento: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    1) Verifica que exista sesan_batch_documento
    2) Sube el archivo a MinIO
    3) Si MinIO OK, actualiza metadata en sesan_batch_documento
    """
    if not minio_client:
        raise HTTPException(status_code=500, detail="El servicio de almacenamiento no está disponible")

    # ✅ 1) validar doc existe (SIN 'activo')
    q = text("""
        SELECT id
        FROM sesan_batch_documento
        WHERE id = :id
    """)
    row = db.execute(q, {"id": doc_id}).first()
    if not row:
        raise HTTPException(status_code=404, detail="Documento de batch no encontrado")

    # ✅ 2) validar fecha (YYYY-MM-DD)
    f = _parse_date_yyyy_mm_dd(fecha_documento)

    if not file:
        raise HTTPException(status_code=422, detail="Debe adjuntar un archivo")

    # ✅ 3) leer bytes
    try:
        content = await file.read()
    except Exception as e:
        print(f"Error leyendo UploadFile: {e}")
        raise HTTPException(status_code=500, detail="Error leyendo el archivo")

    if not content:
        raise HTTPException(status_code=422, detail="El archivo está vacío")

    original_name = file.filename or "archivo.dat"
    mime_type = file.content_type or "application/octet-stream"
    size_bytes = len(content)
    checksum = _sha256_bytes(content)

    storage_key = _build_storage_key(doc_id, original_name)
    bucket_name = _get_bucket()

    # ✅ 4) subir a MinIO (si falla, NO actualiza DB)
    try:
        data = BytesIO(content)
        minio_client.put_object(
            bucket_name,
            storage_key,
            data,
            length=size_bytes,
            content_type=mime_type,
        )
    except Exception as e:
        print(f"Error subiendo a MinIO: {e}")
        raise HTTPException(status_code=500, detail="Error subiendo el archivo al almacenamiento")

    # ✅ 5) update DB SOLO con columnas existentes en tu DDL
    try:
        upd = text("""
            UPDATE sesan_batch_documento
            SET
              fecha_documento = :fecha_documento,
              archivo_nombre_original = :filename,
              archivo_mime_type = :mime_type,
              archivo_size_bytes = :size_bytes,
              storage_provider = 'MINIO',
              storage_key = :storage_key,
              checksum_sha256 = :checksum,
              updated_at = NOW()
            WHERE id = :id
        """)
        db.execute(upd, {
            "id": doc_id,
            "fecha_documento": f,
            "filename": original_name,
            "mime_type": mime_type,
            "size_bytes": size_bytes,
            "storage_key": storage_key,
            "checksum": checksum,
        })
        db.commit()
    except Exception as e:
        db.rollback()
        # Aquí el archivo ya quedó en MinIO. Si querés, luego agregamos limpieza (remove_object).
        print(f"Error actualizando metadata en DB: {e}")
        raise HTTPException(status_code=500, detail="Error actualizando metadata del documento en base de datos")

    return {
        "ok": True,
        "doc_id": doc_id,
        "storage_key": storage_key,
        "filename": original_name,
        "mime_type": mime_type,
        "size_bytes": size_bytes,
        "checksum_sha256": checksum,
        "fecha_documento": str(f),
    }


# ====================================================
# GET: Descargar doc batch (Proxy MinIO -> Usuario)
# ====================================================
@router.get("/batch-documento/{doc_id}/download")
def download_batch_documento(
    doc_id: int,
    db: Session = Depends(get_db),
):
    q = text("""
        SELECT id, storage_key, storage_provider,
               archivo_nombre_original, archivo_mime_type
        FROM sesan_batch_documento
        WHERE id = :id
    """)
    row = db.execute(q, {"id": doc_id}).first()

    if not row:
        raise HTTPException(status_code=404, detail="Documento no encontrado en base de datos")

    storage_key = row.storage_key
    provider = row.storage_provider
    filename = row.archivo_nombre_original
    mime_type = row.archivo_mime_type

    if not storage_key:
        raise HTTPException(status_code=404, detail="El registro existe pero no tiene archivo asociado")
    if provider and provider != "MINIO":
        raise HTTPException(status_code=404, detail="El archivo físico no está disponible en el almacenamiento")

    try:
        if not minio_client:
            raise HTTPException(status_code=500, detail="Servicio de almacenamiento no disponible")

        bucket_name = _get_bucket()
        data_stream = minio_client.get_object(bucket_name, storage_key)

        final_name = filename if filename else f"batch_documento_{doc_id}.dat"
        headers = {"Content-Disposition": f'attachment; filename="{final_name}"'}

        return StreamingResponse(
            data_stream.stream(32 * 1024),
            media_type=mime_type or "application/octet-stream",
            headers=headers
        )

    except Exception as e:
        print(f"Error descargando desde MinIO: {e}")
        raise HTTPException(status_code=404, detail="El archivo físico no se encuentra en el servidor")
