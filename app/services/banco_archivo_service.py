import os
import io
import hashlib

from datetime import datetime
from typing import Optional, Dict, Any, List

from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.core.minio import minio_client

from app.models.banco_archivo_operacion import BancoArchivoOperacion
from app.models.cuentas_bancarias import LoteAperturaCuenta


# ======================================================
# SUBIR ARCHIVO BANCARIO (similar a upload_documento_por_tipo_core)
# ======================================================

def upload_archivo_banco_core(
    db: Session,
    tipo_operacion: str,
    operacion_id: int,
    tipo_archivo: str,
    banco_codigo: str,
    filename: str,
    content_type: str,
    content: bytes,
    observacion: Optional[str] = None,
    descripcion: Optional[str] = None,
    usuario: Optional[str] = None,
) -> Dict[str, Any]:

    if not filename:
        raise HTTPException(status_code=400, detail="Archivo inválido.")

    size = len(content)

    mime = content_type or "application/octet-stream"

    checksum = hashlib.sha256(content).hexdigest()

    # ======================================================
    # crear registro si no existe
    # ======================================================

    archivo = (
        db.query(BancoArchivoOperacion)
        .filter(BancoArchivoOperacion.tipo_operacion == tipo_operacion)
        .filter(BancoArchivoOperacion.operacion_id == operacion_id)
        .filter(BancoArchivoOperacion.tipo_archivo == tipo_archivo)
        .first()
    )

    if not archivo:
        archivo = BancoArchivoOperacion(
            tipo_operacion=tipo_operacion,
            operacion_id=operacion_id,
            tipo_archivo=tipo_archivo,
            banco_codigo=banco_codigo,
            estado="GENERADO",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        db.add(archivo)
        db.flush()

    # ======================================================
    # SUBIR A MINIO
    # ======================================================

    try:

        bucket_name = os.getenv("MINIO_BUCKET", "almacenamiento-mis")

        safe_filename = filename.replace(" ", "_")

        storage_key = (
            f"bancos/"
            f"{tipo_operacion.lower()}/"
            f"operacion_{operacion_id}/"
            f"{tipo_archivo.lower()}_{safe_filename}"
        )

        if not minio_client:
            raise HTTPException(
                status_code=500,
                detail="Servicio de almacenamiento no disponible"
            )

        data_stream = io.BytesIO(content)

        minio_client.put_object(
            bucket_name,
            storage_key,
            data_stream,
            length=size,
            content_type=mime
        )

        archivo.storage_provider = "MINIO"
        archivo.storage_key = storage_key
        archivo.estado = "RECIBIDO"

    except Exception as e:

        print(f"Error subiendo archivo bancario a MinIO: {e}")

        raise HTTPException(
            status_code=500,
            detail="Error guardando el archivo físico en el servidor."
        )

    # ======================================================
    # METADATA
    # ======================================================

    archivo.filename = filename
    archivo.mime_type = mime
    archivo.size_bytes = size
    archivo.checksum_sha256 = checksum
    archivo.subido_por = usuario
    archivo.observacion = observacion
    archivo.descripcion = descripcion
    archivo.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(archivo)

    return {
        "ok": True,
        "id": archivo.id,
        "tipo_operacion": archivo.tipo_operacion,
        "operacion_id": archivo.operacion_id,
        "tipo_archivo": archivo.tipo_archivo,
        "estado": archivo.estado,
        "filename": archivo.filename,
        "mime_type": archivo.mime_type,
        "size_bytes": archivo.size_bytes,
        "storage_provider": archivo.storage_provider,
        "storage_key": archivo.storage_key,
        "checksum_sha256": archivo.checksum_sha256,
        "updated_at": archivo.updated_at,
    }


# ======================================================
# OBTENER ARCHIVO
# ======================================================

def obtener_archivo_banco(
    db: Session,
    archivo_id: int
) -> BancoArchivoOperacion:

    archivo = (
        db.query(BancoArchivoOperacion)
        .filter(BancoArchivoOperacion.id == archivo_id)
        .first()
    )

    if not archivo:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")

    return archivo


# ======================================================
# LISTAR ARCHIVOS POR OPERACION
# ======================================================

def listar_archivos_operacion(
    db: Session,
    tipo_operacion: str,
    operacion_id: int
) -> List[BancoArchivoOperacion]:

    return (
        db.query(BancoArchivoOperacion)
        .filter(BancoArchivoOperacion.tipo_operacion == tipo_operacion)
        .filter(BancoArchivoOperacion.operacion_id == operacion_id)
        .order_by(BancoArchivoOperacion.created_at.desc())
        .all()
    )


# ======================================================
# DESCARGAR ARCHIVO DESDE MINIO
# ======================================================

def descargar_archivo_banco(
    db: Session,
    archivo_id: int
) -> Dict[str, Any]:

    archivo = obtener_archivo_banco(db, archivo_id)

    bucket_name = os.getenv("MINIO_BUCKET", "almacenamiento-mis")

    if not minio_client:
        raise HTTPException(
            status_code=500,
            detail="Servicio de almacenamiento no disponible"
        )

    try:

        response = minio_client.get_object(
            bucket_name,
            archivo.storage_key
        )

        data = response.read()

        return {
            "filename": archivo.filename,
            "mime_type": archivo.mime_type,
            "data": data,
        }

    except Exception as e:

        print(f"Error descargando archivo bancario: {e}")

        raise HTTPException(
            status_code=500,
            detail="Error descargando archivo"
        )
    

def descargar_archivo_operacion(
    db: Session,
    *,
    lote_id: int,
    tipo_archivo: str,  # SOLICITUD | RESPUESTA
):
    """
    Descarga el archivo asociado a un lote de apertura de cuenta
    """

    lote = (
        db.query(LoteAperturaCuenta)
        .filter(LoteAperturaCuenta.id == lote_id)
        .first()
    )

    if not lote:
        raise HTTPException(status_code=404, detail="Lote no encontrado")

    # ======================================================
    # determinar archivo
    # ======================================================

    archivo_id = None

    if tipo_archivo == "SOLICITUD":
        archivo_id = lote.archivo_solicitud_id

    elif tipo_archivo == "RESPUESTA":
        archivo_id = lote.archivo_respuesta_id

    if not archivo_id:
        raise HTTPException(status_code=404, detail="Archivo no disponible")

    archivo = (
        db.query(BancoArchivoOperacion)
        .filter(BancoArchivoOperacion.id == archivo_id)
        .first()
    )

    if not archivo:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")

    bucket_name = os.getenv("MINIO_BUCKET", "almacenamiento-mis")

    try:

        response = minio_client.get_object(
            bucket_name,
            archivo.storage_key
        )

        data = response.read()

        return {
            "filename": archivo.filename,
            "mime_type": archivo.mime_type,
            "data": data,
        }

    except Exception as e:

        print(f"Error descargando archivo bancario: {e}")

        raise HTTPException(
            status_code=500,
            detail="Error descargando archivo"
        )