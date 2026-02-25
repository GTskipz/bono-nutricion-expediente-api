# app/services/bpm_service_task_data.py

from __future__ import annotations

from typing import Dict, Any, Optional
import logging
import httpx
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.bpm.bpm_client import BpmClient

logger = logging.getLogger("mis.bpm.task.data")


class BpmServiceTaskData:
    """
    ✅ Servicio SOLO de consulta BPM (no toca BD salvo lecturas).
    - Método A: recibe expediente_id y resuelve bpm_instance_id + task_guid
    - Método B: recibe bpm_instance_id y resuelve task_guid
    """

    def __init__(self, db: Session):
        self.db = db
        self.bpm = BpmClient()

    # -----------------------------------------------------
    # Internos
    # -----------------------------------------------------
    def _obtener_bpm_instance_id_por_expediente(self, expediente_id: int) -> int:
        row = self.db.execute(
            text("""
                SELECT bpm_instance_id
                FROM expediente_electronico
                WHERE id = :id
            """),
            {"id": expediente_id},
        ).mappings().first()

        if not row or not row.get("bpm_instance_id"):
            raise ValueError("Expediente no tiene bpm_instance_id")

        return int(row["bpm_instance_id"])

    async def _obtener_task_guid_activo(self, bpm_instance_id: int) -> str:
        instruction = await self.bpm.get_task_instruction(int(bpm_instance_id))
        task = (instruction or {}).get("task") or {}
        task_guid = task.get("id")
        if not task_guid:
            raise RuntimeError("No se encontró task activa en BPM para la instancia indicada")
        return str(task_guid)

    async def _get_task_data(
        self,
        *,
        bpm_instance_id: int,
        task_guid: str,
        process_model_identifier: str,
        with_form_data: bool,
    ) -> Dict[str, Any]:
        if not self.bpm.enabled:
            return {
                "bpm_instance_id": int(bpm_instance_id),
                "task_guid": task_guid,
                "process_model_identifier": process_model_identifier,
                "with_form_data": bool(with_form_data),
                "data": {"stub": True},
                "stub": True,
            }

        url = (
            f"{self.bpm.base_url}/v1.0/task-data/"
            f"{process_model_identifier}/"
            f"{int(bpm_instance_id)}/"
            f"{task_guid}"
            f"?with_form_data={'True' if with_form_data else 'False'}"
        )

        logger.warning("========== BPM TASK DATA ==========")
        logger.warning("URL: %s", url)
        logger.warning("===================================")

        async with httpx.AsyncClient(
            verify=self.bpm.verify_ssl,
            timeout=self.bpm.timeout
        ) as client:
            response = await client.get(url, headers=await self.bpm._headers())

        if response.status_code >= 400:
            detail = self.bpm._safe_response_detail(response)
            raise RuntimeError(f"Error BPM Spiff {response.status_code}: {detail}")

        try:
            body = response.json()
            logger.warning("TASK DATA (PRUNED): %s", self.bpm._prune_for_log(body))
        except Exception:
            pass

        return response.json()

    # -----------------------------------------------------
    # Público (2 métodos reutilizables)
    # -----------------------------------------------------
    async def obtener_task_data_por_bpm_instance_id(
        self,
        *,
        bpm_instance_id: int,
        process_model_identifier: str = "integracion:integracion",
        with_form_data: bool = True,
    ) -> Dict[str, Any]:
        """
        Recibe bpm_instance_id, resuelve task_guid activo y devuelve task-data.
        """
        task_guid = await self._obtener_task_guid_activo(int(bpm_instance_id))
        data = await self._get_task_data(
            bpm_instance_id=int(bpm_instance_id),
            task_guid=task_guid,
            process_model_identifier=process_model_identifier,
            with_form_data=with_form_data,
        )
        return {
            "bpm_instance_id": int(bpm_instance_id),
            "task_guid": task_guid,
            "data": data,
        }

    async def obtener_task_data_por_expediente_id(
        self,
        *,
        expediente_id: int,
        process_model_identifier: str = "integracion:integracion",
        with_form_data: bool = True,
    ) -> Dict[str, Any]:
        """
        Recibe expediente_id, resuelve bpm_instance_id + task_guid activo y devuelve task-data.
        """
        bpm_instance_id = self._obtener_bpm_instance_id_por_expediente(int(expediente_id))
        task_guid = await self._obtener_task_guid_activo(int(bpm_instance_id))
        data = await self._get_task_data(
            bpm_instance_id=int(bpm_instance_id),
            task_guid=task_guid,
            process_model_identifier=process_model_identifier,
            with_form_data=with_form_data,
        )
        return {
            "expediente_id": int(expediente_id),
            "bpm_instance_id": int(bpm_instance_id),
            "task_guid": task_guid,
            "data": data,
        }