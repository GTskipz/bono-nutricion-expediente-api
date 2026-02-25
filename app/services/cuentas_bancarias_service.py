# app/services/cuentas_bancarias_service.py
from __future__ import annotations

from functools import partial
from typing import Optional, List, Tuple
from datetime import datetime
import anyio
from openpyxl import Workbook
from io import BytesIO

import random
import string

from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, case

from app.models.expediente_electronico import ExpedienteElectronico
from app.models.cat_departamento import CatDepartamento
from app.models.cat_municipio import CatMunicipio
from app.models.cat_estado_flujo_expediente import CatEstadoFlujoExpediente

from app.bpm.bpm_service_task_data import BpmServiceTaskData

from app.models.cuentas_bancarias import (
    LoteAperturaCuenta,
    DetalleAperturaCuenta,
    CuentaBancariaExpediente,
)

# ✅ Tracking por expediente (eventos importantes)
from app.services.tracking_evento_service import TrackingEventoService


# =========================================================
# BANDEJA (expedientes por estado_flujo_id)
# =========================================================
def bandeja_expedientes_por_estado_flujo(
    db: Session,
    *,
    estado_flujo_id: int,
    texto: Optional[str] = None,
    departamento_id: Optional[int] = None,
    municipio_id: Optional[int] = None,
    page: int = 1,
    limit: int = 20,
):
    texto = (texto or "").strip()
    filters = [ExpedienteElectronico.estado_flujo_id == estado_flujo_id]

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

    total = (
        db.query(func.count(ExpedienteElectronico.id))
        .filter(*filters)
        .scalar()
        or 0
    )

    offset = (page - 1) * limit

    rows = (
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
        })

    return {"data": data, "page": page, "limit": limit, "total": total}


# =========================================================
# CREAR LOTE + ITEMS (snapshot)
# =========================================================
def crear_lote_apertura(
    db: Session,
    *,
    expediente_ids: List[int],
    creado_por: Optional[str] = None,
    observacion: Optional[str] = None,
    proveedor_servicio: Optional[str] = None,
) -> Tuple[int, int]:
    exp_rows = (
        db.query(
            ExpedienteElectronico.id,
            ExpedienteElectronico.cui_beneficiario,
            ExpedienteElectronico.nombre_beneficiario,
            CatDepartamento.nombre.label("departamento"),
            CatMunicipio.nombre.label("municipio"),
        )
        .outerjoin(CatDepartamento, CatDepartamento.id == ExpedienteElectronico.departamento_id)
        .outerjoin(CatMunicipio, CatMunicipio.id == ExpedienteElectronico.municipio_id)
        .filter(ExpedienteElectronico.id.in_(expediente_ids))
        .all()
    )

    found_ids = {r.id for r in exp_rows}
    missing = [i for i in expediente_ids if i not in found_ids]
    if missing:
        raise HTTPException(status_code=404, detail=f"Expedientes no encontrados: {missing[:20]}")

    lote = LoteAperturaCuenta(
        banco_codigo="BANRURAL",
        estado="CREADO",
        creado_por=creado_por,
        observacion=observacion,
        proveedor_servicio=proveedor_servicio,
    )
    db.add(lote)
    db.flush()

    for r in exp_rows:
        item = DetalleAperturaCuenta(
            lote_id=lote.id,
            expediente_id=r.id,
            estado="PENDIENTE",
            cui_beneficiario=r.cui_beneficiario,
            nombre_beneficiario=r.nombre_beneficiario,
            titular_dpi=r.cui_beneficiario,         # placeholder (ajustar cuando exista tabla contacto/titular real)
            titular_nombre=r.nombre_beneficiario,   # placeholder
            departamento=r.departamento,
            municipio=r.municipio,
            direccion=None,
            telefono=None,
        )
        db.add(item)

        # ✅ TRACKING IMPORTANTE: intento creación de cuenta (por expediente)
        TrackingEventoService._registrar(
            db,
            expediente_id=int(r.id),
            titulo="Intento de creación de cuenta bancaria",
            origen=TrackingEventoService.ORIGEN_CUENTAS,
            tipo_evento=TrackingEventoService.CUENTA_INTENTO,
            usuario=creado_por,
            observacion=f"Lote apertura #{lote.id}",
            commit=False,
        )

    db.commit()
    return lote.id, len(exp_rows)


