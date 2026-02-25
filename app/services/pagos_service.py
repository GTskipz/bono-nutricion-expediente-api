from __future__ import annotations

from typing import Optional, List, Tuple
from datetime import datetime
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import String, func, or_, case

from openpyxl import Workbook
from io import BytesIO

from app.models.expediente_electronico import ExpedienteElectronico
from app.models.cat_departamento import CatDepartamento
from app.models.cat_municipio import CatMunicipio
from app.models.cat_estado_flujo_expediente import CatEstadoFlujoExpediente

from app.models.cuentas_bancarias import CuentaBancariaExpediente
from app.models.pagos import LotePago, DetallePago

# ✅ Tracking por expediente (eventos importantes)
from app.services.tracking_evento_service import TrackingEventoService


# -------------------------------------------------
# BANDEJA: expedientes con cuenta bancaria
# -------------------------------------------------
def bandeja_expedientes_con_cuenta(
    db: Session,
    *,
    estado_flujo_codigo: str = "CUENTA_BANCARIA_CREADA",
    texto: Optional[str] = None,
    departamento_id: Optional[int] = None,
    municipio_id: Optional[int] = None,
    page: int = 1,
    limit: int = 20,
):
    texto = (texto or "").strip()

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
            CuentaBancariaExpediente.banco_codigo.label("banco_codigo"),
            CuentaBancariaExpediente.numero_cuenta.label("numero_cuenta"),
        )
        .join(CuentaBancariaExpediente, CuentaBancariaExpediente.expediente_id == ExpedienteElectronico.id)
        .outerjoin(CatEstadoFlujoExpediente, CatEstadoFlujoExpediente.id == ExpedienteElectronico.estado_flujo_id)
        .outerjoin(CatDepartamento, CatDepartamento.id == ExpedienteElectronico.departamento_id)
        .outerjoin(CatMunicipio, CatMunicipio.id == ExpedienteElectronico.municipio_id)
    )

    filters = []

    if estado_flujo_codigo:
        filters.append(CatEstadoFlujoExpediente.codigo == estado_flujo_codigo)

    if texto:
        filters.append(
            or_(
                ExpedienteElectronico.nombre_beneficiario.ilike(f"%{texto}%"),
                ExpedienteElectronico.cui_beneficiario.like(f"{texto}%"),
            )
        )
    if departamento_id:
        filters.append(ExpedienteElectronico.departamento_id == departamento_id)
    if municipio_id:
        filters.append(ExpedienteElectronico.municipio_id == municipio_id)

    total = q.with_entities(func.count(ExpedienteElectronico.id)).filter(*filters).scalar() or 0
    offset = (page - 1) * limit

    rows = (
        q.filter(*filters)
        .order_by(ExpedienteElectronico.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    data = []
    for r in rows:
        data.append({
            "id": r.id,
            "created_at": r.created_at,
            "nombre_beneficiario": r.nombre_beneficiario,
            "cui_beneficiario": r.cui_beneficiario,
            "estado_expediente": r.estado_expediente,
            "bpm_status": r.bpm_status,
            "bpm_current_task_name": r.bpm_current_task_name,
            "estado_flujo_codigo": getattr(r, "estado_flujo_codigo", None),
            "estado_flujo_nombre": getattr(r, "estado_flujo_nombre", None),
            "departamento": r.departamento,
            "municipio": r.municipio,
            "banco_codigo": getattr(r, "banco_codigo", None),
            "numero_cuenta": getattr(r, "numero_cuenta", None),
        })

    return {"data": data, "page": page, "limit": limit, "total": total}


# -------------------------------------------------
# CREAR LOTE + ITEMS (snapshot mínimo)
# -------------------------------------------------
def crear_lote_pago(
    db: Session,
    *,
    expediente_ids: List[int],
    anio_fiscal: int,
    mes_fiscal: int,
    monto_por_persona: float,
    tope_anual_persona: float,
    creado_por: Optional[str] = None,
    observacion: Optional[str] = None,
) -> Tuple[int, int]:

    rows = (
        db.query(
            ExpedienteElectronico.id,
            ExpedienteElectronico.cui_beneficiario,
            ExpedienteElectronico.nombre_beneficiario,
            CatDepartamento.nombre.label("departamento"),
            CatMunicipio.nombre.label("municipio"),
            CuentaBancariaExpediente.banco_codigo.label("banco_codigo"),
            CuentaBancariaExpediente.numero_cuenta.label("numero_cuenta"),
        )
        .join(CuentaBancariaExpediente, CuentaBancariaExpediente.expediente_id == ExpedienteElectronico.id)
        .outerjoin(CatDepartamento, CatDepartamento.id == ExpedienteElectronico.departamento_id)
        .outerjoin(CatMunicipio, CatMunicipio.id == ExpedienteElectronico.municipio_id)
        .filter(ExpedienteElectronico.id.in_(expediente_ids))
        .all()
    )

    found_ids = {r.id for r in rows}
    missing = [i for i in expediente_ids if i not in found_ids]
    if missing:
        raise HTTPException(status_code=404, detail=f"Expedientes no encontrados o sin cuenta: {missing[:20]}")

    lote = LotePago(
        anio_fiscal=anio_fiscal,
        mes_fiscal=mes_fiscal,
        monto_por_persona=monto_por_persona,
        tope_anual_persona=tope_anual_persona,
        banco_codigo="BANRURAL",
        estado="CREADO",
        creado_por=creado_por,
        observacion=observacion,
    )
    db.add(lote)
    db.flush()

    # ✅ Crear items
    for r in rows:
        db.add(DetallePago(
            lote_id=lote.id,
            expediente_id=r.id,
            anio_fiscal=anio_fiscal,
            mes_fiscal=mes_fiscal,
            estado="PENDIENTE",
            monto_asignado=monto_por_persona,
            cui_beneficiario=r.cui_beneficiario,
            nombre_beneficiario=r.nombre_beneficiario,
            banco_codigo=r.banco_codigo or "BANRURAL",
            numero_cuenta=r.numero_cuenta,
        ))

        # ✅ TRACKING IMPORTANTE: intento de pago (por expediente)
        TrackingEventoService._registrar(
            db,
            expediente_id=int(r.id),
            titulo="Intento de pago",
            origen=TrackingEventoService.ORIGEN_PAGOS,
            tipo_evento=TrackingEventoService.PAGO_INTENTO,
            usuario=creado_por,
            observacion=f"Lote #{lote.id} | Periodo {anio_fiscal}-{mes_fiscal:02d} | Monto Q{float(monto_por_persona):,.2f}",
            commit=False,
        )

    db.commit()
    return lote.id, len(rows)


# -------------------------------------------------
# LISTAR LOTES (paginado + filtros)
# -------------------------------------------------
def listar_lotes_pago(
    db: Session,
    *,
    anio: Optional[int] = None,
    mes: Optional[int] = None,
    estado: Optional[str] = None,
    texto: Optional[str] = None,
    page: int = 1,
    limit: int = 20,
):
    texto = (texto or "").strip()
    offset = (page - 1) * limit

    q = db.query(LotePago)

    if anio:
        q = q.filter(LotePago.anio_fiscal == anio)
    if mes:
        q = q.filter(LotePago.mes_fiscal == mes)
    if estado:
        q = q.filter(LotePago.estado == estado)

    if texto:
        q = q.filter(
            or_(
                func.cast(LotePago.id, String).ilike(f"%{texto}%"),
                LotePago.estado.ilike(f"%{texto}%"),
                (LotePago.creado_por.ilike(f"%{texto}%") if LotePago.creado_por is not None else False),
                (LotePago.observacion.ilike(f"%{texto}%") if LotePago.observacion is not None else False),
            )
        )

    total = q.with_entities(func.count(LotePago.id)).scalar() or 0
    lotes = q.order_by(LotePago.creado_en.desc()).offset(offset).limit(limit).all()

    lote_ids = [l.id for l in lotes]
    counts_map = {lid: {"total_items": 0, "pagados": 0, "rechazados": 0} for lid in lote_ids}

    if lote_ids:
        agg = (
            db.query(
                DetallePago.lote_id.label("lote_id"),
                func.count(DetallePago.id).label("total_items"),
                func.coalesce(func.sum(case((DetallePago.estado == "PAGADO", 1), else_=0)), 0).label("pagados"),
                func.coalesce(func.sum(case((DetallePago.estado == "RECHAZADO", 1), else_=0)), 0).label("rechazados"),
            )
            .filter(DetallePago.lote_id.in_(lote_ids))
            .group_by(DetallePago.lote_id)
            .all()
        )
        for r in agg:
            counts_map[r.lote_id] = {
                "total_items": int(r.total_items or 0),
                "pagados": int(r.pagados or 0),
                "rechazados": int(r.rechazados or 0),
            }

    data = []
    for l in lotes:
        c = counts_map.get(l.id, {"total_items": 0, "pagados": 0, "rechazados": 0})
        data.append({
            "id": l.id,
            "anio_fiscal": l.anio_fiscal,
            "mes_fiscal": l.mes_fiscal,
            "banco_codigo": l.banco_codigo,
            "estado": l.estado,
            "creado_por": l.creado_por,
            "creado_en": l.creado_en,
            "procesado_en": l.procesado_en,
            "observacion": l.observacion,
            **c,
        })

    return {"data": data, "page": page, "limit": limit, "total": total}


# -------------------------------------------------
# OBTENER DETALLE DE LOTE
# -------------------------------------------------
def obtener_lote_pago(db: Session, *, lote_id: int) -> dict:
    lote = db.query(LotePago).filter(LotePago.id == lote_id).first()
    if not lote:
        raise HTTPException(status_code=404, detail="Lote no encontrado")

    agg = (
        db.query(
            func.count(DetallePago.id).label("total_items"),
            func.coalesce(func.sum(case((DetallePago.estado == "PAGADO", 1), else_=0)), 0).label("pagados"),
            func.coalesce(func.sum(case((DetallePago.estado == "RECHAZADO", 1), else_=0)), 0).label("rechazados"),
        )
        .filter(DetallePago.lote_id == lote_id)
        .first()
    )

    return {
        "id": lote.id,
        "anio_fiscal": lote.anio_fiscal,
        "mes_fiscal": lote.mes_fiscal,
        "banco_codigo": lote.banco_codigo,
        "estado": lote.estado,
        "creado_por": lote.creado_por,
        "creado_en": lote.creado_en,
        "procesado_en": lote.procesado_en,
        "observacion": lote.observacion,
        "monto_por_persona": float(lote.monto_por_persona),
        "tope_anual_persona": float(lote.tope_anual_persona),
        "total_items": int(getattr(agg, "total_items", 0) or 0),
        "pagados": int(getattr(agg, "pagados", 0) or 0),
        "rechazados": int(getattr(agg, "rechazados", 0) or 0),
    }


# -------------------------------------------------
# LISTAR ITEMS DE LOTE
# -------------------------------------------------
def listar_items_lote_pago(db: Session, *, lote_id: int, page: int = 1, limit: int = 50) -> dict:
    exists = db.query(LotePago.id).filter(LotePago.id == lote_id).first()
    if not exists:
        raise HTTPException(status_code=404, detail="Lote no encontrado")

    base_q = db.query(DetallePago).filter(DetallePago.lote_id == lote_id)
    total = base_q.with_entities(func.count(DetallePago.id)).scalar() or 0
    offset = (page - 1) * limit

    rows = (
        base_q.order_by(DetallePago.id.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    data = []
    for it in rows:
        data.append({
            "id": it.id,
            "lote_id": it.lote_id,
            "expediente_id": it.expediente_id,
            "anio_fiscal": it.anio_fiscal,
            "mes_fiscal": it.mes_fiscal,
            "estado": it.estado,
            "monto_asignado": float(it.monto_asignado),
            "acumulado_pagado_antes": float(it.acumulado_pagado_antes) if it.acumulado_pagado_antes is not None else None,
            "excede_tope": bool(it.excede_tope),
            "cui_beneficiario": it.cui_beneficiario,
            "nombre_beneficiario": it.nombre_beneficiario,
            "banco_codigo": it.banco_codigo,
            "numero_cuenta": it.numero_cuenta,
            "motivo_rechazo": it.motivo_rechazo,
            "referencia_externa": it.referencia_externa,
            "procesado_en": it.procesado_en,
        })

    return {"data": data, "page": page, "limit": limit, "total": total}


# -------------------------------------------------
# PROCESAR LOTE (SIMULADO) + VALIDACIÓN TOPE ANUAL
# -------------------------------------------------
def procesar_lote_pago_simulado(db: Session, *, lote_id: int) -> dict:
    lote = db.query(LotePago).filter(LotePago.id == lote_id).first()
    if not lote:
        raise HTTPException(status_code=404, detail="Lote no encontrado")

    if (lote.estado or "").upper() == "PROCESADO":
        # Idempotente: devuelve resumen actual (no vuelve a registrar tracking)
        agg = (
            db.query(
                func.count(DetallePago.id).label("total_items"),
                func.coalesce(func.sum(case((DetallePago.estado == "PAGADO", 1), else_=0)), 0).label("pagados"),
                func.coalesce(func.sum(case((DetallePago.estado == "RECHAZADO", 1), else_=0)), 0).label("rechazados"),
            )
            .filter(DetallePago.lote_id == lote_id)
            .first()
        )
        return {
            "lote_id": lote_id,
            "total_items": int(getattr(agg, "total_items", 0) or 0),
            "pagados": int(getattr(agg, "pagados", 0) or 0),
            "rechazados": int(getattr(agg, "rechazados", 0) or 0),
            "procesado_en": lote.procesado_en,
        }

    now = datetime.utcnow()

    items = (
        db.query(DetallePago)
        .filter(DetallePago.lote_id == lote_id)
        .order_by(DetallePago.id.asc())
        .all()
    )

    total_items = len(items)
    pagados = 0
    rechazados = 0

    for it in items:
        if (it.estado or "").upper() not in ("PENDIENTE", ""):
            continue

        try:
            # acumulado anual pagado (solo items PAGADO del mismo expediente/año)
            acumulado = (
                db.query(func.coalesce(func.sum(DetallePago.monto_asignado), 0))
                .filter(
                    DetallePago.expediente_id == it.expediente_id,
                    DetallePago.anio_fiscal == lote.anio_fiscal,
                    DetallePago.estado == "PAGADO",
                )
                .scalar()
                or 0
            )

            it.acumulado_pagado_antes = acumulado
            it.actualizado_en = now

            monto = float(it.monto_asignado)
            tope = float(lote.tope_anual_persona)

            if (acumulado + monto) > tope:
                it.estado = "RECHAZADO"
                it.excede_tope = True
                it.motivo_rechazo = "EXCEDE_TOPE_ANUAL"
                it.response_status_code = 409
                it.response_payload = {
                    "ok": False,
                    "reason": "EXCEDE_TOPE_ANUAL",
                    "acumulado": float(acumulado),
                    "monto": monto,
                    "tope": tope,
                }
                it.procesado_en = now
                rechazados += 1

                # ✅ TRACKING IMPORTANTE: excede tope (por expediente)
                TrackingEventoService._registrar(
                    db,
                    expediente_id=int(it.expediente_id),
                    titulo="Pago rechazado por exceder tope anual",
                    origen=TrackingEventoService.ORIGEN_PAGOS,
                    tipo_evento=TrackingEventoService.PAGO_EXCEDE_TOPE,
                    usuario=None,
                    observacion=f"Lote #{lote.id} | Periodo {lote.anio_fiscal}-{lote.mes_fiscal:02d} | Acumulado Q{float(acumulado):,.2f} | Monto Q{monto:,.2f} | Tope Q{tope:,.2f}",
                    commit=False,
                )
                continue

            # ✅ Simulación de “consumo”
            ref = f"SIM-{uuid4().hex[:12].upper()}"
            it.estado = "PAGADO"
            it.excede_tope = False
            it.motivo_rechazo = None
            it.referencia_externa = ref
            it.proveedor_servicio = it.proveedor_servicio or lote.proveedor_servicio or "SIMULADO"
            it.response_status_code = 200
            it.response_payload = {"ok": True, "referencia": ref}
            it.procesado_en = now
            pagados += 1

            # ✅ TRACKING IMPORTANTE: pago aprobado (por expediente)
            TrackingEventoService._registrar(
                db,
                expediente_id=int(it.expediente_id),
                titulo="Pago aprobado",
                origen=TrackingEventoService.ORIGEN_PAGOS,
                tipo_evento=TrackingEventoService.PAGO_APROBADO,
                usuario=None,
                observacion=f"Lote #{lote.id} | Periodo {lote.anio_fiscal}-{lote.mes_fiscal:02d} | Monto Q{monto:,.2f} | Ref {ref}",
                commit=False,
            )

            # ---------------------------------------------------------
            # (FUTURO) Consumo real del servicio externo (DEJAR COMENTADO)
            # ---------------------------------------------------------
            # payload = {...}
            # resp = external_client.post(..., json=payload)
            # it.request_payload = payload
            # it.response_payload = resp.json()
            # it.response_status_code = resp.status_code
            # if resp.ok: PAGADO else RECHAZADO
            # ---------------------------------------------------------

        except Exception as e:
            # ✅ TRACKING IMPORTANTE: error técnico (por expediente)
            TrackingEventoService._registrar(
                db,
                expediente_id=int(it.expediente_id),
                titulo="Error técnico en proceso de pago",
                origen=TrackingEventoService.ORIGEN_PAGOS,
                tipo_evento=TrackingEventoService.PAGO_ERROR,
                usuario=None,
                observacion=str(e)[:500],
                commit=False,
            )

            # Estado de item (si quieres mantenerlo pendiente o marcarlo rechazado)
            it.estado = "RECHAZADO"
            it.excede_tope = False
            it.motivo_rechazo = "ERROR_TECNICO"
            it.response_status_code = 500
            it.response_payload = {"ok": False, "reason": "ERROR_TECNICO"}
            it.procesado_en = now
            rechazados += 1

    lote.estado = "PROCESADO"
    lote.procesado_en = now
    lote.total_items = total_items
    lote.pagados = pagados
    lote.rechazados = rechazados

    db.commit()

    return {
        "lote_id": lote_id,
        "total_items": total_items,
        "pagados": pagados,
        "rechazados": rechazados,
        "procesado_en": now,
    }


# -------------------------------------------------
# EXCEL EXPORT (NO solicitud, solo export evidencia)
# -------------------------------------------------
def generar_excel_lote_pago_export_bytes(db: Session, *, lote_id: int) -> bytes:
    lote = db.query(LotePago).filter(LotePago.id == lote_id).first()
    if not lote:
        raise HTTPException(status_code=404, detail="Lote no encontrado")

    items = (
        db.query(DetallePago)
        .filter(DetallePago.lote_id == lote_id)
        .order_by(DetallePago.id.asc())
        .all()
    )

    wb = Workbook()
    ws = wb.active
    ws.title = "PAGOS_EXPORT"

    headers = [
        "lote_id",
        "anio_fiscal",
        "mes_fiscal",
        "expediente_id",
        "cui_beneficiario",
        "nombre_beneficiario",
        "banco_codigo",
        "numero_cuenta",
        "monto_asignado",
        "acumulado_pagado_antes",
        "tope_anual",
        "estado",
        "motivo_rechazo",
        "referencia_externa",
        "procesado_en",
        "creado_en",
    ]
    ws.append(headers)

    for it in items:
        ws.append([
            lote.id,
            lote.anio_fiscal,
            lote.mes_fiscal,
            it.expediente_id,
            it.cui_beneficiario,
            it.nombre_beneficiario,
            it.banco_codigo,
            it.numero_cuenta,
            float(it.monto_asignado),
            float(it.acumulado_pagado_antes) if it.acumulado_pagado_antes is not None else None,
            float(lote.tope_anual_persona),
            it.estado,
            it.motivo_rechazo,
            it.referencia_externa,
            it.procesado_en.isoformat() if it.procesado_en else None,
            it.creado_en.isoformat() if it.creado_en else None,
        ])

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()