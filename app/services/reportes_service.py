from __future__ import annotations

from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import text


class ReportesService:
    def __init__(self, db: Session):
        self.db = db

    def expedientes_totales_por_departamento(self) -> dict:
        # (tu método actual se queda igual)
        sql = text("""
            SELECT
              d.id     AS departamento_id,
              d.nombre AS departamento,
              d.codigo AS codigo,
              COALESCE(COUNT(e.id), 0) AS total_expedientes
            FROM cat_departamento d
            LEFT JOIN info_general ig
              ON ig.departamento_residencia_id = d.id
            LEFT JOIN expediente_electronico e
              ON e.id = ig.expediente_id
            GROUP BY d.id, d.nombre, d.codigo
            ORDER BY d.nombre;
        """)
        rows = self.db.execute(sql).mappings().all()

        items = [
            {
                "departamento_id": int(r["departamento_id"]),
                "departamento": r["departamento"],
                "codigo": r["codigo"],
                "total_expedientes": int(r["total_expedientes"] or 0),
            }
            for r in rows
        ]

        total = sum(x["total_expedientes"] for x in items)

        return {
            "total": total,
            "items": items,
            "generado_en": datetime.utcnow().isoformat(),
        }

    # ✅ NUEVO: listado para tabla
    def expedientes_listado_por_departamento(
        self,
        departamento_id: int,
        texto: str = "",
        estado_flujo_codigo: str | None = None,
        page: int = 1,
        limit: int = 10,
    ) -> dict:
        """
        Listado de expedientes por departamento de residencia (info_general.departamento_residencia_id).
        Devuelve shape tipo bandeja: { data, page, limit, total }
        Incluye campos útiles para 'ver expediente' (solo lectura).
        """
        offset = (page - 1) * limit
        q = (texto or "").strip()

        where = ["ig.departamento_residencia_id = :departamento_id"]
        params: dict = {
            "departamento_id": departamento_id,
            "limit": limit,
            "offset": offset,
        }

        if q:
            where.append("""
                (
                  COALESCE(e.nombre_beneficiario,'') ILIKE :q
                  OR COALESCE(e.cui_beneficiario,'') ILIKE :q
                  OR COALESCE(e.rub,'') ILIKE :q
                )
            """)
            params["q"] = f"%{q}%"

        if estado_flujo_codigo:
            where.append("ef.codigo = :estado_flujo_codigo")
            params["estado_flujo_codigo"] = estado_flujo_codigo

        where_sql = " AND ".join(where)

        # TOTAL
        total_sql = text(f"""
            SELECT COUNT(1)
            FROM expediente_electronico e
            JOIN info_general ig ON ig.expediente_id = e.id
            LEFT JOIN cat_departamento d ON d.id = ig.departamento_residencia_id
            LEFT JOIN cat_municipio m ON m.id = ig.municipio_residencia_id
            LEFT JOIN cat_estado_flujo_expediente ef ON ef.id = e.estado_flujo_id
            WHERE {where_sql}
        """)
        total = int(self.db.execute(total_sql, params).scalar() or 0)

        # DATA
        data_sql = text(f"""
            SELECT
              e.id,
              e.created_at,

              e.nombre_beneficiario,
              e.cui_beneficiario,
              e.rub,

              ef.codigo AS estado_flujo_codigo,
              ef.nombre AS estado_flujo_nombre,

              d.nombre AS departamento,
              m.nombre AS municipio,

              e.titular_nombre,
              e.titular_dpi

            FROM expediente_electronico e
            JOIN info_general ig ON ig.expediente_id = e.id
            LEFT JOIN cat_departamento d ON d.id = ig.departamento_residencia_id
            LEFT JOIN cat_municipio m ON m.id = ig.municipio_residencia_id
            LEFT JOIN cat_estado_flujo_expediente ef ON ef.id = e.estado_flujo_id

            WHERE {where_sql}
            ORDER BY e.created_at DESC, e.id DESC
            LIMIT :limit OFFSET :offset
        """)

        rows = self.db.execute(data_sql, params).mappings().all()

        # Shape "bandeja": data/page/limit/total
        data = [
            {
                "id": int(r["id"]),
                "created_at": r["created_at"],

                "nombre_beneficiario": r["nombre_beneficiario"],
                "cui_beneficiario": r["cui_beneficiario"],
                "rub": r["rub"],

                # Bandeja MIS (estado)
                "estado_flujo_codigo": r["estado_flujo_codigo"],
                "estado_flujo_nombre": r["estado_flujo_nombre"],

                # Join territorio
                "departamento": r["departamento"],
                "municipio": r["municipio"],

                # Extra útil para modal (solo lectura)
                "titular_nombre": r["titular_nombre"],
                "titular_dpi": r["titular_dpi"],
            }
            for r in rows
        ]

        return {
            "data": data,
            "page": page,
            "limit": limit,
            "total": total,
        }
