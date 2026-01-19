from __future__ import annotations

from fastapi import HTTPException
from io import BytesIO
import openpyxl
import re
import unicodedata


def norm_header(s) -> str:
    """
    Normaliza headers para matching flexible:
    - trim
    - uppercase
    - quita acentos (AÑO->ANO, NIÑO->NINO)
    - deja A-Z0-9 y espacios
    - colapsa espacios

    ✅ Caso especial: si el header literal es "#", significa RUB.
    """
    if s is None:
        return ""
    raw = str(s).strip()

    if raw == "#":
        return "RUB"

    s = raw.upper()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^A-Z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def find_header_row(ws, max_scan_rows=40, max_scan_cols=80) -> int | None:
    """
    Busca la fila donde están los encabezados.
    Heurística: fila que contiene (normalizado) al menos estos “mínimos”:
      - CUI DEL NINO (o variantes)
      - NOMBRE DEL NINO (o variantes)
      - ANO / MES
    """
    triggers = [
        {"CUI DEL NINO", "CUI NINO", "CUI"},
        {"NOMBRE DEL NINO", "NOMBRE NINO"},
        {"ANO", "ANIO", "AÑO"},
        {"MES"},
    ]

    best_row = None
    best_score = -1

    for r in range(1, max_scan_rows + 1):
        row_vals = [ws.cell(r, c).value for c in range(1, max_scan_cols + 1)]
        norm_vals = {norm_header(v) for v in row_vals if v not in (None, "")}

        score = 0
        for group in triggers:
            if any(g in norm_vals for g in group):
                score += 1

        if score > best_score:
            best_score = score
            best_row = r

        if score == len(triggers):
            return r

    if best_score >= 3:
        return best_row
    return None


def read_sesan_xlsx_rows(file_bytes: bytes) -> list[dict]:
    """
    Lee el Excel SESAN en memoria.
    - Detecta la fila real del header automáticamente.
    - Normaliza headers (acentos, símbolos, dobles espacios).
    - No exige “25 columnas fijas”; solo exige mínimas.
    - Permite columnas extra (se guardan en raw_data).
    - Devuelve filas con keys canónicas para insertar staging.
    """
    bio = BytesIO(file_bytes)
    wb = openpyxl.load_workbook(bio, data_only=True)

    ws = wb["SEVEROS"] if "SEVEROS" in wb.sheetnames else wb.active

    header_row = find_header_row(ws)
    if not header_row:
        raise HTTPException(
            status_code=422,
            detail="No se pudo detectar el encabezado del archivo SESAN (fila de títulos).",
        )

    max_cols = min(int(ws.max_column or 0) or 80, 120)
    raw_headers = [ws.cell(row=header_row, column=c).value for c in range(1, max_cols + 1)]
    norm_headers = [norm_header(h) for h in raw_headers]

    ALIASES = {
        "CIE 10": "CIE 10",
        "CIE-10": "CIE 10",
        "CIE_10": "CIE 10",
        "COMUNIDAD DE RESIDENCIA": "COMUNIDAD RESIDENCIA",
        "DIRECCION DE RESIDENCIA": "DIRECCION RESIDENCIA",
        "TELEFONOS DEL ENCARGADO": "TELEFONOS ENCARGADOS",
        "TELEFONO ENCARGADOS": "TELEFONOS ENCARGADOS",
        "TELEFONO DEL ENCARGADO": "TELEFONOS ENCARGADOS",
        "EDAD EN ANIOS": "EDAD EN ANOS",
        "EDAD EN AÑOS": "EDAD EN ANOS",
        "CUI DEL NIÑO": "CUI DEL NINO",
        "NOMBRE DEL NIÑO": "NOMBRE DEL NINO",
        "AÑO": "ANO",
        "ANIO": "ANO",
        "REGISTRO UNICO DE BENEFICIARIO": "RUB",
        "REGISTRO ÚNICO DE BENEFICIARIO": "RUB",
        "REGISTRO UNICO BENEFICIARIO": "RUB",
        "REGISTRO ÚNICO BENEFICIARIO": "RUB",
    }
    norm_headers = [ALIASES.get(h, h) for h in norm_headers]

    CANON = {
        "RUB": "RUB",
        "ANO": "ANO",
        "MES": "MES",
        "AREA DE SALUD": "AREA_DE_SALUD",
        "DISTRITO DE SALUD": "DISTRITO_DE_SALUD",
        "SERVICIO DE SALUD": "SERVICIO_DE_SALUD",
        "DEPARTAMENTO DE RESIDENCIA": "DEPTO_RESIDENCIA",
        "MUNICIPIO DE RESIDENCIA": "MUNI_RESIDENCIA",
        "COMUNIDAD RESIDENCIA": "COMUNIDAD_RESIDENCIA",
        "DIRECCION RESIDENCIA": "DIRECCION_RESIDENCIA",
        "CUI DEL NINO": "CUI_NINO",
        "SEXO": "SEXO",
        "EDAD EN ANOS": "EDAD_EN_ANOS",
        "NOMBRE DEL NINO": "NOMBRE_NINO",
        "FECHA NACIMIENTO": "FECHA_NACIMIENTO",
        "FECHA DEL PRIMER CONTACTO": "FECHA_PRIMER_CONTACTO",
        "FECHA DE REGISTRO": "FECHA_REGISTRO",
        "CIE 10": "CIE_10",
        "CIE_10": "CIE_10",
        "DIAGNOSTICO": "DIAGNOSTICO",
        "NOMBRE DE LA MADRE": "NOMBRE_MADRE",
        "CUI DE LA MADRE": "CUI_MADRE",
        "NOMBRE DEL PADRE": "NOMBRE_PADRE",
        "CUI DEL PADRE": "CUI_PADRE",
        "TELEFONOS ENCARGADOS": "TELEFONOS_ENCARGADOS",
        "VALIDACION": "VALIDACION",
    }

    present = {h for h in norm_headers if h}
    required_min = {"CUI DEL NINO", "NOMBRE DEL NINO", "ANO", "MES"}  # RUB es opcional
    missing = sorted(required_min - present)
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Estructura del archivo SESAN no coincide (faltan columnas críticas mínimas): {missing}",
        )

    col_to_key: dict[int, str] = {}
    for idx, h in enumerate(norm_headers, start=1):
        if h in CANON:
            col_to_key[idx] = CANON[h]

    rows: list[dict] = []
    for r in range(header_row + 1, ws.max_row + 1):
        empty = 0
        row_canon: dict[str, object] = {}
        row_raw: dict[str, object] = {}

        for c in range(1, max_cols + 1):
            val = ws.cell(row=r, column=c).value
            hdr = norm_headers[c - 1] or f"COL_{c}"
            row_raw[hdr] = val

            if val is None or str(val).strip() == "":
                empty += 1

            key = col_to_key.get(c)
            if key:
                row_canon[key] = val

        if empty == max_cols:
            continue

        rows.append({"excel_row": r, "data": row_canon, "raw": row_raw})

    return rows