# =========================================================
# LISTAR LOTES (paginado + filtro año)
# =========================================================
def listar_lotes_apertura(
    db: Session,
    *,
    anio: Optional[int] = None,
    estado: Optional[str] = None,
    texto: Optional[str] = None,
    page: int = 1,
    limit: int = 20,
):
    texto = (texto or "").strip()
    offset = (page - 1) * limit

    q = db.query(LoteAperturaCuenta)

    # filtro año: usa anio si existe, si no usa created_at o creado_en
    if anio:
        if hasattr(LoteAperturaCuenta, "anio"):
            q = q.filter(getattr(LoteAperturaCuenta, "anio") == anio)
        elif hasattr(LoteAperturaCuenta, "created_at"):
            q = q.filter(func.extract("year", getattr(LoteAperturaCuenta, "created_at")) == anio)
        elif hasattr(LoteAperturaCuenta, "creado_en"):
            q = q.filter(func.extract("year", getattr(LoteAperturaCuenta, "creado_en")) == anio)
        else:
            raise HTTPException(status_code=400, detail="No hay columna anio/created_at/creado_en para filtrar por año.")

    if estado:
        q = q.filter(LoteAperturaCuenta.estado == estado)

    if texto:
        conds = []
        if hasattr(LoteAperturaCuenta, "banco_codigo"):
            conds.append(LoteAperturaCuenta.banco_codigo.ilike(f"%{texto}%"))
        if hasattr(LoteAperturaCuenta, "creado_por"):
            conds.append(LoteAperturaCuenta.creado_por.ilike(f"%{texto}%"))
        if hasattr(LoteAperturaCuenta, "observacion"):
            conds.append(LoteAperturaCuenta.observacion.ilike(f"%{texto}%"))
        if hasattr(LoteAperturaCuenta, "estado"):
            conds.append(LoteAperturaCuenta.estado.ilike(f"%{texto}%"))
        if conds:
            q = q.filter(or_(*conds))

    total = q.with_entities(func.count(LoteAperturaCuenta.id)).scalar() or 0

    # orden seguro
    if hasattr(LoteAperturaCuenta, "created_at"):
        q = q.order_by(getattr(LoteAperturaCuenta, "created_at").desc())
    elif hasattr(LoteAperturaCuenta, "creado_en"):
        q = q.order_by(getattr(LoteAperturaCuenta, "creado_en").desc())
    else:
        q = q.order_by(LoteAperturaCuenta.id.desc())

    lotes = q.offset(offset).limit(limit).all()

    lote_ids = [l.id for l in lotes]
    counts_map = {lid: {"total_items": 0, "cuentas_creadas": 0, "rechazados": 0} for lid in lote_ids}

    if lote_ids:
        agg = (
            db.query(
                DetalleAperturaCuenta.lote_id.label("lote_id"),
                func.count(DetalleAperturaCuenta.id).label("total_items"),
                func.coalesce(
                    func.sum(case((DetalleAperturaCuenta.estado == "CUENTA_CREADA", 1), else_=0)),
                    0,
                ).label("cuentas_creadas"),
                func.coalesce(
                    func.sum(case((DetalleAperturaCuenta.estado == "RECHAZADO", 1), else_=0)),
                    0,
                ).label("rechazados"),
            )
            .filter(DetalleAperturaCuenta.lote_id.in_(lote_ids))
            .group_by(DetalleAperturaCuenta.lote_id)
            .all()
        )
        for r in agg:
            counts_map[r.lote_id] = {
                "total_items": int(r.total_items or 0),
                "cuentas_creadas": int(r.cuentas_creadas or 0),
                "rechazados": int(r.rechazados or 0),
            }

    data = []
    for l in lotes:
        data.append({
            "id": l.id,
            "banco_codigo": getattr(l, "banco_codigo", None),
            "estado": getattr(l, "estado", None),
            "proveedor_servicio": getattr(l, "proveedor_servicio", None),
            "creado_por": getattr(l, "creado_por", None),
            "observacion": getattr(l, "observacion", None),
            "created_at": getattr(l, "created_at", None),
            "creado_en": getattr(l, "creado_en", None),
            "procesado_en": getattr(l, "procesado_en", None),
            "anio": getattr(l, "anio", None) if hasattr(l, "anio") else None,
            **counts_map.get(l.id, {"total_items": 0, "cuentas_creadas": 0, "rechazados": 0}),
        })

    return {"data": data, "page": page, "limit": limit, "total": total}


