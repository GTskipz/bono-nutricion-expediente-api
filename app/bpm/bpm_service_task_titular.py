from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Dict, Any
import httpx
import logging

from app.bpm.bpm_client import BpmClient
from app.services.tracking_evento_service import TrackingEventoService
from app.services.expedientes_service import actualizar_titular_y_estado_flujo

logger = logging.getLogger("mis.bpm.task.titular")


class BpmServiceTaskTitular:

    def __init__(self, db: Session):
        self.db = db
        self.bpm = BpmClient()

    # =====================================================
    # MÉTODO PRINCIPAL TRANSACCIONAL
    # =====================================================
    async def procesar_titular(
        self,
        *,
        expediente_id: int,
        nombre_titular: str,
        dpi_titular: str,
        tiene_copia_recibo: bool,
        tiene_copia_dpi: bool,
        usuario_nombre: str | None = None,  # CAMBIO
    ) -> Dict[str, Any]:

        try:
            # ============================================
            # 1️⃣ Validar expediente y obtener bpm_instance_id
            # ============================================
            row = self.db.execute(
                text("""
                    SELECT id, bpm_instance_id
                    FROM expediente_electronico
                    WHERE id = :id
                """),
                {"id": expediente_id},
            ).mappings().first()

            if not row:
                raise ValueError("Expediente no encontrado")

            if not row.get("bpm_instance_id"):
                raise ValueError("Expediente no tiene bpm_instance_id")

            process_instance_id = int(row["bpm_instance_id"])

            # ============================================
            # 2️⃣ Obtener task activo
            # ============================================
            instruction = await self.bpm.get_task_instruction(process_instance_id)

            task = (instruction or {}).get("task") or {}
            task_guid = task.get("id")

            if not task_guid:
                raise RuntimeError("No se encontró task activo en BPM")

            # ============================================
            # 3️⃣ Enviar titular a BPM
            # ============================================
            payload = {
                "seccion_titular": {
                    "nombre_titular": nombre_titular,
                    "dpi_titular": dpi_titular,
                    "tiene_copia_recibo": bool(tiene_copia_recibo),
                    "tiene_copia_dpi": bool(tiene_copia_dpi),
                }
            }

            url = (
                f"{self.bpm.base_url}"
                f"/v1.0/tasks/{process_instance_id}/{task_guid}"
                f"?with_form_data=true"
            )

            async with httpx.AsyncClient(
                verify=self.bpm.verify_ssl,
                timeout=self.bpm.timeout
            ) as client:
                response = await client.put(
                    url,
                    json=payload,
                    headers=await self.bpm._headers(),
                )

            if response.status_code >= 400:
                raise RuntimeError(
                    f"BPM error {response.status_code}: {response.text}"
                )

            bpm_response = response.json()

            # ============================================
            # 4️⃣ Solo si BPM salió bien, actualizar BD
            # ============================================
            expediente = actualizar_titular_y_estado_flujo(
                db=self.db,
                expediente_id=expediente_id,
                titular_nombre=nombre_titular,
                titular_dpi=dpi_titular,
                personalizado=False,
                usuario_nombre=usuario_nombre,  # CAMBIO
            )

            if not expediente:
                raise ValueError("Expediente no encontrado al actualizar titular")

            # ============================================
            # 5️⃣ Commit final
            # ============================================
            self.db.commit()

            return {
                "ok": True,
                "expediente": expediente,
                "bpm": bpm_response,
            }

        except Exception as e:
            try:
                self.db.rollback()
            except Exception:
                pass

            logger.error("Error procesando titular BPM: %s", str(e))

            raise RuntimeError(
                f"No se pudo completar la operación. No se actualizó el expediente. Detalle: {str(e)}"
            )