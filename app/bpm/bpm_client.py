from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any, Optional
import os
import httpx
import logging
import json
import re

# ✅ Token de servicio (cacheado)
from app.bpm.keycloak_token_cache import get_access_token

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("mis.bpm")


@dataclass
class BpmEvaluationResult:
    # ✅ puede ser None si Spiff devolvió error top-level y no incluye process_instance.id
    bpm_instance_id: Optional[int]
    raw_create: Dict[str, Any]
    raw_status: Dict[str, Any]

    status: str
    last_milestone_bpmn_name: str

    should_create_expediente: bool
    decision_reason: str
    is_rejected: bool
    requires_human_tasks: bool

    # ✅ indicador informativo
    procesamiento_exitoso: bool

    # ✅ errores detectados (resumen)
    errors: Dict[str, Any]


class BpmClient:
    MESSAGE_REGISTRAR_NUTRICION_PATH = "/v1.0/messages/registrar_nutricion"
    PROCESS_INSTANCE_STATUS_PATH = "/v1.0/process-instances/integracion:integracion"

    # Campos pesados o sensibles (pueden traer tokens / JSON enorme)
    HEAVY_FIELDS = {
        "bpmn_xml_file_contents",
        "bpmn_xml_file_contents_retrieval_error",
        "task_data",
        "payload",  # 👈 importante: a veces trae token o credenciales
    }

    MAX_STRING_LEN = 3000

    def __init__(self):
        self.enabled = (os.getenv("BPM_ENABLED", "false") or "false").lower().strip() == "true"
        self.base_url = (os.getenv("SPIFF_BASE_URL", "") or "").rstrip("/")
        self.timeout = int(os.getenv("SPIFF_TIMEOUT_SECONDS", "30") or "30")

        verify_ssl = (os.getenv("SPIFF_VERIFY_SSL", "true") or "true").lower().strip()
        self.verify_ssl = verify_ssl in ("1", "true", "yes", "y")

        logger.warning("========== BPM INIT ==========")
        logger.warning("Enabled: %s", self.enabled)
        logger.warning("Base URL: %s", self.base_url)
        logger.warning("Timeout: %s", self.timeout)
        logger.warning("Verify SSL: %s", self.verify_ssl)
        logger.warning("================================")

        if self.enabled and not self.base_url:
            raise RuntimeError("Falta variable de entorno SPIFF_BASE_URL")

    # =====================================================
    # HEADERS (TOKEN DE SERVICIO CACHEADO)
    # =====================================================
    async def _headers(self) -> Dict[str, str]:
        token = await get_access_token()

        if not token:
            logger.error("❌ No se pudo obtener token de servicio (Keycloak)")
            raise RuntimeError("No se pudo obtener token de servicio (Keycloak).")

        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    # =====================================================
    # LOG SAFE HELPERS
    # =====================================================
    def _truncate(self, s: str) -> str:
        if s is None:
            return s
        if len(s) <= self.MAX_STRING_LEN:
            return s
        return s[: self.MAX_STRING_LEN - 20] + f"...(truncated,len={len(s)})"

    def _prune_for_log(self, obj: Any) -> Any:
        if obj is None:
            return None
        if isinstance(obj, str):
            return self._truncate(obj)
        if isinstance(obj, (int, float, bool)):
            return obj
        if isinstance(obj, list):
            return [self._prune_for_log(x) for x in obj]
        if isinstance(obj, dict):
            out: Dict[str, Any] = {}
            for k, v in obj.items():
                if k in self.HEAVY_FIELDS:
                    out[k] = "[omitted]"
                else:
                    out[k] = self._prune_for_log(v)
            return out
        return self._truncate(str(obj))

    def _payload_summary(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # Idea: NUNCA loguear SESAN completo
        return {
            "cui_nino": payload.get("CUI DEL NIÑO") or payload.get("cui_nino") or payload.get("cui"),
            "nombre_nino": payload.get("NOMBRE DEL NIÑO") or payload.get("nombre_nino") or payload.get("nombre"),
            "anio": payload.get("ANO") or payload.get("anio"),
            "mes": payload.get("MES") or payload.get("mes"),
            "depto": payload.get("DEPARTAMENTO DE RESIDENCIA") or payload.get("departamento"),
            "mun": payload.get("MUNICIPIO DE RESIDENCIA") or payload.get("municipio"),
        }

    # =====================================================
    # ERROR EXTRACT (REAL)
    # =====================================================
    @staticmethod
    def _has_top_level_error(create_json: Dict[str, Any]) -> bool:
        """
        Detecta el caso tipo:
          {
            "status": 400,
            "error_code": "...",
            "error_type": "...",
            "detail": "...",
            ...
          }
        """
        st = create_json.get("status")
        if isinstance(st, int) and st >= 400:
            return True

        # a veces status viene string
        try:
            if isinstance(st, str) and st.strip().isdigit() and int(st.strip()) >= 400:
                return True
        except Exception:
            pass

        # flags adicionales
        if create_json.get("error_code") or create_json.get("error_type") or create_json.get("title") == "unexpected_workflow_exception":
            return True

        return False

    @staticmethod
    def _try_parse_raw_http_response(text: str) -> Optional[Dict[str, Any]]:
        """
        Busca: Raw http_response was: { ... }
        y parsea ese JSON.
        """
        if not text or not isinstance(text, str):
            return None
        m = re.search(r"Raw http_response was:\s*(\{.*\})", text)
        if not m:
            return None
        raw = m.group(1)
        try:
            return json.loads(raw)
        except Exception:
            return None

    @staticmethod
    def _extract_errors_from_create(create_json: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prioriza errores top-level (detail/message + raw http_response embebido).
        Luego fallback a task_data.
        """
        items = []

        # top-level basics
        top_status = create_json.get("status")
        error_code = create_json.get("error_code") or create_json.get("errorCode")
        title = create_json.get("title")
        error_type = create_json.get("error_type") or create_json.get("errorType")
        file_name = create_json.get("file_name")

        detail = create_json.get("detail") or ""
        message = create_json.get("message") or ""

        if BpmClient._has_top_level_error(create_json):
            items.append({
                "source": "spiff",
                "status": top_status,
                "error_code": error_code,
                "title": title,
                "error_type": error_type,
                "file_name": file_name,
            })

        # parse embedded raw http_response (RENAP/SNIS/etc)
        parsed = None
        if isinstance(detail, str):
            parsed = BpmClient._try_parse_raw_http_response(detail)
        if not parsed and isinstance(message, str):
            parsed = BpmClient._try_parse_raw_http_response(message)

        if parsed:
            msgs = parsed.get("message")
            if isinstance(msgs, list):
                for x in msgs:
                    if x:
                        items.append({"source": "service", "message": str(x)})
            elif isinstance(msgs, str) and msgs.strip():
                items.append({"source": "service", "message": msgs.strip()})

            if parsed.get("error") or parsed.get("statusCode"):
                items.append({
                    "source": "service",
                    "error": parsed.get("error"),
                    "statusCode": parsed.get("statusCode"),
                })

        # include truncated detail/message as last resort
        if isinstance(detail, str) and detail.strip():
            items.append({"source": "spiff", "detail": detail[:500]})
        if isinstance(message, str) and message.strip():
            items.append({"source": "spiff", "message": message[:500]})

        # fallback heurístico dentro de task_data
        task_data = create_json.get("task_data") or {}
        candidates = [
            "errors", "errores",
            "validations", "validaciones",
            "messages", "mensajes",
            "warnings", "advertencias",
            "detail", "details",
            "error_detalle", "error_snis"
        ]
        for k in candidates:
            v = task_data.get(k)
            if isinstance(v, list) and v:
                for it in v[:50]:
                    items.append({"source": "task_data", "field": k, "message": str(it)[:500]})
            elif isinstance(v, dict) and v:
                items.append({"source": "task_data", "field": k, "value": v})
            elif isinstance(v, str) and v.strip():
                items.append({"source": "task_data", "field": k, "message": v.strip()[:500]})

        # de-dup simple
        unique = []
        seen = set()
        for it in items:
            s = json.dumps(it, sort_keys=True, ensure_ascii=False, default=str)
            if s in seen:
                continue
            seen.add(s)
            unique.append(it)

        return {"has_errors": len(unique) > 0, "items": unique[:50]}

    # =====================================================
    # POST MESSAGE
    # =====================================================
    async def send_message_registrar_nutricion(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.enabled:
            return {
                "task_data": {"procesamiento_exitoso": True},
                "process_instance": {
                    "id": 1,
                    "status": "user_input_required",
                    "last_milestone_bpmn_name": "Stub - Inicio",
                },
                "stub": True,
            }

        url = f"{self.base_url}{self.MESSAGE_REGISTRAR_NUTRICION_PATH}"

        logger.warning("========== BPM POST ==========")
        logger.warning("URL: %s", url)
        logger.warning("PAYLOAD SUMMARY: %s", self._payload_summary(payload))
        logger.warning("================================")

        async with httpx.AsyncClient(verify=self.verify_ssl, timeout=self.timeout) as client:
            response = await client.post(url, json=payload, headers=await self._headers())

        logger.warning("========== BPM RESPONSE ==========")
        logger.warning("STATUS CODE: %s", response.status_code)
        try:
            body = response.json()
            logger.warning("BODY JSON (PRUNED): %s", self._prune_for_log(body))
        except Exception:
            logger.warning("BODY TEXT: %s", self._truncate(response.text or ""))
        logger.warning("====================================")

        # Si HTTP es 4xx/5xx -> error directo
        if response.status_code >= 400:
            detail = self._safe_response_detail(response)
            raise RuntimeError(f"Error BPM Spiff {response.status_code}: {detail}")

        # Nota: a veces Spiff responde 200 pero con error top-level dentro del JSON (status:400)
        return response.json()

    # =====================================================
    # GET STATUS (se mantiene para otros consumos)
    # =====================================================
    async def get_process_instance(self, bpm_instance_id: str | int) -> Dict[str, Any]:
        if not self.enabled:
            return {
                "id": int(bpm_instance_id),
                "status": "user_input_required",
                "last_milestone_bpmn_name": "Stub - Inicio",
                "stub": True,
            }

        url = f"{self.base_url}{self.PROCESS_INSTANCE_STATUS_PATH}/{bpm_instance_id}"

        logger.warning("========== BPM GET ==========")
        logger.warning("URL: %s", url)
        logger.warning("================================")

        async with httpx.AsyncClient(verify=self.verify_ssl, timeout=self.timeout) as client:
            response = await client.get(url, headers=await self._headers())

        logger.warning("========== BPM GET RESPONSE ==========")
        logger.warning("STATUS CODE: %s", response.status_code)
        try:
            body = response.json()
            logger.warning("BODY JSON (PRUNED): %s", self._prune_for_log(body))
        except Exception:
            logger.warning("BODY TEXT: %s", self._truncate(response.text or ""))
        logger.warning("=======================================")

        if response.status_code >= 400:
            detail = self._safe_response_detail(response)
            raise RuntimeError(f"Error BPM Spiff {response.status_code}: {detail}")

        return response.json()

    # =====================================================
    # ORQUESTADOR
    # =====================================================
    async def evaluate_run_and_get_decision(
        self,
        payload: Dict[str, Any],
        *,
        force_refresh_status: bool = False,
    ) -> BpmEvaluationResult:
        create_json = await self.send_message_registrar_nutricion(payload)

        # ✅ IMPORTANTE: NO inventar ids (NO usar "or 0")
        bpm_instance_id = self._extract_process_instance_id(create_json)  # Optional[int]

        normalized = self._normalize_decision_from_create(create_json)

        status_json: Dict[str, Any] = {}
        if force_refresh_status and bpm_instance_id is not None:
            status_json = await self.get_process_instance(bpm_instance_id)

        return BpmEvaluationResult(
            bpm_instance_id=bpm_instance_id,
            raw_create=create_json,
            raw_status=status_json,
            status=normalized["status"],
            last_milestone_bpmn_name=normalized["last_milestone_bpmn_name"],
            should_create_expediente=normalized["should_create_expediente"],
            decision_reason=normalized["decision_reason"],
            is_rejected=normalized["is_rejected"],
            requires_human_tasks=normalized["requires_human_tasks"],
            procesamiento_exitoso=normalized["procesamiento_exitoso"],
            errors=normalized["errors"],
        )

    # =====================================================
    # HELPERS
    # =====================================================
    @staticmethod
    def _extract_process_instance_id(create_json: Dict[str, Any]) -> Optional[int]:
        """
        Nuevo contrato: create_json.process_instance.id
        Mantiene compatibilidad con respuestas antiguas.
        """
        pi = create_json.get("process_instance")
        if isinstance(pi, dict):
            iid = pi.get("id")
            if iid is not None:
                try:
                    return int(iid)
                except Exception:
                    return None

        for key in ("process_instance_id", "processInstanceId", "id"):
            val = create_json.get(key)
            if val is None:
                continue
            try:
                return int(val)
            except Exception:
                continue

        return None

    @staticmethod
    def _normalize_decision_from_create(create_json: Dict[str, Any]) -> Dict[str, Any]:
        """
        Lógica final:
        1) Si create_json trae error top-level => ERROR_EN_BPM (NO crear)
        2) Si no hay error top-level:
            - usar task_data.procesamiento_exitoso + process_instance.status/milestone
        """
        errors = BpmClient._extract_errors_from_create(create_json)

        # 1) Error top-level manda
        if BpmClient._has_top_level_error(create_json):
            st = create_json.get("status")
            st_norm = str(st) if st is not None else "error"

            return {
                "procesamiento_exitoso": False,
                "errors": errors,
                "status": st_norm,
                "last_milestone_bpmn_name": "",
                "should_create_expediente": False,
                "decision_reason": "ERROR_EN_BPM",
                "is_rejected": False,
                "requires_human_tasks": False,
            }

        # 2) Caso normal (sin error top-level)
        task_data = create_json.get("task_data") or {}
        process_instance = create_json.get("process_instance") or {}

        procesamiento_exitoso = bool(task_data.get("procesamiento_exitoso", False))

        status = (process_instance.get("status") or "").strip()
        status_l = status.lower()

        milestone = (process_instance.get("last_milestone_bpmn_name") or "").strip()
        milestone_l = milestone.lower()

        if procesamiento_exitoso:
            if status_l == "user_input_required":
                return {
                    "procesamiento_exitoso": True,
                    "errors": errors,
                    "status": status or "user_input_required",
                    "last_milestone_bpmn_name": milestone,
                    "should_create_expediente": True,
                    "decision_reason": "PROCESADO_OK_EN_BPM",
                    "is_rejected": False,
                    "requires_human_tasks": True,
                }

            if status_l == "complete" and "rechaz" not in milestone_l:
                return {
                    "procesamiento_exitoso": True,
                    "errors": errors,
                    "status": status,
                    "last_milestone_bpmn_name": milestone,
                    "should_create_expediente": True,
                    "decision_reason": "PROCESADO_OK_COMPLETO",
                    "is_rejected": False,
                    "requires_human_tasks": False,
                }

            return {
                "procesamiento_exitoso": True,
                "errors": errors,
                "status": status or "unknown",
                "last_milestone_bpmn_name": milestone,
                "should_create_expediente": True,
                "decision_reason": "PROCESADO_OK",
                "is_rejected": False,
                "requires_human_tasks": status_l == "user_input_required",
            }

        # No exitoso (sin error top-level)
        if "rechaz" in milestone_l:
            return {
                "procesamiento_exitoso": False,
                "errors": errors,
                "status": status or "unknown",
                "last_milestone_bpmn_name": milestone,
                "should_create_expediente": False,
                "decision_reason": "RECHAZADO_EN_BPM",
                "is_rejected": True,
                "requires_human_tasks": False,
            }

        return {
            "procesamiento_exitoso": False,
            "errors": errors,
            "status": status or "unknown",
            "last_milestone_bpmn_name": milestone,
            "should_create_expediente": False,
            "decision_reason": "PENDIENTE_O_ERROR",
            "is_rejected": False,
            "requires_human_tasks": False,
        }

    @staticmethod
    def _safe_response_detail(response: httpx.Response) -> Any:
        try:
            return response.json()
        except Exception:
            return response.text
        

    # =====================================================
    # ✅ GET TASK INSTRUCTION (según tu endpoint)
    # =====================================================
    async def get_task_instruction(self, task_id: int) -> Dict[str, Any]:
        if not self.enabled:
            return {
                "task_id": int(task_id),
                "instruction": {"stub": True},
                "stub": True,
            }

        url = f"{self.base_url}/v1.0/tasks/{task_id}/instruction"

        logger.warning("========== BPM TASK INSTRUCTION ==========")
        logger.warning("URL: %s", url)
        logger.warning("==========================================")

        async with httpx.AsyncClient(
            verify=self.verify_ssl,
            timeout=self.timeout
        ) as client:
            response = await client.get(url, headers=await self._headers())

        if response.status_code >= 400:
            detail = self._safe_response_detail(response)
            raise RuntimeError(f"Error BPM Spiff {response.status_code}: {detail}")

        # (opcional) log pruned si quieres
        try:
            body = response.json()
            logger.warning("TASK INSTRUCTION (PRUNED): %s", self._prune_for_log(body))
        except Exception:
            pass

        return response.json()
    
    # =====================================================
    # ✅ GET COMPLETED TASKS (Spiff)
    # =====================================================
    async def get_tasks_completed(
        self,
        process_instance_id: int,
        page: int = 1,
        per_page: int = 20,
    ) -> Dict[str, Any]:
        if not self.enabled:
            return {
                "process_instance_id": int(process_instance_id),
                "page": int(page),
                "per_page": int(per_page),
                "data": [],
                "stub": True,
            }

        url = (
            f"{self.base_url}/v1.0/tasks/completed/{int(process_instance_id)}"
            f"?page={int(page)}&per_page={int(per_page)}"
        )

        logger.warning("========== BPM TASKS COMPLETED ==========")
        logger.warning("URL: %s", url)
        logger.warning("=========================================")

        async with httpx.AsyncClient(
            verify=self.verify_ssl,
            timeout=self.timeout
        ) as client:
            response = await client.get(url, headers=await self._headers())

        if response.status_code >= 400:
            detail = self._safe_response_detail(response)
            raise RuntimeError(f"Error BPM Spiff {response.status_code}: {detail}")

        # (opcional) log pruned
        try:
            body = response.json()
            logger.warning("TASKS COMPLETED (PRUNED): %s", self._prune_for_log(body))
        except Exception:
            pass

        return response.json()