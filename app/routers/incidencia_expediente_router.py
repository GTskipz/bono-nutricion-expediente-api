from io import BytesIO
from typing import Optional

from fastapi import APIRouter, Depends, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.db import get_db

from app.services.incidencia_expediente_service import (
    crear_incidencia_expediente_core,
    listar_archivos_incidencia_core,
    listar_incidencias_expediente_core,
    listar_tipos_incidencia_core,
    upload_archivo_incidencia_core,
    descargar_archivo_incidencia_core,
    eliminar_archivo_incidencia_core,
    procesar_incidencia_expediente_core,
    cerrar_incidencia_expediente_core,
)

router = APIRouter(prefix="/incidencias", tags=["Incidencias Expediente"])


# ==========================================================
# HELPER USUARIO (TEMPORAL)
# ==========================================================

def get_usuario_id(usuario_id: Optional[int] = None):

    """
    TEMPORAL:
    Si no viene usuario_id desde frontend,
    se usa usuario 1.

    FUTURO:
        auth: AuthContext = Depends(require_auth_context)
        return auth.user.get("id")
    """

    if usuario_id:
        return usuario_id

    # temporal
    return 1

# ==========================================================
# LISTAR INCIDENCIAS POR EXPEDIENTE
# ==========================================================

@router.get("/expediente/{expediente_id}")
def listar_incidencias(
    expediente_id: int,
    db: Session = Depends(get_db),
):
    return listar_incidencias_expediente_core(
        db,
        expediente_id=expediente_id,
    )


# ==========================================================
# CREAR INCIDENCIA
# ==========================================================

@router.post("/")
def crear_incidencia(
    expediente_id: int = Query(...),
    tipo_incidencia_id: int = Query(...),
    descripcion: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):

    usuario = get_usuario_id()

    return crear_incidencia_expediente_core(
        db,
        expediente_id=expediente_id,
        tipo_incidencia_id=tipo_incidencia_id,
        descripcion=descripcion,
        usuario_id=usuario,
    )


# ==========================================================
# SUBIR EVIDENCIA
# ==========================================================

@router.post("/{incidencia_id}/archivo")
async def subir_evidencia(
    incidencia_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):

    usuario = get_usuario_id()

    file_bytes = await file.read()

    return upload_archivo_incidencia_core(
        db,
        incidencia_id=incidencia_id,
        filename=file.filename,
        content_type=file.content_type,
        content=file_bytes,
        usuario_id=usuario,
    )


# ==========================================================
# DESCARGAR EVIDENCIA
# ==========================================================

@router.get("/archivo/{archivo_id}")
def descargar_archivo(
    archivo_id: int,
    db: Session = Depends(get_db),
):

    result = descargar_archivo_incidencia_core(
        db,
        archivo_id=archivo_id,
    )

    return StreamingResponse(
        BytesIO(result["data"]),
        media_type=result["mime_type"],
        headers={
            "Content-Disposition": f'attachment; filename="{result["filename"]}"'
        },
    )


# ==========================================================
# ELIMINAR EVIDENCIA
# ==========================================================

@router.delete("/archivo/{archivo_id}")
def eliminar_archivo(
    archivo_id: int,
    usuario_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):

    usuario = get_usuario_id(usuario_id)

    return eliminar_archivo_incidencia_core(
        db,
        archivo_id=archivo_id,
        usuario_id=usuario,
    )


# ==========================================================
# PROCESAR INCIDENCIA
# ==========================================================

@router.post("/{incidencia_id}/procesar")
def procesar_incidencia(
    incidencia_id: int,
    db: Session = Depends(get_db),
):

    usuario = get_usuario_id()

    return procesar_incidencia_expediente_core(
        db,
        incidencia_id=incidencia_id,
        usuario_id=usuario,
    )


# ==========================================================
# CERRAR INCIDENCIA
# ==========================================================

@router.post("/{incidencia_id}/cerrar")
def cerrar_incidencia(
    incidencia_id: int,
    usuario_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):

    usuario = get_usuario_id(usuario_id)

    return cerrar_incidencia_expediente_core(
        db,
        incidencia_id=incidencia_id,
        usuario_id=usuario,
    )


# ==========================================================
# CATALOGO TIPOS INCIDENCIA
# ==========================================================

@router.get("/tipos")
def listar_tipos_incidencia(
    db: Session = Depends(get_db),
):
    return listar_tipos_incidencia_core(db)


# ==========================================================
# LISTAR ARCHIVOS DE INCIDENCIA
# ==========================================================

@router.get("/{incidencia_id}/archivos")
def listar_archivos_incidencia(
    incidencia_id: int,
    db: Session = Depends(get_db),
):

    return listar_archivos_incidencia_core(
        db,
        incidencia_id=incidencia_id,
    )