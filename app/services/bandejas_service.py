from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from app.models.expediente_electronico import ExpedienteElectronico
from app.models.cat_departamento import CatDepartamento
from app.models.cat_municipio import CatMunicipio
from app.models.cat_estado_flujo_expediente import CatEstadoFlujoExpediente
from app.schemas.expediente import ExpedienteSearchItem, ExpedienteSearchResponse



def buscar_expedientes_por_estado_flujo(
    db: Session,
    *,
    estado_flujo_id: Optional[int] = None,
    estado_flujo_codigo: Optional[str] = None,
    texto: Optional[str] = None,
    departamento_id: Optional[int] = None,
    municipio_id: Optional[int] = None,
    page: int = 1,
    limit: int = 20,
) -> ExpedienteSearchResponse:
    """
    ✅ Genérico para bandejas:
    - Filtra por estado_flujo_id (rápido) o por estado_flujo_codigo (más “humano”).
    - Mantiene la misma estructura de respuesta que tu buscar_expedientes.
    """

    if estado_flujo_id is None and not estado_flujo_codigo:
        # No adivinamos: la bandeja DEBE decir qué estado quiere.
        return ExpedienteSearchResponse(data=[], page=page, limit=limit, total=0)

    texto = (texto or "").strip()
    filters = []

    # ✅ Filtro principal
    if estado_flujo_id is not None:
        filters.append(ExpedienteElectronico.estado_flujo_id == estado_flujo_id)

    # Si viene por código, filtramos por catálogo (join + where)
    # (dejamos outerjoin en la query principal, pero aquí forzamos match)
    if estado_flujo_codigo:
        filters.append(CatEstadoFlujoExpediente.codigo == estado_flujo_codigo)

    # ✅ Búsqueda opcional
    if texto:
        filters.append(
            or_(
                ExpedienteElectronico.nombre_beneficiario.ilike(f"%{texto}%"),
                ExpedienteElectronico.cui_beneficiario.like(f"{texto}%"),
            )
        )

    # ✅ Territorio opcional
    if departamento_id:
        filters.append(ExpedienteElectronico.departamento_id == departamento_id)
    if municipio_id:
        filters.append(ExpedienteElectronico.municipio_id == municipio_id)

    # Total
    total_q = (
        db.query(func.count(ExpedienteElectronico.id))
        .outerjoin(
            CatEstadoFlujoExpediente,
            CatEstadoFlujoExpediente.id == ExpedienteElectronico.estado_flujo_id,
        )
        .filter(*filters)
    )
    total = total_q.scalar() or 0

    offset = (page - 1) * limit

    q = (
        db.query(
            ExpedienteElectronico.id,
            ExpedienteElectronico.created_at,
            ExpedienteElectronico.nombre_beneficiario,
            ExpedienteElectronico.cui_beneficiario,
            ExpedienteElectronico.estado_expediente,
            ExpedienteElectronico.bpm_status,
            ExpedienteElectronico.bpm_current_task_name,

            CatEstadoFlujoExpediente.codigo.label("estado_flujo_codigo"),
            CatEstadoFlujoExpediente.nombre.label("estado_flujo_nombre"),

            CatDepartamento.nombre.label("departamento"),
            CatMunicipio.nombre.label("municipio"),
        )
        .outerjoin(
            CatEstadoFlujoExpediente,
            CatEstadoFlujoExpediente.id == ExpedienteElectronico.estado_flujo_id,
        )
        .outerjoin(CatDepartamento, CatDepartamento.id == ExpedienteElectronico.departamento_id)
        .outerjoin(CatMunicipio, CatMunicipio.id == ExpedienteElectronico.municipio_id)
        .filter(*filters)
        .order_by(ExpedienteElectronico.created_at.desc())
        .offset(offset)
        .limit(limit)
    )

    rows = q.all()

    data = [
        ExpedienteSearchItem(
            id=r.id,
            created_at=r.created_at,
            nombre_beneficiario=r.nombre_beneficiario,
            cui_beneficiario=r.cui_beneficiario,
            estado_expediente=r.estado_expediente,
            bpm_status=r.bpm_status,
            bpm_current_task_name=r.bpm_current_task_name,
            estado_flujo_codigo=getattr(r, "estado_flujo_codigo", None),
            estado_flujo_nombre=getattr(r, "estado_flujo_nombre", None),
            departamento=r.departamento,
            municipio=r.municipio,
        )
        for r in rows
    ]

    return ExpedienteSearchResponse(data=data, page=page, limit=limit, total=total)
