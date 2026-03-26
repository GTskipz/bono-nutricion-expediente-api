import subprocess
import os
import tempfile
import shutil
from io import BytesIO
from docx import Document

# Nota: Se mantienen los imports de reportlab solo por si otras partes 
# del sistema los requieren, pero ya no se usan para esta conversión.
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfbase.pdfmetrics import stringWidth

def docx_bytes_to_pdf_bytes(docx_bytes: bytes) -> bytes:
    """
    Convierte DOCX -> PDF usando LibreOffice en modo headless (Requerimiento 28).
    Este motor garantiza que imágenes, logos y tablas se mantengan idénticos al original.
    """
    
    # --- INICIO DE CAMBIO: Motor de conversión profesional vía LibreOffice ---
    
    # Creamos un directorio temporal único para procesar el archivo
    temp_dir = tempfile.mkdtemp()
    try:
        # 1. Guardamos los bytes del DOCX recibido en un archivo físico temporal
        input_path = os.path.join(temp_dir, "documento.docx")
        with open(input_path, "wb") as f:
            f.write(docx_bytes)

        # 2. Ejecutamos LibreOffice (instalado en el Dockerfile) para convertir
        # Se usa UserInstallation para evitar conflictos de permisos en el contenedor
        user_profile = f"file://{temp_dir}/profile"
        
        subprocess.run([
            "libreoffice",
            f"-env:UserInstallation={user_profile}",
            "--headless",
            "--convert-to", "pdf",
            "--outdir", temp_dir,
            input_path
        ], check=True, capture_output=True)

        # 3. Localizamos y leemos el archivo PDF generado por LibreOffice
        pdf_path = os.path.join(temp_dir, "documento.pdf")
        
        if not os.path.exists(pdf_path):
            raise FileNotFoundError("LibreOffice no generó el archivo PDF.")
            
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        return pdf_bytes

    except Exception as e:
        # Error detallado en caso de que LibreOffice no responda
        print(f"Error crítico en la conversión de LibreOffice: {e}")
        raise RuntimeError(f"No se pudo convertir el documento a PDF: {str(e)}")
        
    finally:
        # Limpieza absoluta de archivos temporales para no llenar el contenedor
        shutil.rmtree(temp_dir)
        
    # --- FIN DE CAMBIO ---

# Se mantienen las funciones auxiliares originales intactas por estructura de archivo
def wrap_line(text: str) -> list[str]:
    """Wrap básico por ancho (Legacy)."""
    return [text]

def ensure_space():
    """Control de espacio (Legacy)."""
    pass