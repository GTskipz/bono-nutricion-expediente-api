from pydantic import BaseModel
from typing import Optional

class EstadoFlujoExpedienteOut(BaseModel):
    id: int
    codigo: str
    nombre: str
    descripcion: Optional[str] = None
    orden: int
    activo: bool

    class Config:
        from_attributes = True
