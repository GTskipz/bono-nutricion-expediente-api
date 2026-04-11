from datetime import date
from sqlalchemy.orm import Session
from fastapi import HTTPException
from sqlalchemy import text


def validar_reglas_cronologicas_documento(
    db: Session,
    *,
    batch_id: int,
    tipo_doc_id: int,
    fecha_documento: date,
):
    reglas = db.execute(text("""
        SELECT
            tipo_doc_id,
            tipo_doc_referencia_id,
            operador,
            mensaje_error
        FROM cat_tipo_doc_batch_regla_fecha
        WHERE activo = TRUE
          AND tipo_doc_id = :tipo_doc_id
    """), {
        "tipo_doc_id": tipo_doc_id
    }).fetchall()

    if not reglas:
        return

    docs = db.execute(text("""
        SELECT tipo_doc_id, fecha_documento
        FROM sesan_batch_documento
        WHERE batch_id = :batch_id
          AND fecha_documento IS NOT NULL
    """), {
        "batch_id": batch_id
    }).fetchall()

    fechas = {
        row.tipo_doc_id: row.fecha_documento
        for row in docs
    }

    for regla in reglas:
        fecha_ref = fechas.get(regla.tipo_doc_referencia_id)

        if not fecha_ref:
            continue

        operador = regla.operador
        valido = True

        if operador == ">=":
            valido = fecha_documento >= fecha_ref
        elif operador == "<=":
            valido = fecha_documento <= fecha_ref
        elif operador == ">":
            valido = fecha_documento > fecha_ref
        elif operador == "<":
            valido = fecha_documento < fecha_ref
        elif operador == "=":
            valido = fecha_documento == fecha_ref

        if not valido:
            raise HTTPException(
                status_code=400,
                detail=regla.mensaje_error or "Regla cronológica inválida"
            )