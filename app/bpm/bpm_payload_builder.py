# app/bpm/bpm_payload_builder.py
from __future__ import annotations

from typing import Any, Dict, Optional
from datetime import date, datetime

import json


def _iso(v: Any) -> Optional[str]:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    # si ya viene como "YYYY-MM-DD"
    return str(v)


def _safe_str(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def _raw_data_to_dict(raw_data: Any) -> Dict[str, Any]:
    """
    raw_data en tu staging puede venir como:
    - dict (si SQLAlchemy ya lo parseó)
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

    # otros tipos
    return {}


def build_bpm_payload_from_staging_row(
    *,
    row: Dict[str, Any],
    anio_carga: int,
    mes_carga: Optional[int],
    renap_validado: bool = True,
    verificacion_sobrevivencia: bool = True,
    familia_cumple_validaciones: bool = True,
) -> Dict[str, Any]:
    """
    Recibe la 'row' TAL COMO TE LLEGA en _procesar_row_creando_expediente (mappings().first()).
    Devuelve el JSON a enviar al BPM con una estructura como el ejemplo que pusiste.
    """

    raw = _raw_data_to_dict(row.get("raw_data"))

    # Intento de RUB/correlativo:
    # - si tu staging tiene rub, lo ponemos en correlativo
    # - si en raw venía "#" lo usamos
    correlativo = _safe_str(raw.get("#")) or _safe_str(row.get("rub")) or _safe_str(row.get("row_num")) or "N/A"

    anio = int(row.get("anio") or anio_carga)
    mes = int(row.get("mes") or (mes_carga or 0) or 0)

    # Campos base (staging)
    beneficiario_nombre = _safe_str(row.get("nombre_nino"))
    beneficiario_cui = _safe_str(row.get("cui_nino"))
    beneficiario_sexo = _safe_str(row.get("sexo"))
    fecha_nac = _iso(row.get("fecha_nacimiento"))
    fecha_contacto = _iso(row.get("fecha_primer_contacto"))
    fecha_registro = _iso(row.get("fecha_registro"))

    diagnostico = _safe_str(row.get("diagnostico")) or _safe_str(raw.get("DIAGNÓSTICO")) or _safe_str(raw.get("DIAGNOSTICO"))
    cie_10 = _safe_str(row.get("cie_10")) or _safe_str(raw.get("CIE-10")) or _safe_str(raw.get("CIE 10"))

    dep = _safe_str(row.get("departamento_residencia"))
    muni = _safe_str(row.get("municipio_residencia"))
    comu = _safe_str(row.get("comunidad_residencia"))
    dire = _safe_str(row.get("direccion_residencia"))

    madre = _safe_str(row.get("nombre_madre"))
    cui_madre = _safe_str(row.get("cui_madre"))
    padre = _safe_str(row.get("nombre_padre"))
    cui_padre = _safe_str(row.get("cui_padre"))
    tels = _safe_str(row.get("telefonos_encargados")) or "N/A"

    validacion = _safe_str(row.get("validacion_raw")) or _safe_str(raw.get("VALIDACION")) or "N/A"

    servicio_salud = _safe_str(row.get("servicio_salud"))
    area_salud = _safe_str(row.get("area_salud")) or "N/A"
    distrito_salud = _safe_str(row.get("distrito_salud"))

    # Sección control
    periodo = f"{mes}/{anio}" if mes else f"{anio}"

    payload = {
        "renap_validado": bool(renap_validado),
        "verificacion_sobrevivencia": bool(verificacion_sobrevivencia),
        "familia_cumple_validaciones": bool(familia_cumple_validaciones),

        # ✅ Audit: fila original (si existe raw_data) + campos “bonitos”
        "fila_sesan": raw,

        # ✅ Secciones consolidadas
        "data": {
            "seccion_menor": {
                "beneficiario_nombre": beneficiario_nombre,
                "beneficiario_cui": beneficiario_cui,
                "beneficiario_sexo": beneficiario_sexo,
                "beneficiario_fecha_nacimiento": fecha_nac,
                "edad_anos": _safe_str(row.get("edad_en_anios")) or "N/A",
            },
            "seccion_salud": {
                "diagnostico": diagnostico,
                "cie_10": cie_10,
                "servicio_salud": servicio_salud,
                "area_salud": area_salud,
                "distrito_salud": distrito_salud,
                "fecha_registro": fecha_registro,
                "fecha_contacto": fecha_contacto,
            },
            "seccion_ubicacion": {
                "residencia_departamento": dep,
                "residencia_municipio": muni,
                "residencia_comunidad": comu,
                "residencia_direccion": dire,
            },
            "seccion_padres": {
                "nombre_madre": madre,
                "dpi_madre": cui_madre,
                "nombre_padre": padre,
                "dpi_padre": cui_padre,
                "telefonos": tels,
            },
            "seccion_control": {
                "correlativo": correlativo,
                "periodo": periodo,
                "validacion_sesan": validacion,
            },

            # Estos campos pueden existir o no todavía; el BPM real te dirá el contrato final.
            # Los dejamos mínimos y el BPM STUB los ignora.
            "consistencia_valida": True,
            "duplicado_encontrado": False,
        },

        # “Top-level” resumen (puedes dejarlo, o removerlo; no rompe nada)
        "edad_menor": None,
        "diagnostico": "Desnutrición Aguda" if diagnostico else None,
        "resultado_elegibilidad": None,
        "monto_bono": None,
        "observaciones": None,
        "seccion_titular": None,
    }

    return payload
