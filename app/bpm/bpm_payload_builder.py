from __future__ import annotations

from typing import Any, Dict, Optional
from datetime import date, datetime
import json


# =====================================================
# Helpers básicos
# =====================================================
def _iso(v: Any) -> Optional[str]:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    return str(v)


def _safe_str(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def _to_int(v: Any) -> Optional[int]:
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    try:
        return int(float(s))
    except Exception:
        return None


def _to_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    try:
        return float(s)
    except Exception:
        return None


def _raw_data_to_dict(raw_data: Any) -> Dict[str, Any]:
    """
    raw_data puede venir como:
    - dict
    - str JSON
    - None
    """
    if raw_data is None:
        return {}

    if isinstance(raw_data, dict):
        return raw_data

    if isinstance(raw_data, str):
        s = raw_data.strip()
        if not s:
            return {}
        try:
            return json.loads(s)
        except Exception:
            return {}

    return {}


# =====================================================
# ✅ Payload para MESSAGE registrar_nutricion (Spiff)
# =====================================================
def build_spiff_payload_from_staging_row(*, row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Construye el body EXACTO que espera:
    POST /v1.0/messages/registrar_nutricion
    """

    raw = _raw_data_to_dict(row.get("raw_data"))

    def pick(*keys: str) -> Any:
        for k in keys:
            if k in raw and raw.get(k) not in (None, ""):
                return raw.get(k)
        return None

    # Periodo
    anio = _to_int(row.get("anio")) or _to_int(pick("ANO", "AÑO")) or _to_int(row.get("anio_carga"))
    mes = _to_int(row.get("mes")) or _to_int(pick("MES")) or _to_int(row.get("mes_carga"))

    # Salud
    area_salud = _safe_str(row.get("area_salud")) or _safe_str(pick("AREA DE SALUD", "ÁREA DE SALUD"))
    distrito_salud = _safe_str(row.get("distrito_salud")) or _safe_str(pick("DISTRITO DE SALUD"))
    servicio_salud = _safe_str(row.get("servicio_salud")) or _safe_str(pick("SERVICIO DE SALUD"))

    # Ubicación
    dep_res = _safe_str(row.get("departamento_residencia")) or _safe_str(
        pick("DEPARTAMENTO DE RESIDENCIA", "DEPARTAMENTO")
    )
    muni_res = _safe_str(row.get("municipio_residencia")) or _safe_str(
        pick("MUNICIPIO DE RESIDENCIA", "MUNICIPIO")
    )
    comu_res = _safe_str(row.get("comunidad_residencia")) or _safe_str(
        pick("COMUNIDAD RESIDENCIA", "COMUNIDAD")
    )
    dir_res = _safe_str(row.get("direccion_residencia")) or _safe_str(
        pick("DIRECCIÓN RESIDENCIA", "DIRECCION RESIDENCIA")
    )

    # Niño
    cui_nino = _to_float(row.get("cui_nino")) or _to_float(pick("CUI DEL NIÑO", "CUI DEL NINO"))
    sexo = _safe_str(row.get("sexo")) or _safe_str(pick("SEXO"))
    edad_anios = _to_int(row.get("edad_en_anios")) or _to_int(
        pick("EDAD EN AÑOS", "EDAD EN ANOS", "EDAD")
    )
    nombre_nino = _safe_str(row.get("nombre_nino")) or _safe_str(
        pick("NOMBRE DEL NIÑO", "NOMBRE DEL NINO")
    )

    # Fechas
    fecha_nac = _iso(row.get("fecha_nacimiento")) or _iso(pick("FECHA NACIMIENTO"))
    fecha_contacto = _iso(row.get("fecha_primer_contacto")) or _iso(
        pick("FECHA DEL PRIMER CONTACTO")
    )
    fecha_registro = _iso(row.get("fecha_registro")) or _iso(pick("FECHA DE REGISTRO"))

    # Diagnóstico
    cie10 = _safe_str(row.get("cie_10")) or _safe_str(pick("CIE-10", "CIE 10"))
    diagnostico = _safe_str(row.get("diagnostico")) or _safe_str(
        pick("DIAGNÓSTICO", "DIAGNOSTICO")
    )

    # Padres
    nombre_madre = _safe_str(row.get("nombre_madre")) or _safe_str(pick("NOMBRE DE LA MADRE"))
    cui_madre = _to_float(row.get("cui_madre")) or _to_float(pick("CUI DE LA MADRE"))
    nombre_padre = _safe_str(row.get("nombre_padre")) or _safe_str(pick("NOMBRE DEL PADRE"))
    cui_padre = _to_float(row.get("cui_padre")) or _to_float(pick("CUI DEL PADRE"))

    telefonos = _safe_str(row.get("telefonos_encargados")) or pick(
        "TELÉFONOS ENCARGADOS", "TELEFONOS ENCARGADOS"
    )
    validacion = _safe_str(row.get("validacion_raw")) or _safe_str(
        pick("VALIDACION", "VALIDACIÓN")
    )

    correlativo = (
        _to_float(pick("#"))
        or _to_float(row.get("row_num"))
        or _to_float(row.get("rub"))
        or _to_float(row.get("id"))
    )

    return {
        "#": correlativo,
        "ANO": anio,
        "MES": mes,
        "AREA DE SALUD": area_salud,
        "DISTRITO DE SALUD": distrito_salud,
        "SERVICIO DE SALUD": servicio_salud,
        "DEPARTAMENTO DE RESIDENCIA": dep_res,
        "MUNICIPIO DE RESIDENCIA": muni_res,
        "COMUNIDAD RESIDENCIA": comu_res,
        "DIRECCIÓN RESIDENCIA": dir_res,
        "CUI DEL NIÑO": cui_nino,
        "SEXO": sexo,
        "EDAD EN AÑOS": edad_anios,
        "NOMBRE DEL NIÑO": nombre_nino,
        "FECHA NACIMIENTO": fecha_nac,
        "FECHA DEL PRIMER CONTACTO": fecha_contacto,
        "FECHA DE REGISTRO": fecha_registro,
        "CIE-10": cie10,
        "DIAGNÓSTICO": diagnostico,
        "NOMBRE DE LA MADRE": nombre_madre,
        "CUI DE LA MADRE": cui_madre,
        "NOMBRE DEL PADRE": nombre_padre,
        "CUI DEL PADRE": cui_padre,
        "TELÉFONOS ENCARGADOS": telefonos,
        "VALIDACION": validacion,
    }


# =====================================================
# ✅ Payload grande interno (auditoría / debug / futuro)
# =====================================================
def build_bpm_payload_from_staging_row(
    *,
    row: Dict[str, Any],
    anio_carga: int,
    mes_carga: Optional[int],
    renap_validado: bool = True,
    verificacion_sobrevivencia: bool = True,
    familia_cumple_validaciones: bool = True,
) -> Dict[str, Any]:

    raw = _raw_data_to_dict(row.get("raw_data"))

    correlativo = (
        _safe_str(raw.get("#"))
        or _safe_str(row.get("rub"))
        or _safe_str(row.get("row_num"))
        or "N/A"
    )

    anio = int(row.get("anio") or anio_carga)
    mes = int(row.get("mes") or (mes_carga or 0) or 0)

    payload = {
        "renap_validado": bool(renap_validado),
        "verificacion_sobrevivencia": bool(verificacion_sobrevivencia),
        "familia_cumple_validaciones": bool(familia_cumple_validaciones),
        "fila_sesan": raw,
        "meta": {
            "correlativo": correlativo,
            "periodo": f"{mes}/{anio}" if mes else f"{anio}",
        },
    }

    return payload
