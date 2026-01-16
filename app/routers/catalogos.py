from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.models.cat_departamento import CatDepartamento
from app.schemas.cat_departamento import DepartamentoOut
from app.models.cat_municipio import CatMunicipio
from app.schemas.cat_municipio import MunicipioOut
from app.models.cat_tipo_documento import CatTipoDocumento
from app.schemas.cat_tipo_documento import TipoDocumentoOut
from app.models.cat_area_salud import CatAreaSalud
from app.schemas.cat_area_salud import AreaSaludOut
from app.models.cat_distrito_salud import CatDistritoSalud
from app.schemas.cat_distrito_salud import DistritoSaludOut
from app.models.cat_servicio_salud import CatServicioSalud
from app.schemas.cat_servicio_salud import ServicioSaludOut
from app.models.cat_sexo import CatSexo
from app.schemas.cat_sexo import SexoOut
from fastapi import Query

router = APIRouter(prefix="/catalogos", tags=["Catálogos"])

@router.get("/departamentos", response_model=list[DepartamentoOut])
def listar_departamentos(db: Session = Depends(get_db)):
    return db.query(CatDepartamento).order_by(CatDepartamento.nombre.asc()).all()

@router.get("/municipios", response_model=list[MunicipioOut])
def listar_municipios(
    departamento_id: int = Query(..., description="ID del departamento"),
    db: Session = Depends(get_db),
):
    return (
        db.query(CatMunicipio)
        .filter(CatMunicipio.departamento_id == departamento_id)
        .order_by(CatMunicipio.nombre.asc())
        .all()
    )

@router.get("/tipos-documento", response_model=list[TipoDocumentoOut])
def listar_tipos_documento(db: Session = Depends(get_db)):
    return (
        db.query(CatTipoDocumento)
        .filter(CatTipoDocumento.activo.is_(True))
        .order_by(CatTipoDocumento.orden.asc())
        .all()
    )

@router.get("/areas-salud", response_model=list[AreaSaludOut])
def listar_areas_salud(db: Session = Depends(get_db)):
    return db.query(CatAreaSalud).order_by(CatAreaSalud.nombre.asc()).all()


@router.get("/distritos-salud", response_model=list[DistritoSaludOut])
def listar_distritos_salud(
    area_salud_id: int = Query(..., description="ID del área de salud"),
    db: Session = Depends(get_db),
):
    return (
        db.query(CatDistritoSalud)
        .filter(CatDistritoSalud.area_salud_id == area_salud_id)
        .order_by(CatDistritoSalud.nombre.asc())
        .all()
    )


@router.get("/servicios-salud", response_model=list[ServicioSaludOut])
def listar_servicios_salud(
    distrito_salud_id: int = Query(..., description="ID del distrito de salud"),
    db: Session = Depends(get_db),
):
    return (
        db.query(CatServicioSalud)
        .filter(CatServicioSalud.distrito_salud_id == distrito_salud_id)
        .order_by(CatServicioSalud.nombre.asc())
        .all()
    )


@router.get("/sexos", response_model=list[SexoOut])
def listar_sexos(
    solo_activos: bool = Query(True, description="Si true, retorna solo activos"),
    db: Session = Depends(get_db),
):
    q = db.query(CatSexo)
    if solo_activos:
        q = q.filter(CatSexo.activo.is_(True))
    return q.order_by(CatSexo.nombre.asc()).all()

@router.get("/catalogos/tipos-documento")
def listar_tipos_documento(
    obligatorios: bool = Query(True, description="true=solo obligatorios"),
    activos: bool = Query(True, description="true=solo activos"),
    db: Session = Depends(get_db),
):
    q = db.query(
        CatTipoDocumento.id,
        CatTipoDocumento.codigo,
        CatTipoDocumento.nombre,
        CatTipoDocumento.es_obligatorio,
        CatTipoDocumento.orden,
        CatTipoDocumento.activo,
    )

    if obligatorios:
        q = q.filter(CatTipoDocumento.es_obligatorio.is_(True))

    if activos:
        q = q.filter(CatTipoDocumento.activo.is_(True))

    rows = q.order_by(CatTipoDocumento.orden.asc().nullslast(), CatTipoDocumento.id.asc()).all()

    return [
        {
            "id": r.id,
            "codigo": r.codigo,
            "nombre": r.nombre,
            "es_obligatorio": r.es_obligatorio,
            "orden": r.orden,
            "activo": r.activo,
        }
        for r in rows
    ]

