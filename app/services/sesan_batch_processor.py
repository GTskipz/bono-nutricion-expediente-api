import json

from sqlalchemy import text
from sqlalchemy.orm import Session
import asyncio

from app.core.db import SessionLocal
from app.bpm.bpm_client import BpmClient
from app.bpm.bpm_payload_builder import build_spiff_payload_from_staging_row
from app.services.utils import norm_lookup, norm_str, to_cui, to_int


MAX_WORKERS = 3


class SesanBatchProcessor:

    def __init__(self, bpm_service=None):
        self.bpm = bpm_service or BpmClient()

    # ==========================================================
    # Procesar lote
    # ==========================================================
    async def procesar_lote(self, row_ids: list[int], usuario_id: str | None = None):

        semaphore = asyncio.Semaphore(MAX_WORKERS)

        async def worker(rid):

            async with semaphore:
                await self.procesar_row(rid, usuario_id)

        await asyncio.gather(*(worker(r) for r in row_ids), return_exceptions=True)


    # ==========================================================
    # Procesar fila
    # ==========================================================
    async def procesar_row(self, row_id: int, usuario_id: str | None = None):

        db: Session = SessionLocal()

        try:

            print(f"[SESAN] ▶️ Procesando row_id={row_id}")

            row = db.execute(
                text("""
                    SELECT
                        s.*,
                        b.anio_carga,
                        b.mes_carga
                    FROM sesan_staging s
                    JOIN sesan_batch b ON b.id = s.batch_id
                    WHERE s.id = :id
                """),
                {"id": row_id},
            ).mappings().first()

            if not row:
                print(f"[SESAN] ⚠️ Row {row_id} no encontrado.")
                return

            if row["estado"] == "IGNORADO":
                print(f"[SESAN] ⚠️ Row {row_id} ignorado por el usuario.")
                return

            if row["estado"] == "PROCESADO" and row.get("expediente_id"):
                print(f"[SESAN] ⚠️ Row {row_id} ya procesado.")
                return

            anio_carga = int(row["anio_carga"])
            mes_carga = int(row["mes_carga"]) if row.get("mes_carga") else None

            rub = row.get("rub")

            cui = to_cui(row.get("cui_nino"))
            nombre = norm_str(row.get("nombre_nino"))

            print(f"[SESAN] Datos básicos -> año={anio_carga} mes={mes_carga} rub={rub} cui={cui} nombre={nombre}")

            if not cui:
                raise ValueError(
                    "MISSING_CUI|El registro no contiene CUI del beneficiario. "
                    "No es posible continuar con el procesamiento."
                )

            if not nombre:
                raise ValueError(
                    "MISSING_NAME|El registro no contiene el nombre del beneficiario."
                )

            if self._is_dup_cui_in_year(db, cui, anio_carga, row_id):
                raise ValueError(
                    f"DUP_CUI_BATCH|El CUI {cui} aparece duplicado dentro del mismo archivo SESAN."
                )

            if self._is_dup_cui_in_expedientes(db, cui, anio_carga):
                raise ValueError(
                    f"DUP_CUI_EXPEDIENTE|Ya existe un expediente para el CUI {cui} en el año {anio_carga}."
                )

            payload_spiff = build_spiff_payload_from_staging_row(row=row)
            payload_spiff["usuario_id"] = usuario_id

            print(f"[SESAN] Enviando payload a BPM...")

            self._set_row_bpm_request(db, row_id, payload_spiff)

            bpm_eval = await self.bpm.evaluate_run_and_get_decision(payload_spiff)

            iid = bpm_eval.bpm_instance_id
            iid_str = str(iid) if iid and int(iid) > 0 else None

            print(f"[SESAN] BPM respondió -> instancia={iid_str} status={bpm_eval.status}")

            self._set_row_bpm_result(
                db,
                row_id,
                bpm_eval.status,
                bpm_eval.raw_create,
                iid_str,
            )

            if not bpm_eval.should_create_expediente:

                self._set_row_error(
                    db,
                    row_id,
                    "BPM_RECHAZADO",
                    "El motor BPM determinó que el expediente no debe crearse."
                )

                db.commit()

                print(f"[SESAN] ❌ BPM rechazó la creación del expediente para row {row_id}")

                return

            db.execute(
                text("""
                    UPDATE sesan_staging
                    SET estado = 'ESPERANDO_CALLBACK'
                    WHERE id = :id
                """),
                {"id": row_id},
            )

            db.commit()

            print(f"[SESAN] ✅ Row {row_id} enviado a BPM. Esperando callback.")

        except Exception as e:

            db.rollback()

            code = "PROCESS_ERROR"
            message = str(e)

            if "|" in message:
                code, message = message.split("|", 1)

            print(f"[SESAN] ❌ Error en row {row_id} -> {code}: {message}")

            self._set_row_error(
                db,
                row_id,
                code,
                message,
            )

            db.commit()

        finally:

            db.close()
            
    # ==========================================================
    # VALIDACIONES
    # ==========================================================
    def _is_dup_cui_in_year(self, db: Session, cui_nino: str, anio_carga: int, current_row_id: int):

        exists = db.execute(
            text("""
                SELECT 1
                FROM sesan_staging s
                JOIN sesan_batch b ON b.id = s.batch_id
                WHERE b.anio_carga = :anio
                AND s.estado = 'PROCESADO'
                AND s.cui_nino = :cui
                AND s.id <> :row_id
                LIMIT 1
            """),
            {"anio": anio_carga, "cui": cui_nino, "row_id": current_row_id},
        ).scalar()

        return bool(exists)

    def _is_dup_cui_in_expedientes(self, db: Session, cui_nino: str, anio_carga: int):

        exists = db.execute(
            text("""
                SELECT 1
                FROM info_general ig
                WHERE ig.cui_del_nino = :cui
                AND ig.anio = :anio
                LIMIT 1
            """),
            {"cui": cui_nino, "anio": str(anio_carga)},
        ).scalar()

        return bool(exists)

    # ==========================================================
    # HELPERS
    # ==========================================================

    def _set_row_error(self, db: Session, row_id: int, code: str, msg: str):

        db.execute(
            text("""
                UPDATE sesan_staging
                SET estado='ERROR',
                    error_code=:code,
                    error_mensaje=:msg,
                    updated_at=NOW()
                WHERE id=:id
            """),
            {"id": row_id, "code": code, "msg": msg},
        )

    def _set_row_bpm_request(self, db: Session, row_id: int, bpm_req: dict):

        db.execute(
            text("""
                UPDATE sesan_staging
                SET bpm_request_json=:req
                WHERE id=:id
            """),
            {"id": row_id, "req": json.dumps(bpm_req)},
        )

    def _set_row_bpm_result(self, db: Session, row_id: int, bpm_status: str, bpm_res: dict, bpm_instance_id: str | None):

        db.execute(
            text("""
                UPDATE sesan_staging
                SET bpm_status=:status,
                    bpm_instance_id=:iid,
                    bpm_response_json=:res
                WHERE id=:id
            """),
            {
                "id": row_id,
                "status": bpm_status,
                "iid": bpm_instance_id,
                "res": json.dumps(bpm_res),
            },
        )