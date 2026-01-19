# app/bpm/bpm_client.py
from __future__ import annotations
from typing import Dict, Any
import os


class BpmClient:
    """
    Cliente BPM.
    - Si BPM_ENABLED=false → STUB (no red)
    - Si BPM_ENABLED=true → aquí luego se implementa HTTP real
    """

    def __init__(self):
        self.enabled = os.getenv("BPM_ENABLED", "false").lower() == "true"

    def evaluate_expediente(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evalúa expediente en BPM.
        Por ahora: STUB controlado por env.
        """
        if not self.enabled:
            # ✅ STUB: comportamiento controlado
            return {
                "resultado_elegibilidad": "APROBADO",
                "monto_bono": 700,
                "observaciones": "STUB BPM (BPM_ENABLED=false)",
            }

        # 🔒 FUTURO: aquí va la llamada real a Spiff
        # (cuando te den la URL y el contrato)
        raise RuntimeError("BPM_ENABLED=true pero cliente real no implementado aún")
