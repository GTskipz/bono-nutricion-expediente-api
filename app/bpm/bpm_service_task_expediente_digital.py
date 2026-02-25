# app/services/bpm_service_task_expediente_digital.py

from __future__ import annotations

from typing import Dict, Any, Optional
import logging
import httpx
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.bpm.bpm_client import BpmClient

logger = logging.getLogger("mis.bpm.task.expediente_digital")


class BpmServiceTaskExpedienteDigital:
    """
    ✅ Solo BPM + construcción de links (relativos) a documentos, usando documentos_y_anexos.
    ✅ NO crea endpoints nuevos.
    ✅ NO usa URL absoluta (sin servidor); envía rutas relativas tipo: /expedientes/documento/{doc_id}
    ✅ NO actualiza BD (no commits/rollbacks aquí).
    """

    # Ajusta estos IDs según tu catálogo real.
    # (Ya vimos que DPI_TITULAR = 1 en tu ejemplo.)
    TIPO_DOC = {
        "DPI_TITULAR": 1,
        "DPI_NINO": 2,
        "RECIBO_LUZ": 3,
        "CARTA_ACEPTACION": 4,
    }

    ESTADO_VALIDO = "ADJUNTADO"

    def __init__(self, db: Session):
        self.db = db
        self.bpm = BpmClient()

    # -----------------------------
    # Helpers: links relativos
    # -----------------------------
    @staticmethod
    def _link_relativo_descarga(doc_id: int) -> str:
        return f"/expedientes/documento/{doc_id}"

    def _obtener_doc_ids_ultimos_por_tipo(
        self,
        *,
        expediente_id: int,
        tipo_doc_map: Optional[Dict[str, int]] = None,
        estado: Optional[str] = None,
    ) -> Dict[str, Optional[int]]:
        """
        Devuelve el último doc_id por cada tipo requerido (según created_at DESC).
        """
        tipos = (tipo_doc_map or self.TIPO_DOC).copy()
        estado_ok = estado or self.ESTADO_VALIDO

        rows = self.db.execute(
            text("""
                SELECT id, tipo_documento_id
                FROM documentos_y_anexos
                WHERE expediente_id = :expediente_id
                  AND tipo_documento_id = ANY(:tipos)
                  AND estado = :estado
                ORDER BY tipo_documento_id, created_at DESC
            """),
            {
                "expediente_id": expediente_id,
                "tipos": list(tipos.values()),
                "estado": estado_ok,
            },
        ).mappings().all()

        # Tomar el más reciente por tipo_documento_id
        last_by_tipo: Dict[int, int] = {}
        for r in rows:
            tid = int(r["tipo_documento_id"])
            if tid not in last_by_tipo:
                last_by_tipo[tid] = int(r["id"])

        # Mapear a llaves lógicas
        out: Dict[str, Optional[int]] = {}
        for key, tipo_id in tipos.items():
            out[key] = last_by_tipo.get(int(tipo_id))
        return out

    def _generar_links_para_spiff(
        self,
        *,
        expediente_id: int,
        tipo_doc_map: Optional[Dict[str, int]] = None,
        estado: Optional[str] = None,
        strict: bool = True,
    ) -> Dict[str, str]:
        """
        Genera los 4 links relativos que pide BPM.

        strict=True  -> si falta alguno, lanza ValueError
        strict=False -> si falta alguno, lo manda como "" (vacío)
        """
        doc_ids = self._obtener_doc_ids_ultimos_por_tipo(
            expediente_id=expediente_id,
            tipo_doc_map=tipo_doc_map,
            estado=estado,
        )

        # Convertir a links con nombres exactos que BPM espera
        links = {
            "link_DPI_NINO": self._link_relativo_descarga(doc_ids["DPI_NINO"]) if doc_ids.get("DPI_NINO") else "",
            "link_RECIBO_LUZ": self._link_relativo_descarga(doc_ids["RECIBO_LUZ"]) if doc_ids.get("RECIBO_LUZ") else "",
            "link_CARTA_ACEPTACION": self._link_relativo_descarga(doc_ids["CARTA_ACEPTACION"]) if doc_ids.get("CARTA_ACEPTACION") else "",
            "link_DPI_TITULAR": self._link_relativo_descarga(doc_ids["DPI_TITULAR"]) if doc_ids.get("DPI_TITULAR") else "",
        }

        if strict:
            faltantes = [k for k, v in links.items() if not v]
            if faltantes:
                raise ValueError(f"Faltan documentos requeridos para verificación: {', '.join(faltantes)}")

        return links

    # -----------------------------
    # BPM: enviar sección expediente_digital
    # -----------------------------
    async def enviar_expediente_digital(
        self,
        *,
        expediente_id: int,
        observaciones_exp: str,
        expediente_completo: bool = True,
        strict_links: bool = True,
        tipo_doc_map: Optional[Dict[str, int]] = None,
        estado_docs: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        1) Obtiene bpm_instance_id desde expediente_electronico
        2) GET instruction -> task_guid = instruction["task"]["id"]
        3) Genera links relativos desde documentos_y_anexos por expediente_id
        4) PUT /v1.0/tasks/{process_instance_id}/{task_guid}?with_form_data=true
        """
        try:
            # 1) bpm_instance_id
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

            process_instance_id = int(row["bpm_instance_id"])

            # 2) instruction + task_guid
            instruction = await self.bpm.get_task_instruction(process_instance_id)
            task = (instruction or {}).get("task") or {}
            task_guid = task.get("id")

            if not task_guid:
                logger.warning("TASK INSTRUCTION (RAW): %s", instruction)
                raise RuntimeError("No se encontró task activo en BPM")

            # 3) links (relativos)
            links = self._generar_links_para_spiff(
                expediente_id=expediente_id,
                tipo_doc_map=tipo_doc_map,
                estado=estado_docs,
                strict=strict_links,
            )

            payload = {
                "expediente_digital": {
                    "expediente_completo": bool(expediente_completo),
                    "observaciones_exp": observaciones_exp or "",
                    **links,
                }
            }

            # 4) PUT a Spiff
            url = (
                f"{self.bpm.base_url}"
                f"/v1.0/tasks/{process_instance_id}/{task_guid}"
                f"?with_form_data=true"
            )

            async with httpx.AsyncClient(
                verify=self.bpm.verify_ssl,
                timeout=self.bpm.timeout,
            ) as client:
                response = await client.put(
                    url,
                    json=payload,
                    headers=await self.bpm._headers(),
                )

            if response.status_code >= 400:
                raise RuntimeError(f"BPM error {response.status_code}: {response.text}")

            return response.json()

        except Exception as e:
            logger.error("Error enviando expediente_digital a BPM: %s", str(e))
            raise RuntimeError(f"No se pudo enviar expediente_digital a BPM. Detalle: {str(e)}")