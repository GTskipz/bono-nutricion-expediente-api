from fastapi import APIRouter, Depends, UploadFile, File, Form
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.services.sesan_documentos_service import (
    upload_batch_documento_service,
    download_batch_documento_service,
)

router = APIRouter(prefix="/sesan-documentos", tags=["SESAN - Documentos"])


@router.post("/batch-documento/{doc_id}/upload")
async def upload_batch_documento(
    doc_id: int,
    fecha_documento: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    return await upload_batch_documento_service(
        db,
        doc_id=doc_id,
        fecha_documento=fecha_documento,
        file=file,
    )


@router.get("/batch-documento/{doc_id}/download")
def download_batch_documento(
    doc_id: int,
    db: Session = Depends(get_db),
):
    return download_batch_documento_service(
        db,
        doc_id=doc_id,
    )