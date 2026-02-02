from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Any, Dict
from datetime import date, datetime
from enum import Enum


# =========================
# INFO GENERAL
# =========================

class InfoGeneralIn(BaseModel):
    numero: Optional[str] = None
    anio: Optional[str] = None
    mes: Optional[str] = None

    # ✅ Salud (IDs a catálogos)
    area_salud_id: Optional[int] = None
    distrito_salud_id: Optional[int] = None
    servicio_salud_id: Optional[int] = None

    # ✅ Residencia (IDs a catálogos)
    departamento_residencia_id: Optional[int] = None
    municipio_residencia_id: Optional[int] = None
    comunidad_residencia: Optional[str] = None
    direccion_residencia: Optional[str] = None

    # Niño
    cui_del_nino: Optional[str] = None
    sexo_id: Optional[int] = None
    edad_en_anios: Optional[str] = None
    nombre_del_nino: Optional[str] = None

    fecha_nacimiento: Optional[date] = None
    fecha_del_primer_contacto: Optional[date] = None
    fecha_de_registro: Optional[date] = None

    # Diagnóstico
    cie_10: Optional[str] = None
    diagnostico: Optional[str] = None

    # Madre / Padre
    nombre_de_la_madre: Optional[str] = None
    cui_de_la_madre: Optional[str] = None
    nombre_del_padre: Optional[str] = None
    cui_del_padre: Optional[str] = None

    telefonos_encargados: Optional[str] = None

    # ✅ Validación (ID a catálogo)
    validacion_id: Optional[int] = None


class ExpedienteCreate(BaseModel):
    nombre_beneficiario: Optional[str] = None
    cui_beneficiario: Optional[str] = None

    # ✅ NUEVO: RUB (Registro Único de Beneficiario)
    rub: Optional[str] = None

    departamento_id: Optional[int] = None
    municipio_id: Optional[int] = None

    # ✅ NOT NULL en BD, pero lo dejamos opcional (backend hace fallback si no viene)
    anio_carga: Optional[int] = None

    # ✅ puede quedar opcional si el flujo crea expediente primero y luego info_general
    info_general: Optional[InfoGeneralIn] = None


class InfoGeneralOut(InfoGeneralIn):
    id: int
    expediente_id: int

    model_config = ConfigDict(from_attributes=True)


class ExpedienteOut(BaseModel):
    id: int
    created_at: datetime
    updated_at: datetime

    nombre_beneficiario: Optional[str] = None
    cui_beneficiario: Optional[str] = None

    titular_nombre: Optional[str] = None
    titular_dpi: Optional[str] = None

    # ✅ NUEVO: RUB
    rub: Optional[str] = None

    departamento_id: Optional[int] = None
    municipio_id: Optional[int] = None
    estado_expediente: str

    # ✅ NUEVO: nombres de territorio
    departamento: Optional[str] = None
    municipio: Optional[str] = None

    # ✅ si ya lo tienes en tabla:
    docs_required_status: Optional[Dict[str, Any]] = None
    docs_required_state: Optional[str] = None

    info_general: Optional[InfoGeneralOut] = None

    model_config = ConfigDict(from_attributes=True)


# =========================
# SEARCH / BANDEJA MIS
# =========================

class BuscarPor(str, Enum):
    NOMBRE = "NOMBRE"
    DPI = "DPI"


class ExpedienteSearchRequest(BaseModel):
    texto: str | None = ""
    buscar_por: list[BuscarPor] = Field(
        default_factory=lambda: [BuscarPor.NOMBRE, BuscarPor.DPI]
    )
    traer_todos: bool = False

    page: int = Field(default=1, ge=1)
    limit: int = Field(default=10, ge=1, le=50)

class ExpedienteSearchItem(BaseModel):
    id: int
    created_at: Optional[datetime] = None

    nombre_beneficiario: Optional[str] = None
    cui_beneficiario: Optional[str] = None

    titular_nombre: Optional[str] = None
    titular_dpi: Optional[str] = None

    # ✅ Útil en bandeja/búsqueda si lo quieres mostrar o filtrar
    rub: Optional[str] = None

    estado_expediente: Optional[str] = None
    bpm_status: Optional[str] = None
    bpm_current_task_name: Optional[str] = None

    # 🔴 NUEVO: estado de flujo (cat_estado_flujo_expediente)
    estado_flujo_codigo: Optional[str] = None
    estado_flujo_nombre: Optional[str] = None

    # Para mostrar nombre en bandeja (join)
    departamento: Optional[str] = None
    municipio: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ExpedienteSearchResponse(BaseModel):
    data: List[ExpedienteSearchItem]
    page: int
    limit: int
    total: int

class ExpedienteTitularIn(BaseModel):
    titular_nombre: str = Field(..., min_length=3, max_length=160)
    titular_dpi: str = Field(..., min_length=6, max_length=32)