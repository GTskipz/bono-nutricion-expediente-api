from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


class LotePagoCrearRequest(BaseModel):
    expediente_ids: List[int] = Field(..., min_items=1)
    anio_fiscal: int
    mes_fiscal: int = Field(..., ge=1, le=12)
    monto_por_persona: float = Field(..., ge=0)
    tope_anual_persona: float = Field(..., ge=0)
    observacion: Optional[str] = None


class LotePagoCrearResponse(BaseModel):
    lote_id: int
    total: int


class LotePagoProcesarResponse(BaseModel):
    lote_id: int
    total_items: int
    pagados: int
    rechazados: int
    procesado_en: Optional[datetime] = None


class LotePagoListItem(BaseModel):
    id: int
    anio_fiscal: int
    mes_fiscal: int
    banco_codigo: str
    estado: str
    creado_por: Optional[str] = None
    creado_en: datetime
    procesado_en: Optional[datetime] = None
    observacion: Optional[str] = None

    total_items: Optional[int] = None
    pagados: Optional[int] = None
    rechazados: Optional[int] = None


class PageLotePagoListResponse(BaseModel):
    data: List[LotePagoListItem]
    page: int
    limit: int
    total: int


class LotePagoDetalleResponse(BaseModel):
    id: int
    anio_fiscal: int
    mes_fiscal: int
    banco_codigo: str
    estado: str
    creado_por: Optional[str] = None
    creado_en: datetime
    procesado_en: Optional[datetime] = None
    observacion: Optional[str] = None

    monto_por_persona: float
    tope_anual_persona: float

    total_items: int
    pagados: int
    rechazados: int


class LotePagoItem(BaseModel):
    id: int
    lote_id: int
    expediente_id: int
    anio_fiscal: int
    mes_fiscal: int
    estado: str

    monto_asignado: float
    acumulado_pagado_antes: Optional[float] = None
    excede_tope: bool

    cui_beneficiario: Optional[str] = None
    nombre_beneficiario: Optional[str] = None
    banco_codigo: Optional[str] = None
    numero_cuenta: Optional[str] = None

    motivo_rechazo: Optional[str] = None
    referencia_externa: Optional[str] = None
    procesado_en: Optional[datetime] = None


class PageLotePagoItemsResponse(BaseModel):
    data: List[LotePagoItem]
    page: int
    limit: int
    total: int