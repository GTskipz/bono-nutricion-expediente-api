from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


# =========================================================
# CREAR LOTE
# =========================================================

class LoteCrearRequest(BaseModel):
    expediente_ids: List[int] = Field(..., min_items=1)
    observacion: Optional[str] = None
    proveedor_servicio: Optional[str] = None  # nuevo opcional


class LoteCrearResponse(BaseModel):
    lote_id: int
    total: int


# =========================================================
# PROCESAR LOTE (nuevo flujo sin XLSX)
# =========================================================

class LoteProcesarResponse(BaseModel):
    lote_id: int
    total_items: int
    cuentas_creadas: int
    rechazados: int
    procesado_en: Optional[datetime] = None


# =========================================================
# LISTADO DE LOTES
# =========================================================

class LoteListItem(BaseModel):
    id: int
    banco_codigo: str
    estado: str
    proveedor_servicio: Optional[str] = None
    creado_por: Optional[str] = None
    creado_en: datetime
    procesado_en: Optional[datetime] = None
    observacion: Optional[str] = None


class LoteListResponse(BaseModel):
    data: List[LoteListItem]
    page: int
    limit: int
    total: int


# =========================================================
# DETALLE DE LOTE (para frontend DetalleLoteApertura)
# =========================================================

class DetalleItemResponse(BaseModel):
    id: int
    expediente_id: int
    estado: str
    nombre_beneficiario: Optional[str]
    cui_beneficiario: Optional[str]
    numero_cuenta: Optional[str]
    motivo_rechazo: Optional[str]
    procesado_en: Optional[datetime]


class LoteDetalleResponse(BaseModel):
    id: int
    banco_codigo: str
    estado: str
    proveedor_servicio: Optional[str]
    creado_en: datetime
    procesado_en: Optional[datetime]
    observacion: Optional[str]
    items: List[DetalleItemResponse]