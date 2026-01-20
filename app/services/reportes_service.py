from __future__ import annotations

from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import text


class ReportesService:
    def __init__(self, db: Session):
        self.db = db

    def expedientes_totales_por_departamento(self) -> dict:
        """
        Totales de expedientes electrónicos por departamento de residencia.
        - Usa info_general.departamento_residencia_id
        - Incluye departamentos con 0 (LEFT JOIN contra catálogo)
        """

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
