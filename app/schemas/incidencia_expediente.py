from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


# ======================================================
# CATÁLOGO TIPOS DE INCIDENCIA
# ======================================================

class CatIncidenciaExpedienteResponse(BaseModel):

    id: int
    codigo: str
    nombre: str
    descripcion: Optional[str]
    afecta_estado: bool

    class Config:
        from_attributes = True


# ======================================================
# CREAR INCIDENCIA
# ======================================================

class IncidenciaExpedienteCreate(BaseModel):

    expediente_id: int
    tipo_incidencia_id: int
    descripcion: Optional[str] = None


# ======================================================
# RESPUESTA INCIDENCIA
# ======================================================

class IncidenciaExpedienteResponse(BaseModel):

    id: int
    expediente_id: int
    tipo_incidencia_id: int
    descripcion: Optional[str]
    estado: str
    usuario_id: int
    created_at: datetime

    class Config:
        from_attributes = True


# ======================================================
# HISTORIAL INCIDENCIA
# ======================================================

class HistorialIncidenciaResponse(BaseModel):

    id: int
    incidencia_id: int
    accion: str
    descripcion: Optional[str]
    usuario_id: int
    created_at: datetime

    class Config:
        from_attributes = True


# ======================================================
# SUBIR EVIDENCIA
# ======================================================

class IncidenciaArchivoCreate(BaseModel):

    incidencia_id: int
    filename: Optional[str]
    mime_type: Optional[str]
    size_bytes: Optional[int]
    storage_provider: Optional[str]
    storage_key: Optional[str]


# ======================================================
# RESPUESTA EVIDENCIA
# ======================================================

class IncidenciaArchivoResponse(BaseModel):

    id: int
    incidencia_id: int
    filename: Optional[str]
    mime_type: Optional[str]
    size_bytes: Optional[int]
    storage_provider: Optional[str]
    storage_key: Optional[str]
    activo: bool
    usuario_id: int
    created_at: datetime

    class Config:
        from_attributes = True


# ======================================================
# INCIDENCIA COMPLETA
# ======================================================

class IncidenciaDetalleResponse(BaseModel):

    incidencia: IncidenciaExpedienteResponse
    evidencias: List[IncidenciaArchivoResponse] = []
    historial: List[HistorialIncidenciaResponse] = []