# =========================================================
# OBTENER DETALLE DE LOTE (resumen)
# =========================================================
def obtener_lote_apertura(db: Session, *, lote_id: int) -> dict:
    lote = db.query(LoteAperturaCuenta).filter(LoteAperturaCuenta.id == lote_id).first()
    if not lote:
        raise HTTPException(status_code=404, detail="Lote no encontrado")

    agg = (
        db.query(
            func.count(DetalleAperturaCuenta.id).label("total_items"),
            func.coalesce(
                func.sum(case((DetalleAperturaCuenta.estado == "CUENTA_CREADA", 1), else_=0)),
                0,
            ).label("cuentas_creadas"),
            func.coalesce(
                func.sum(case((DetalleAperturaCuenta.estado == "RECHAZADO", 1), else_=0)),
                0,
            ).label("rechazados"),
        )
        .filter(DetalleAperturaCuenta.lote_id == lote_id)
        .first()
    )

    return {
        "id": lote.id,
        "banco_codigo": getattr(lote, "banco_codigo", None),
        "estado": getattr(lote, "estado", None),
        "proveedor_servicio": getattr(lote, "proveedor_servicio", None),
        "creado_por": getattr(lote, "creado_por", None),
        "observacion": getattr(lote, "observacion", None),
        "created_at": getattr(lote, "created_at", None),
        "creado_en": getattr(lote, "creado_en", None),
        "procesado_en": getattr(lote, "procesado_en", None),
        "anio": getattr(lote, "anio", None) if hasattr(lote, "anio") else None,
        "total_items": int(getattr(agg, "total_items", 0) or 0),
        "cuentas_creadas": int(getattr(agg, "cuentas_creadas", 0) or 0),
        "rechazados": int(getattr(agg, "rechazados", 0) or 0),
    }


