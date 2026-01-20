from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any, Optional
import os
import httpx

from app.bpm.keycloak_token_cache import get_access_token_cached


@dataclass
class BpmEvaluationResult:
    bpm_instance_id: int
    raw_create: Dict[str, Any]
    raw_status: Dict[str, Any]

    status: str
    last_milestone_bpmn_name: str

    # Decisión normalizada (para SESAN)
    should_create_expediente: bool
    decision_reason: str  # EN_BPM | RECHAZADO | PENDIENTE
    is_rejected: bool
    requires_human_tasks: bool


class BpmClient:
    """
    Cliente BPM (SpiffWorkflow)

    Flujo oficial:
      1) POST /v1.0/messages/registrar_nutricion  (crea + inicia proceso)
      2) GET  /v1.0/process-instances/integracion:integracion/{id}
      3) El estado decide (sin asumir reglas nuevas)
    """

    MESSAGE_REGISTRAR_NUTRICION_PATH = "/v1.0/messages/registrar_nutricion"
    PROCESS_INSTANCE_STATUS_PATH = "/v1.0/process-instances/integracion:integracion"

    # Campos pesados que NO queremos persistir completos
    HEAVY_FIELDS = {
        "bpmn_xml_file_contents",
        "bpmn_xml_file_contents_retrieval_error",
    }

    # Si llega otro string gigante, lo recortamos para no sobrecargar DB/logs
    MAX_STRING_LEN = 5000

    def __init__(self):
        self.enabled = (os.getenv("BPM_ENABLED", "false") or "false").lower().strip() == "true"
        self.base_url = (os.getenv("SPIFF_BASE_URL", "") or "").rstrip("/")
        self.timeout = int(os.getenv("SPIFF_TIMEOUT_SECONDS", "30") or "30")

        verify_ssl = (os.getenv("SPIFF_VERIFY_SSL", "true") or "true").lower().strip()
        self.verify_ssl = verify_ssl in ("1", "true", "yes", "y")

        if self.enabled and not self.base_url:
            raise RuntimeError("Falta variable de entorno SPIFF_BASE_URL")

    # =====================================================
    # Limpieza de respuesta Spiff (quita XML gigante)
    # =====================================================
    @classmethod
    def _sanitize_spiff_json(cls, data: Any) -> Any:
        """
        - Remueve o marca como omitidos campos gigantes (XML BPMN).
        - Recorta strings enormes para evitar sobrecargar DB / logs.
        - Mantiene estructura y campos útiles (status, id, milestone, etc).
        """
        if isinstance(data, dict):
            cleaned: Dict[str, Any] = {}
            for k, v in data.items():
                if k in cls.HEAVY_FIELDS:
                    # Puedes cambiar a: continue  (si prefieres eliminarlo)
                    cleaned[k] = "[omitted]"
                    continue
                cleaned[k] = cls._sanitize_spiff_json(v)
            return cleaned

        if isinstance(data, list):
            return [cls._sanitize_spiff_json(x) for x in data]

        if isinstance(data, str):
            if len(data) > cls.MAX_STRING_LEN:
                return data[: cls.MAX_STRING_LEN] + "...[truncated]"
            return data

        return data

    # =====================================================
    # 1) Enviar message (crear + iniciar proceso)
    # =====================================================
    async def send_message_registrar_nutricion(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Envía el payload al message trigger que crea e inicia el proceso BPM.
        """
        if not self.enabled:
            return {
                "process_instance_id": 1,
                "status": "user_input_required",
                "stub": True
            }

        access_token = await get_access_token_cached()
        url = f"{self.base_url}{self.MESSAGE_REGISTRAR_NUTRICION_PATH}"

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(
            verify=self.verify_ssl,
            timeout=self.timeout
        ) as client:
            response = await client.post(url, json=payload, headers=headers)

        if response.status_code >= 400:
            detail = self._safe_response_detail(response)
            raise RuntimeError(f"Error BPM Spiff {response.status_code}: {detail}")

        # ✅ Sanitizar para evitar guardar XML gigante
        return self._sanitize_spiff_json(response.json())

    # =====================================================
    # 2) Consultar estado de instancia
    # =====================================================
    async def get_process_instance(self, bpm_instance_id: str | int) -> Dict[str, Any]:
        if not self.enabled:
            return {
                "id": int(bpm_instance_id),
                "status": "user_input_required",
                "last_milestone_bpmn_name": "Stub - Inicio",
                "stub": True,
            }

        access_token = await get_access_token_cached()
        url = f"{self.base_url}{self.PROCESS_INSTANCE_STATUS_PATH}/{bpm_instance_id}"

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(
            verify=self.verify_ssl,
            timeout=self.timeout
        ) as client:
            response = await client.get(url, headers=headers)

        if response.status_code >= 400:
            detail = self._safe_response_detail(response)
            raise RuntimeError(f"Error BPM Spiff {response.status_code}: {detail}")

        # ✅ Sanitizar para evitar guardar XML gigante
        return self._sanitize_spiff_json(response.json())

    # =====================================================
    # 3) Orquestador oficial
    # =====================================================
    async def evaluate_run_and_get_decision(self, payload: Dict[str, Any]) -> BpmEvaluationResult:
        """
        Flujo oficial MIS/SESAN:
          - enviar message
          - consultar estado
          - devolver decisión SIN asumir reglas nuevas
        """
        create_json = await self.send_message_registrar_nutricion(payload)

        bpm_instance_id = self._extract_process_instance_id(create_json)
        if bpm_instance_id is None:
            raise RuntimeError(
                f"Spiff no devolvió process_instance_id/id en message: {create_json}"
            )

        status_json = await self.get_process_instance(bpm_instance_id)
        normalized = self._normalize_decision_from_status(status_json)

        return BpmEvaluationResult(
            bpm_instance_id=int(bpm_instance_id),
            raw_create=create_json,
            raw_status=status_json,
            status=normalized["status"],
            last_milestone_bpmn_name=normalized["last_milestone_bpmn_name"],
            should_create_expediente=normalized["should_create_expediente"],
            decision_reason=normalized["decision_reason"],
            is_rejected=normalized["is_rejected"],
            requires_human_tasks=normalized["requires_human_tasks"],
        )

    # =====================================================
    # Helpers
    # =====================================================
    @staticmethod
    def _extract_process_instance_id(create_json: Dict[str, Any]) -> Optional[int]:
        candidates = [
            "process_instance_id",
            "processInstanceId",
            "process_instance",
            "processInstance",
            "id",
        ]

        for key in candidates:
            val = create_json.get(key)
            if val is None:
                continue

            if isinstance(val, dict) and "id" in val:
                try:
                    return int(val["id"])
                except Exception:
                    continue

            try:
                return int(val)
            except Exception:
                continue

        return None

    # =====================================================
    # Normalizador (NO se cambia lógica)
    # =====================================================
    @staticmethod
    def _normalize_decision_from_status(status_json: Dict[str, Any]) -> Dict[str, Any]:
        status = (status_json.get("status") or "").strip()
        status_l = status.lower()

        milestone = (status_json.get("last_milestone_bpmn_name") or "").strip()
        milestone_l = milestone.lower()

        if status_l == "user_input_required":
            return {
                "status": status,
                "last_milestone_bpmn_name": milestone,
                "should_create_expediente": True,
                "decision_reason": "EN_BPM",
                "is_rejected": False,
                "requires_human_tasks": True,
            }

        if status_l == "complete" and "rechaz" in milestone_l:
            return {
                "status": status,
                "last_milestone_bpmn_name": milestone,
                "should_create_expediente": False,
                "decision_reason": "RECHAZADO",
                "is_rejected": True,
                "requires_human_tasks": False,
            }

        return {
            "status": status,
            "last_milestone_bpmn_name": milestone,
            "should_create_expediente": False,
            "decision_reason": "PENDIENTE",
            "is_rejected": False,
            "requires_human_tasks": False,
        }

    @staticmethod
    def _safe_response_detail(response: httpx.Response) -> Any:
        try:
            return response.json()
        except Exception:
            return response.text
