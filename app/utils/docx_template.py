from io import BytesIO
from docx import Document

def replace_placeholders_docx_bytes(template_path: str, mapping: dict[str, str]) -> bytes:
    """
    Carga plantilla DOCX, reemplaza placeholders y devuelve el DOCX final en bytes.
    """
    doc = Document(template_path)

    # Etiquetas que requieren negrita
    BOLD_KEYS = ["[NOMBRE DEL TITULAR]", "[NÚMERO DE CUI DEL TITULAR]"]

    def _replace_in_paragraph(p):
        # Si el párrafo no tiene ninguna etiqueta del mapping, no lo procesamos
        if not any(k in p.text for k in mapping.keys()):
            return

        paragraph_text = p.text
        # Limpiamos el párrafo para reconstruirlo palabra por palabra con formato
        p.clear()

        # Ordenamos las llaves por longitud (descendente) para evitar reemplazos parciales erróneos
        sorted_keys = sorted(mapping.keys(), key=len, reverse=True)

        # Usaremos una estrategia de búsqueda y partición para aplicar negritas solo a los valores
        import re
        # Crear un patrón regex que busque todas las llaves del mapping
        pattern = re.compile('|'.join(re.escape(k) for k in sorted_keys))
        
        last_end = 0
        for match in pattern.finditer(paragraph_text):
            # 1. Agregar el texto normal que está ANTES de la etiqueta
            before_text = paragraph_text[last_end:match.start()]
            if before_text:
                p.add_run(before_text)
            
            # 2. Agregar el VALOR de la etiqueta con su formato correspondiente
            key_found = match.group()
            value_to_insert = str(mapping.get(key_found) or "")
            
            run = p.add_run(value_to_insert)
            
            # Aplicar negrita SOLO si es NOMBRE o CUI
            if key_found in BOLD_KEYS:
                run.bold = True
            
            last_end = match.end()

        # 3. Agregar el texto restante después de la última etiqueta
        remaining_text = paragraph_text[last_end:]
        if remaining_text:
            p.add_run(remaining_text)

    # párrafos
    for p in doc.paragraphs:
        _replace_in_paragraph(p)

    # tablas (El RUB usualmente está aquí)
    for t in doc.tables:
        for row in t.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    _replace_in_paragraph(p)

    out = BytesIO()
    doc.save(out)
    out.seek(0)
    return out.getvalue()