# =========================================================
# LISTAR ITEMS DE UN LOTE (paginado)
# =========================================================
def listar_items_lote(
    db: Session,
    *,
    lote_id: int,
    page: int = 1,
    limit: int = 50,
):
    exists = db.query(LoteAperturaCuenta.id).filter(LoteAperturaCuenta.id == lote_id).first()
    if not exists:
        raise HTTPException(status_code=404, detail="Lote no encontrado")

    base_q = db.query(DetalleAperturaCuenta).filter(DetalleAperturaCuenta.lote_id == lote_id)

    total = base_q.with_entities(func.count(DetalleAperturaCuenta.id)).scalar() or 0
    offset = (page - 1) * limit

    items = (
        base_q.order_by(DetalleAperturaCuenta.id.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    data = []
    for it in items:
        data.append({
            "id": it.id,
            "lote_id": it.lote_id,
            "expediente_id": it.expediente_id,
            "estado": getattr(it, "estado", None),
            "cui_beneficiario": getattr(it, "cui_beneficiario", None),
            "nombre_beneficiario": getattr(it, "nombre_beneficiario", None),
            "titular_dpi": getattr(it, "titular_dpi", None),
            "titular_nombre": getattr(it, "titular_nombre", None),
            "departamento": getattr(it, "departamento", None),
            "municipio": getattr(it, "municipio", None),
            "direccion": getattr(it, "direccion", None),
            "telefono": getattr(it, "telefono", None),
            "numero_cuenta": getattr(it, "numero_cuenta", None),
            "motivo_rechazo": getattr(it, "motivo_rechazo", None),

            # campos nuevos integración
            "proveedor_servicio": getattr(it, "proveedor_servicio", None),
            "referencia_externa": getattr(it, "referencia_externa", None),
            "request_payload": getattr(it, "request_payload", None),
            "response_payload": getattr(it, "response_payload", None),
            "response_status_code": getattr(it, "response_status_code", None),
            "error_servicio": getattr(it, "error_servicio", None),
            "procesado_en": getattr(it, "procesado_en", None),

            "creado_en": getattr(it, "creado_en", None),
            "actualizado_en": getattr(it, "actualizado_en", None),
        })

    return {"data": data, "page": page, "limit": limit, "total": total}


# =========================================================
# PROCESAR LOTE (SIMULADO) - NUEVO FLUJO (SIN XLSX)
# =========================================================
def procesar_lote_apertura_simulado(db: Session, *, lote_id: int) -> dict:
    """
    Procesa el lote consultando BPM (Spiff) para verificar resultado bancario.
    - Consulta task-data por expediente (BpmServiceTaskData)
    - Si hay cuenta válida => CUENTA_CREADA + upsert CuentaBancariaExpediente + estado_flujo CUENTA_BANCARIA_CREADA
    - Si NO hay info bancaria => RECHAZADO + tracking error + regresar expediente a DOCS_CARGADOS
    - Si error técnico consultando BPM => RECHAZADO + tracking error + regresar expediente a DOCS_CARGADOS
    - Actualiza lote a PROCESADO
    """

    lote = db.query(LoteAperturaCuenta).filter(LoteAperturaCuenta.id == lote_id).first()
    if not lote:
        raise HTTPException(status_code=404, detail="Lote no encontrado")

    if getattr(lote, "estado", None) not in ["CREADO", "EXCEL_GENERADO", "RESPUESTA_CARGADA"]:
        raise HTTPException(status_code=400, detail="El lote no está en un estado válido para procesar")

    items = (
        db.query(DetalleAperturaCuenta)
        .filter(DetalleAperturaCuenta.lote_id == lote_id)
        .order_by(DetalleAperturaCuenta.id.asc())
        .all()
    )

    total_items = len(items)
    cuentas_creadas = 0
    rechazados = 0

    # precargar estados
    estado_ok = (
        db.query(CatEstadoFlujoExpediente)
        .filter(CatEstadoFlujoExpediente.codigo == "CUENTA_BANCARIA_CREADA")
        .first()
    )
    estado_error = (
        db.query(CatEstadoFlujoExpediente)
        .filter(CatEstadoFlujoExpediente.codigo == "ERROR_CUENTA_BANCARIA")
        .first()
    )
    estado_docs_cargados = (
        db.query(CatEstadoFlujoExpediente)
        .filter(CatEstadoFlujoExpediente.codigo == "DOCS_CARGADOS")
        .first()
    )

    now = datetime.utcnow()
    bpm_service = BpmServiceTaskData(db)

    def _safe_get(d, path, default=None):
        cur = d
        for k in path:
            if not isinstance(cur, dict):
                return default
            cur = cur.get(k)
        return cur if cur is not None else default

    def _extraer_info_banco(task_data_wrapper: dict) -> dict:
        """
        task_data_wrapper es lo que retorna BpmServiceTaskData:
        - por instancia: {"bpm_instance_id":..., "task_guid":..., "data": <task-data-json>}
        - por expediente: {"expediente_id":..., "bpm_instance_id":..., "task_guid":..., "data": <task-data-json>}
        En tu ejemplo, el task-data-json trae:
        data -> { ... "data": { ... variables ... } }
        y ahí viene: banco.body / datos_banco / respuesta_banco / numero_cuenta_final / fecha_apertura
        """
        task_data_json = task_data_wrapper.get("data") or {}
        variables = _safe_get(task_data_json, ["data"], {})  # <- aquí está el gran "data" de variables

        # posibles ubicaciones
        banco_body = _safe_get(variables, ["banco", "body"], {}) or {}
        datos_banco = variables.get("datos_banco") or variables.get("respuesta_banco") or {}
        numero_cuenta = (
            variables.get("numero_cuenta_final")
            or datos_banco.get("numeroCuenta")
            or banco_body.get("numeroCuenta")
        )
        cuenta_id = datos_banco.get("cuentaId") or banco_body.get("cuentaId")
        fecha_apertura = (
            variables.get("fecha_apertura")
            or datos_banco.get("fechaApertura")
            or banco_body.get("fechaApertura")
        )
        codigo = datos_banco.get("codigo") or banco_body.get("codigo")
        mensaje = (
            datos_banco.get("mensaje")
            or variables.get("mensaje_servicio")
            or variables.get("estado_apertura")
            or banco_body.get("mensaje")
        )
        exitoso = datos_banco.get("exitoso")
        if exitoso is None:
            exitoso = banco_body.get("exitoso")

        return {
            "exitoso": bool(exitoso) if exitoso is not None else False,
            "numero_cuenta": numero_cuenta,
            "cuenta_id": cuenta_id,
            "fecha_apertura": fecha_apertura,
            "codigo": codigo,
            "mensaje": mensaje,
            "variables": variables,
            "raw_task_data": task_data_json,
        }

    for item in items:
        if (getattr(item, "estado", None) or "").upper() not in ("PENDIENTE", ""):
            continue

        item.procesado_en = now
        item.proveedor_servicio = getattr(lote, "proveedor_servicio", None) or "BPM_SPIFF"
        item.actualizado_en = now

        # request_payload real (auditoría)
        item.request_payload = {
            "expediente_id": item.expediente_id,
            "cui": item.cui_beneficiario,
            "titular_dpi": item.titular_dpi,
            "lote_id": lote.id,
            "tipo": "CONSULTA_BPM_TASK_DATA_BANCO",
        }

        try:
            # 🔥 Consulta BPM (async) desde función sync
            task_data_wrapper = anyio.run(
                partial(bpm_service.obtener_task_data_por_expediente_id, expediente_id=int(item.expediente_id))
            )

            info = _extraer_info_banco(task_data_wrapper)

            # guardar respuesta completa para auditoría
            item.response_payload = task_data_wrapper
            item.response_status_code = 200
            item.referencia_externa = info.get("cuenta_id") or task_data_wrapper.get("task_guid")

            # ✅ Éxito si hay número y exitoso
            if info["exitoso"] and info["numero_cuenta"]:
                numero_cuenta = str(info["numero_cuenta"]).strip()

                item.estado = "CUENTA_CREADA"
                item.numero_cuenta = numero_cuenta
                item.motivo_rechazo = None
                item.error_servicio = None

                cuentas_creadas += 1

                # upsert en cuenta_bancaria_expediente
                existing = (
                    db.query(CuentaBancariaExpediente)
                    .filter(CuentaBancariaExpediente.expediente_id == item.expediente_id)
                    .first()
                )
                if existing:
                    existing.numero_cuenta = numero_cuenta
                    existing.titular_dpi = item.titular_dpi
                    existing.titular_nombre = item.titular_nombre
                    existing.detalle_apertura_id = item.id
                    existing.cuenta_asignada_en = now
                    existing.banco_codigo = getattr(lote, "banco_codigo", None) or existing.banco_codigo
                else:
                    db.add(
                        CuentaBancariaExpediente(
                            expediente_id=item.expediente_id,
                            banco_codigo=getattr(lote, "banco_codigo", None) or "BANRURAL",
                            numero_cuenta=numero_cuenta,
                            titular_dpi=item.titular_dpi,
                            titular_nombre=item.titular_nombre,
                            detalle_apertura_id=item.id,
                        )
                    )

                # actualizar estado del expediente => CUENTA_BANCARIA_CREADA
                if estado_ok:
                    db.query(ExpedienteElectronico).filter(
                        ExpedienteElectronico.id == item.expediente_id
                    ).update({"estado_flujo_id": estado_ok.id})

                TrackingEventoService._registrar(
                    db,
                    expediente_id=int(item.expediente_id),
                    titulo="Cuenta bancaria verificada",
                    origen=TrackingEventoService.ORIGEN_CUENTAS,
                    tipo_evento=TrackingEventoService.CUENTA_CREADA,
                    usuario=getattr(lote, "creado_por", None),
                    observacion=f"Lote apertura #{lote.id} | Cuenta: {numero_cuenta}",
                    commit=False,
                )

            else:
                # ❌ No hay info bancaria válida -> error negocio
                item.estado = "RECHAZADO"
                item.numero_cuenta = None
                item.motivo_rechazo = "SIN_INFO_BANCARIA_EN_BPM"
                item.error_servicio = "SIN_INFO_BANCARIA_EN_BPM"

                rechazados += 1

                # 🔁 regresar expediente a DOCS_CARGADOS (regla tuya)
                if estado_docs_cargados:
                    db.query(ExpedienteElectronico).filter(
                        ExpedienteElectronico.id == item.expediente_id
                    ).update({"estado_flujo_id": estado_docs_cargados.id})
                elif estado_error:
                    # fallback si no existe DOCS_CARGADOS en catálogo
                    db.query(ExpedienteElectronico).filter(
                        ExpedienteElectronico.id == item.expediente_id
                    ).update({"estado_flujo_id": estado_error.id})

                TrackingEventoService._registrar(
                    db,
                    expediente_id=int(item.expediente_id),
                    titulo="No se recibió información bancaria desde BPM",
                    origen=TrackingEventoService.ORIGEN_CUENTAS,
                    tipo_evento=TrackingEventoService.CUENTA_ERROR,
                    usuario=getattr(lote, "creado_por", None),
                    observacion=f"Lote #{lote.id} | Regreso a DOCS_CARGADOS",
                    commit=False,
                )

        except Exception as e:
            # ❌ Error técnico consultando BPM -> regresar a DOCS_CARGADOS
            TrackingEventoService._registrar(
                db,
                expediente_id=int(item.expediente_id),
                titulo="Error técnico consultando BPM para verificación bancaria",
                origen=TrackingEventoService.ORIGEN_CUENTAS,
                tipo_evento=TrackingEventoService.CUENTA_ERROR,
                usuario=getattr(lote, "creado_por", None),
                observacion=str(e)[:500],
                commit=False,
            )

            item.estado = "RECHAZADO"
            item.numero_cuenta = None
            item.motivo_rechazo = "ERROR_TECNICO_BPM"
            item.response_payload = {"error": "ERROR_TECNICO_BPM", "detail": str(e)[:500]}
            item.response_status_code = 500
            item.error_servicio = "ERROR_TECNICO_BPM"
            item.referencia_externa = item.referencia_externa or f"BPM-{item.id}"
            item.procesado_en = now
            item.actualizado_en = now

            rechazados += 1

            if estado_docs_cargados:
                db.query(ExpedienteElectronico).filter(
                    ExpedienteElectronico.id == item.expediente_id
                ).update({"estado_flujo_id": estado_docs_cargados.id})
            elif estado_error:
                db.query(ExpedienteElectronico).filter(
                    ExpedienteElectronico.id == item.expediente_id
                ).update({"estado_flujo_id": estado_error.id})

    # estado del lote
    lote.estado = "PROCESADO"
    lote.procesado_en = now
    if getattr(lote, "proveedor_servicio", None) is None:
        lote.proveedor_servicio = "BPM_SPIFF"

    db.commit()

    return {
        "lote_id": lote_id,
        "total_items": total_items,
        "cuentas_creadas": cuentas_creadas,
        "rechazados": rechazados,
    }

def generar_excel_lote_export_bytes(db: Session, *, lote_id: int) -> bytes:
    lote = db.query(LoteAperturaCuenta).filter(LoteAperturaCuenta.id == lote_id).first()
    if not lote:
        raise HTTPException(status_code=404, detail="Lote no encontrado")

    items = (
        db.query(DetalleAperturaCuenta)
        .filter(DetalleAperturaCuenta.lote_id == lote_id)
        .order_by(DetalleAperturaCuenta.id.asc())
        .all()
    )

    wb = Workbook()
    ws = wb.active
    ws.title = "LOTE_EXPORT"

    headers = [
        "lote_id",
        "banco_codigo",
        "estado_lote",
        "proveedor_servicio_lote",
        "creado_en",
        "procesado_en_lote",

        "item_id",
        "expediente_id",
        "estado_item",

        "cui_beneficiario",
        "nombre_beneficiario",
        "titular_dpi",
        "titular_nombre",
        "departamento",
        "municipio",
        "direccion",
        "telefono",

        "numero_cuenta",
        "motivo_rechazo",

        "proveedor_servicio_item",
        "referencia_externa",
        "response_status_code",
        "error_servicio",
        "procesado_en_item",
        "actualizado_en",
    ]
    ws.append(headers)

    for it in items:
        ws.append([
            lote.id,
            getattr(lote, "banco_codigo", None),
            getattr(lote, "estado", None),
            getattr(lote, "proveedor_servicio", None),
            getattr(lote, "creado_en", None),
            getattr(lote, "procesado_en", None),

            it.id,
            it.expediente_id,
            getattr(it, "estado", None),

            it.cui_beneficiario,
            it.nombre_beneficiario,
            it.titular_dpi,
            it.titular_nombre,
            it.departamento,
            it.municipio,
            it.direccion,
            it.telefono,

            it.numero_cuenta,
            it.motivo_rechazo,

            getattr(it, "proveedor_servicio", None),
            getattr(it, "referencia_externa", None),
            getattr(it, "response_status_code", None),
            getattr(it, "error_servicio", None),
            getattr(it, "procesado_en", None),
            getattr(it, "actualizado_en", None),
        ])

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


# =========================================================
# DEPRECADO (referencia) - EXCEL SOLICITUD / XLSX RESPUESTA
# =========================================================
"""
# -----------------------------
# GENERAR EXCEL SOLICITUD (stream)  [DEPRECADO]
# -----------------------------
from openpyxl import Workbook
from io import BytesIO

def generar_excel_solicitud_bytes(db: Session, *, lote_id: int) -> bytes:
    ...

# -----------------------------
# PROCESAR RESPUESTA DEL BANCO XLSX [DEPRECADO]
# -----------------------------
def procesar_respuesta_banco_xlsx(db: Session, *, lote_id: int, file_bytes: bytes) -> dict:
    ...
"""