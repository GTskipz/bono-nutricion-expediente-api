from io import BytesIO
from docx import Document
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfbase.pdfmetrics import stringWidth

def docx_bytes_to_pdf_bytes(docx_bytes: bytes) -> bytes:
    """
    Convierte DOCX -> PDF en memoria (sin LibreOffice / sin WeasyPrint).
    Enfoque simple para pruebas: extrae párrafos y los imprime con salto de línea
    y wrapping básico.
    """
    doc = Document(BytesIO(docx_bytes))

    out = BytesIO()
    c = canvas.Canvas(out, pagesize=LETTER)
    width, height = LETTER

    # Márgenes y estilo
    left = 50
    right = 50
    top = 60
    bottom = 50
    max_width = width - left - right

    font_name = "Helvetica"
    font_size = 11
    line_height = 14

    c.setFont(font_name, font_size)

    y = height - top

    def wrap_line(text: str) -> list[str]:
        """Wrap básico por ancho usando métricas de ReportLab."""
        words = (text or "").split()
        if not words:
            return [""]

        lines = []
        current = words[0]
        for w in words[1:]:
            test = current + " " + w
            if stringWidth(test, font_name, font_size) <= max_width:
                current = test
            else:
                lines.append(current)
                current = w
        lines.append(current)
        return lines

    def ensure_space():
        nonlocal y
        if y < bottom + line_height:
            c.showPage()
            c.setFont(font_name, font_size)
            y = height - top

    for p in doc.paragraphs:
        text = (p.text or "").strip()

        # Espacio entre párrafos
        if not text:
            y -= line_height
            ensure_space()
            continue

        for line in wrap_line(text):
            ensure_space()
            c.drawString(left, y, line)
            y -= line_height

        # separación extra entre párrafos
        y -= 6

    c.save()
    out.seek(0)
    return out.getvalue()
