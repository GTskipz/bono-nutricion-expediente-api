from datetime import datetime
from typing import Dict, Any, Optional
import hashlib
import io
import os

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.core.minio import minio_client

from app.models.incidencia_expediente import (
    CatIncidenciaExpediente,
    IncidenciaExpediente,
    IncidenciaExpedienteArchivo,
    HistorialIncidenciaExpediente,
)

from app.models.expediente_electronico import ExpedienteElectronico
from app.services.tracking_evento_service import TrackingEventoService



# ======================================================
# CREAR INCIDENCIA
# ======================================================
def crear_incidencia_expediente_core(
    db: Session,
    expediente_id: int,
    tipo_incidencia_id: int,
    descripcion: Optional[str],
    usuario_id: int,
) -> Dict[str, Any]:

    expediente = (
        db.query(ExpedienteElectronico)
        .filter(ExpedienteElectronico.id == expediente_id)
        .first()
    )

    if not expediente:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")

    incidencia = IncidenciaExpediente(
        expediente_id=expediente_id,
        tipo_incidencia_id=tipo_incidencia_id,
        descripcion=descripcion,
        estado="ACTIVA",
        usuario_id=usuario_id,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    db.add(incidencia)
    db.flush()

    historial = HistorialIncidenciaExpediente(
        incidencia_id=incidencia.id,
        accion="INCIDENCIA_REGISTRADA",
        usuario_id=usuario_id,
        created_at=datetime.utcnow(),
    )

    db.add(historial)

    db.commit()
    db.refresh(incidencia)

    return {
        "ok": True,
        "incidencia_id": incidencia.id,
        "estado": incidencia.estado,
    }

# ======================================================
# LISTAR INCIDENCIAS POR EXPEDIENTE
# ======================================================
def listar_incidencias_expediente_core(
    db: Session,
    expediente_id: int,
):

    incidencias = (
        db.query(IncidenciaExpediente)
        .filter(IncidenciaExpediente.expediente_id == expediente_id)
        .order_by(IncidenciaExpediente.created_at.desc())
        .all()
    )

    return incidencias


# ======================================================
# SUBIR EVIDENCIA
# ======================================================
def upload_archivo_incidencia_core(
    db: Session,
    incidencia_id: int,
    filename: str,
    content_type: str,
    content: bytes,
    usuario_id: int,
) -> Dict[str, Any]:

    if not filename:
        raise HTTPException(status_code=400, detail="Archivo inválido.")

    size = len(content)
    mime = content_type or "application/octet-stream"
    checksum = hashlib.sha256(content).hexdigest()

    incidencia = (
        db.query(IncidenciaExpediente)
        .filter(IncidenciaExpediente.id == incidencia_id)
        .first()
    )

    if not incidencia:
        raise HTTPException(status_code=404, detail="Incidencia no encontrada")

    # ===============================
    # SUBIR A MINIO
    # ===============================

    try:

        bucket_name = os.getenv("MINIO_BUCKET", "almacenamiento-mis")

        safe_filename = filename.replace(" ", "_")

        storage_key = (
            f"incidencias/"
            f"expediente_{incidencia.expediente_id}/"
            f"incidencia_{incidencia_id}/"
            f"{safe_filename}"
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

    except Exception as e:

        print(f"Error subiendo archivo incidencia: {e}")

        raise HTTPException(
            status_code=500,
            detail="Error guardando el archivo físico."
        )

    # ===============================
    # METADATA
    # ===============================

    archivo = IncidenciaExpedienteArchivo(
        incidencia_id=incidencia_id,
        filename=filename,
        mime_type=mime,
        size_bytes=size,
        storage_provider="MINIO",
        storage_key=storage_key,
        checksum_sha256=checksum,
        usuario_id=usuario_id,
        created_at=datetime.utcnow(),
    )

    db.add(archivo)

    historial = HistorialIncidenciaExpediente(
        incidencia_id=incidencia_id,
        accion="EVIDENCIA_AGREGADA",
        usuario_id=usuario_id,
        created_at=datetime.utcnow(),
    )

    db.add(historial)

    db.commit()
    db.refresh(archivo)

    return {
        "ok": True,
        "archivo_id": archivo.id,
        "filename": archivo.filename,
        "mime_type": archivo.mime_type,
        "size_bytes": archivo.size_bytes,
        "storage_provider": archivo.storage_provider,
        "storage_key": archivo.storage_key,
    }

# ======================================================
# DESCARGAR EVIDENCIA
# ======================================================
def descargar_archivo_incidencia_core(
    db: Session,
    archivo_id: int
) -> Dict[str, Any]:

    archivo = (
        db.query(IncidenciaExpedienteArchivo)
        .filter(IncidenciaExpedienteArchivo.id == archivo_id)
        .first()
    )

    if not archivo:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")

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

        print(f"Error descargando archivo incidencia: {e}")

        raise HTTPException(
            status_code=500,
            detail="Error descargando archivo"
        )

# ======================================================
# BORRAR EVIDENCIA (LOGICO)
# ======================================================
def eliminar_archivo_incidencia_core(
    db: Session,
    archivo_id: int,
    usuario_id: int,
) -> Dict[str, Any]:

    archivo = (
        db.query(IncidenciaExpedienteArchivo)
        .filter(IncidenciaExpedienteArchivo.id == archivo_id)
        .first()
    )

    if not archivo:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")

    archivo.activo = False

    historial = HistorialIncidenciaExpediente(
        incidencia_id=archivo.incidencia_id,
        accion="EVIDENCIA_ELIMINADA",
        usuario_id=usuario_id,
        created_at=datetime.utcnow(),
    )

    db.add(historial)

    db.commit()

    return {
        "ok": True,
        "archivo_id": archivo_id,
        "activo": False,
    }

# ======================================================
# PROCESAR INCIDENCIA
# ======================================================
def procesar_incidencia_expediente_core(
    db: Session,
    incidencia_id: int,
    usuario_id: int,
) -> Dict[str, Any]:

    incidencia = (
        db.query(IncidenciaExpediente)
        .filter(IncidenciaExpediente.id == incidencia_id)
        .first()
    )

    if not incidencia:
        raise HTTPException(status_code=404, detail="Incidencia no encontrada")

    if incidencia.estado != "ACTIVA":
        raise HTTPException(
            status_code=400,
            detail="Solo incidencias activas pueden procesarse"
        )

    # ===============================
    # OBTENER TIPO DE INCIDENCIA
    # ===============================

    tipo = (
        db.query(CatIncidenciaExpediente)
        .filter(CatIncidenciaExpediente.id == incidencia.tipo_incidencia_id)
        .first()
    )

    # ===============================
    # CAMBIO DE ESTADO DEL EXPEDIENTE
    # ===============================

    if tipo and tipo.afecta_estado:

        expediente = (
            db.query(ExpedienteElectronico)
            .filter(ExpedienteElectronico.id == incidencia.expediente_id)
            .first()
        )

        if expediente:

            if tipo.codigo in [
                "MUERTE_BENEFICIARIO",
                "RENUNCIA_PROGRAMA",
                "EXPEDIENTE_DUPLICADO",
            ]:

                expediente.estado_expediente = "SUSPENDIDO"
                expediente.updated_at = datetime.utcnow()

                TrackingEventoService._registrar(
                    db,
                    expediente_id=int(expediente.id),
                    titulo="Expediente suspendido",
                    origen=TrackingEventoService.ORIGEN_INCIDENCIAS,
                    tipo_evento=TrackingEventoService.EXPEDIENTE_SUSPENDIDO,
                    usuario=None,
                    observacion=f"Incidencia procesada: {tipo.nombre}",
                    commit=False,
                )

            elif tipo.codigo == "REACTIVACION_EXPEDIENTE":

                expediente.estado_expediente = "ABIERTO"
                expediente.updated_at = datetime.utcnow()

                TrackingEventoService._registrar(
                    db,
                    expediente_id=int(expediente.id),
                    titulo="Expediente reactivado",
                    origen=TrackingEventoService.ORIGEN_INCIDENCIAS,
                    tipo_evento=TrackingEventoService.EXPEDIENTE_REACTIVADO,
                    usuario=None,
                    observacion=f"Incidencia procesada: {tipo.nombre}",
                    commit=False,
                )

    # ===============================
    # LÓGICA ORIGINAL (NO MODIFICADA)
    # ===============================

    incidencia.estado = "PROCESADA"
    incidencia.updated_at = datetime.utcnow()

    historial = HistorialIncidenciaExpediente(
        incidencia_id=incidencia_id,
        accion="INCIDENCIA_PROCESADA",
        usuario_id=usuario_id,
        created_at=datetime.utcnow(),
    )

    db.add(historial)

    db.commit()
    db.refresh(incidencia)

    return {
        "ok": True,
        "incidencia_id": incidencia.id,
        "estado": incidencia.estado,
    }

# ======================================================
# CERRAR INCIDENCIA
# ======================================================
def cerrar_incidencia_expediente_core(
    db: Session,
    incidencia_id: int,
    usuario_id: int,
) -> Dict[str, Any]:

    incidencia = (
        db.query(IncidenciaExpediente)
        .filter(IncidenciaExpediente.id == incidencia_id)
        .first()
    )

    if not incidencia:
        raise HTTPException(status_code=404, detail="Incidencia no encontrada")

    incidencia.estado = "CERRADA"
    incidencia.updated_at = datetime.utcnow()

    historial = HistorialIncidenciaExpediente(
        incidencia_id=incidencia_id,
        accion="INCIDENCIA_CERRADA",
        usuario_id=usuario_id,
        created_at=datetime.utcnow(),
    )

    db.add(historial)

    db.commit()

    return {
        "ok": True,
        "incidencia_id": incidencia.id,
        "estado": incidencia.estado,
    }

# ======================================================
# CATALOGO
# ======================================================
def listar_tipos_incidencia_core(db: Session):

    return db.query(CatIncidenciaExpediente)\
        .order_by(CatIncidenciaExpediente.nombre)\
        .all()

def listar_archivos_incidencia_core(
    db: Session,
    incidencia_id: int
):

    return (
        db.query(IncidenciaExpedienteArchivo)
        .filter(
            IncidenciaExpedienteArchivo.incidencia_id == incidencia_id,
            IncidenciaExpedienteArchivo.activo == True
        )
        .order_by(IncidenciaExpedienteArchivo.created_at.desc())
        .all()
    )

# ======================================================
# CAMBIO ESTADO
# ======================================================

def suspender_expediente_por_incidencia(db: Session, expediente_id: int):

    row = db.execute(
        text("""
            UPDATE expediente_electronico
            SET estado_expediente = 'SUSPENDIDO',
                updated_at = NOW()
            WHERE id = :id
            RETURNING id, estado_expediente
        """),
        {"id": expediente_id},
    ).mappings().first()

    if not row:
        return None

    # TRACKING
    TrackingEventoService._registrar(
        db,
        expediente_id=int(expediente_id),
        titulo="Expediente suspendido",
        origen=TrackingEventoService.ORIGEN_INCIDENCIAS,
        tipo_evento=TrackingEventoService.EXPEDIENTE_SUSPENDIDO,
        usuario=None,
        observacion="Suspensión por incidencia",
        commit=False,
    )

    db.commit()

    return dict(row)

def activar_expediente_por_incidencia(db: Session, expediente_id: int):

    row = db.execute(
        text("""
            UPDATE expediente_electronico
            SET estado_expediente = 'ABIERTO',
                updated_at = NOW()
            WHERE id = :id
            RETURNING id, estado_expediente
        """),
        {"id": expediente_id},
    ).mappings().first()

    if not row:
        return None

    # TRACKING
    TrackingEventoService._registrar(
        db,
        expediente_id=int(expediente_id),
        titulo="Expediente reactivado",
        origen=TrackingEventoService.ORIGEN_INCIDENCIAS,
        tipo_evento=TrackingEventoService.EXPEDIENTE_REACTIVADO,
        usuario=None,
        observacion="Reactivación por incidencia",
        commit=False,
    )

    db.commit()

    return dict(row)