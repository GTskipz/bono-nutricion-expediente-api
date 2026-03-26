from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
from datetime import datetime


# =========================
# FILTROS DINAMICOS
# =========================

class FiltroPago(BaseModel):
    codigo: str
    valor: Any


class FiltroPagoOpcion(BaseModel):
    valor: Any
    etiqueta: str


class FiltroPagoResponse(BaseModel):
    codigo: str
    nombre: str
    descripcion: Optional[str] = None
    tipo_control: str
    opciones: Optional[List[FiltroPagoOpcion]] = None


# =========================
# PREVISUALIZACION DEL LOTE
# =========================

class LotePagoPreviewRequest(BaseModel):
    anio_fiscal: int
    mes_fiscal: int = Field(..., ge=1, le=12)

    monto_por_persona: float = Field(..., ge=0)
    tope_anual_persona: float = Field(..., ge=0)

    presupuesto_total: float = Field(..., ge=0)

    filtros: Dict[str, Any]


class LotePagoPreviewResponse(BaseModel):
    beneficiarios_encontrados: int
    beneficiarios_posibles: int
    monto_estimado: float


# =========================
# CREAR LOTE (NUEVO FLUJO)
# =========================

class UbicacionFiltro(BaseModel):
    departamento_id: int
    municipios: List[int] = []

class LotePagoCrearPorFiltrosRequest(BaseModel):
    anio_fiscal: int
    mes_fiscal: int = Field(..., ge=1, le=12)

    monto_por_persona: float = Field(..., ge=0)
    tope_anual_persona: float = Field(..., ge=0)

    presupuesto_total: float = Field(..., ge=0)

    numero_pago: int
    ubicaciones: Optional[List[UbicacionFiltro]] = None

    observacion: Optional[str] = None

# =========================
# RESPUESTA CREAR LOTE
# =========================

class LotePagoCrearResponse(BaseModel):
    lote_id: int
    total: int


# =========================
# PROCESAR LOTE
# =========================

class LotePagoProcesarResponse(BaseModel):
    lote_id: int
    total_items: int
    pagados: int
    rechazados: int
    procesado_en: Optional[datetime] = None


# =========================
# LISTADO DE LOTES
# =========================

class LotePagoListItem(BaseModel):

    model_config = ConfigDict(from_attributes=True)

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


# =========================
# DETALLE DEL LOTE
# =========================

class LotePagoDetalleResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)

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
    presupuesto_total: Optional[float] = None
    monto_usado: Optional[float] = None

    total_items: int
    pagados: int
    rechazados: int


# =========================
# ITEMS DEL LOTE
# =========================

class LotePagoItem(BaseModel):

    model_config = ConfigDict(from_attributes=True)

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

class ExportBeneficiariosRequest(BaseModel):
    numero_pago: int
    ubicaciones: list | None = None