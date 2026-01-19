# app/bpm/bpm_types.py
from __future__ import annotations
from typing import Any, Dict, Optional
from pydantic import BaseModel


class BpmEvaluateResponse(BaseModel):
    status: str = "ok"
    resultado_elegibilidad: str = "APROBADO"  # APROBADO | RECHAZADO | etc
    monto_bono: Optional[int] = None
    observaciones: Optional[str] = None
    data: Dict[str, Any] = {}
