from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class BancoArchivoOperacionOut(BaseModel):

    id: int
    tipo_operacion: str
    operacion_id: int
    tipo_archivo: str

    banco_codigo: Optional[str]

    filename: Optional[str]
    mime_type: Optional[str]
    size_bytes: Optional[int]

    storage_provider: Optional[str]
    storage_key: Optional[str]

    estado: str

    created_at: datetime

    class Config:
        orm_mode = True