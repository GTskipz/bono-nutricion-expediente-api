from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db

from app.schemas.cat_departamento import DepartamentoOut
from app.schemas.cat_municipio import MunicipioOut
from app.schemas.cat_tipo_documento import TipoDocumentoOut
from app.schemas.cat_area_salud import AreaSaludOut
from app.schemas.cat_distrito_salud import DistritoSaludOut
from app.schemas.cat_servicio_salud import ServicioSaludOut
from app.schemas.cat_sexo import SexoOut
from app.schemas.cat_estado_flujo_expediente import EstadoFlujoExpedienteOut

from app.services.catalogos_service import (
    get_departamentos,
    get_municipios,
    get_tipos_documento_activos,
    get_areas_salud,
    get_distritos_salud,
    get_servicios_salud,
    get_sexos,
    get_tipos_documento_public,
    get_estados_flujo_expediente
)

router = APIRouter(prefix="/catalogos", tags=["Catálogos"])


@router.get("/departamentos", response_model=list[DepartamentoOut])
def listar_departamentos(db: Session = Depends(get_db)):
    return get_departamentos(db)


@router.get("/municipios", response_model=list[MunicipioOut])
def listar_municipios(
    departamento_id: int = Query(..., description="ID del departamento"),
    db: Session = Depends(get_db),
):
    return get_municipios(db, departamento_id)


@router.get("/tipos-documento", response_model=list[TipoDocumentoOut])
def listar_tipos_documento_activos(db: Session = Depends(get_db)):
    return get_tipos_documento_activos(db)


@router.get("/areas-salud", response_model=list[AreaSaludOut])
def listar_areas_salud(db: Session = Depends(get_db)):
    return get_areas_salud(db)


@router.get("/distritos-salud", response_model=list[DistritoSaludOut])
def listar_distritos_salud(
    area_salud_id: int = Query(..., description="ID del área de salud"),
    db: Session = Depends(get_db),
):
    return get_distritos_salud(db, area_salud_id)


@router.get("/servicios-salud", response_model=list[ServicioSaludOut])
def listar_servicios_salud(
    distrito_salud_id: int = Query(..., description="ID del distrito de salud"),
    db: Session = Depends(get_db),
):
    return get_servicios_salud(db, distrito_salud_id)


@router.get("/sexos", response_model=list[SexoOut])
def listar_sexos(
    solo_activos: bool = Query(True, description="Si true, retorna solo activos"),
    db: Session = Depends(get_db),
):
    return get_sexos(db, solo_activos)


# ⚠️ Nota: esta ruta en tu router original queda como "/catalogos/catalogos/tipos-documento"
# porque ya tienes prefix="/catalogos". Mantengo exactamente el path para no romper frontend,
# pero te recomiendo luego cambiarlo a "/tipos-documento-public" o similar.
@router.get("/catalogos/tipos-documento")
def listar_tipos_documento_publico(
    obligatorios: bool = Query(True, description="true=solo obligatorios"),
    activos: bool = Query(True, description="true=solo activos"),
    db: Session = Depends(get_db),
):
    return get_tipos_documento_public(db, obligatorios=obligatorios, activos=activos)

@router.get("/estado-flujo-expediente", response_model=list[EstadoFlujoExpedienteOut])
def listar_estados_flujo_expediente(
    solo_activos: bool = Query(True, description="Si true, retorna solo activos"),
    db: Session = Depends(get_db),
):
    return get_estados_flujo_expediente(db, solo_activos=solo_activos)