from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Literal
from datetime import datetime


OrigenTracking = Literal["MANUAL", "SISTEMA", "BPM"]


class TrackingCreate(BaseModel):
    titulo: str = Field(..., max_length=255)
    usuario: Optional[str] = Field(default=None, max_length=255)
    observacion: Optional[str] = None

    origen: OrigenTracking = "MANUAL"
    tipo_evento: Optional[str] = None

    fecha_evento: Optional[datetime] = None


class TrackingOut(BaseModel):
    id: int
    expediente_id: int
    created_at: datetime

    fecha_evento: datetime
    titulo: str
    usuario: Optional[str] = None
    observacion: Optional[str] = None

    origen: Optional[str] = None
    tipo_evento: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
