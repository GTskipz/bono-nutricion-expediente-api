from __future__ import annotations

from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from app.models.cat_departamento import CatDepartamento
from app.models.cat_municipio import CatMunicipio
from app.models.cat_tipo_documento import CatTipoDocumento
from app.models.cat_area_salud import CatAreaSalud
from app.models.cat_distrito_salud import CatDistritoSalud
from app.models.cat_servicio_salud import CatServicioSalud
from app.models.cat_sexo import CatSexo


def get_departamentos(db: Session) -> List[CatDepartamento]:
    return db.query(CatDepartamento).order_by(CatDepartamento.nombre.asc()).all()


def get_municipios(db: Session, departamento_id: int) -> List[CatMunicipio]:
    return (
        db.query(CatMunicipio)
        .filter(CatMunicipio.departamento_id == departamento_id)
        .order_by(CatMunicipio.nombre.asc())
        .all()
    )


def get_tipos_documento_activos(db: Session) -> List[CatTipoDocumento]:
    return (
        db.query(CatTipoDocumento)
        .filter(CatTipoDocumento.activo.is_(True))
        .order_by(CatTipoDocumento.orden.asc())
        .all()
    )


def get_areas_salud(db: Session) -> List[CatAreaSalud]:
    return db.query(CatAreaSalud).order_by(CatAreaSalud.nombre.asc()).all()


def get_distritos_salud(db: Session, area_salud_id: int) -> List[CatDistritoSalud]:
    return (
        db.query(CatDistritoSalud)
        .filter(CatDistritoSalud.area_salud_id == area_salud_id)
        .order_by(CatDistritoSalud.nombre.asc())
        .all()
    )


def get_servicios_salud(db: Session, distrito_salud_id: int) -> List[CatServicioSalud]:
    return (
        db.query(CatServicioSalud)
        .filter(CatServicioSalud.distrito_salud_id == distrito_salud_id)
        .order_by(CatServicioSalud.nombre.asc())
        .all()
    )


def get_sexos(db: Session, solo_activos: bool = True) -> List[CatSexo]:
    q = db.query(CatSexo)
    if solo_activos:
        q = q.filter(CatSexo.activo.is_(True))
    return q.order_by(CatSexo.nombre.asc()).all()


def get_tipos_documento_public(
    db: Session,
    obligatorios: bool = True,
    activos: bool = True,
) -> List[Dict[str, Any]]:
    """
    Endpoint "public" que devuelve campos específicos en dict (no ORM),
    útil para combos sin response_model rígido.
    """
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

    rows = q.order_by(
        CatTipoDocumento.orden.asc().nullslast(),
        CatTipoDocumento.id.asc()
    ).all()

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
