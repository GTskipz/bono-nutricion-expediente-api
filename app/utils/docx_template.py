from io import BytesIO
from docx import Document
from docx.shared import Pt
import re

def replace_placeholders_docx_bytes(template_path: str, mapping: dict[str, str]) -> bytes:
    """
    Carga plantilla DOCX, reemplaza placeholders y aplica una reducción 
    de fuente (8pt / 7pt) para garantizar que el documento quepa en una sola página.
    """
    doc = Document(template_path)

    # Etiquetas que requieren negrita
    BOLD_KEYS = ["[NOMBRE DEL TITULAR]", "[NÚMERO DE CUI DEL TITULAR]"]
    
    # Fuente general del documento (Muy compacta)
    GLOBAL_TEXT_SIZE = Pt(8)
    # Bloque del titular (Recuadro rojo)
    CRITICAL_DATA_SIZE = Pt(7)

    def _replace_in_paragraph(p):
        # 1. Reducción total de todo el texto existente en el párrafo (heredado del Word)
        for run in p.runs:
            run.font.size = GLOBAL_TEXT_SIZE

        # Si el párrafo no tiene etiquetas del mapping, no procesamos el reemplazo dinámico
        if not any(k in p.text for k in mapping.keys()):
            return

        paragraph_text = p.text
        # Limpiamos el párrafo para reconstruirlo palabra por palabra con formato
        p.clear()

        sorted_keys = sorted(mapping.keys(), key=len, reverse=True)
        pattern = re.compile('|'.join(re.escape(k) for k in sorted_keys))
        
        last_end = 0
        for match in pattern.finditer(paragraph_text):
            # 2. Texto antes de la etiqueta
            before_text = paragraph_text[last_end:match.start()]
            if before_text:
                run_before = p.add_run(before_text)
                # Si el párrafo es el del titular, usamos el tamaño crítico
                is_critical_p = any(bk in paragraph_text for bk in BOLD_KEYS)
                run_before.font.size = CRITICAL_DATA_SIZE if is_critical_p else GLOBAL_TEXT_SIZE
            
            # 3. Valor de la etiqueta (CUI, Nombre, RUB, etc)
            key_found = match.group()
            value_to_insert = str(mapping.get(key_found) or "")
            
            run = p.add_run(value_to_insert)
            
            if key_found in BOLD_KEYS:
                run.bold = True
                run.font.size = CRITICAL_DATA_SIZE
            else:
                run.font.size = GLOBAL_TEXT_SIZE
            
            last_end = match.end()

        # 4. Texto restante tras la última etiqueta
        remaining_text = paragraph_text[last_end:]
        if remaining_text:
            run_after = p.add_run(remaining_text)
            is_critical_p = any(bk in paragraph_text for bk in BOLD_KEYS)
            run_after.font.size = CRITICAL_DATA_SIZE if is_critical_p else GLOBAL_TEXT_SIZE

    # --- PROCESAMIENTO TOTAL ---

    # Procesar todos los párrafos principales
    for p in doc.paragraphs:
        _replace_in_paragraph(p)

    # Procesar tablas (Donde están las firmas, el sello y el RUB)
    # Esta parte es vital porque las tablas suelen tener márgenes internos que empujan el texto
    for t in doc.tables:
        for row in t.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    # Forzamos reducción de fuente en cada run de la celda
                    for run in p.runs:
                        run.font.size = GLOBAL_TEXT_SIZE
                    _replace_in_paragraph(p)

    out = BytesIO()
    doc.save(out)
    out.seek(0)
    return out.getvalue()