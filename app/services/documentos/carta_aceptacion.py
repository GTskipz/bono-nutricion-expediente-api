from sqlalchemy.orm import Session
from app.utils.docx_template import replace_placeholders_docx_bytes
from app.utils.docx_to_pdf import docx_bytes_to_pdf_bytes

from app.models.expediente_electronico import ExpedienteElectronico
from app.models.info_general import InfoGeneral
from app.models.cat_departamento import CatDepartamento
from app.models.cat_municipio import CatMunicipio

TEMPLATE_PATH = "app/templates/Carta_Aceptacion_Bono_Nutricion.docx"


def generar_carta_aceptacion_docx_bytes(expediente_id: int, db: Session) -> tuple[bytes, str]:
    exp = db.query(ExpedienteElectronico).filter_by(id=expediente_id).first()
    if not exp:
        raise ValueError("Expediente no encontrado")

    ig = db.query(InfoGeneral).filter_by(expediente_id=exp.id).first()
    if not ig:
        raise ValueError("Expediente sin información general")

    dep = (
        db.query(CatDepartamento)
        .filter_by(id=ig.departamento_residencia_id)
        .first()
        if ig.departamento_residencia_id
        else None
    )

    mun = (
        db.query(CatMunicipio)
        .filter_by(id=ig.municipio_residencia_id)
        .first()
        if ig.municipio_residencia_id
        else None
    )

    # ✅ RUB con fallback seguro
    rub = getattr(exp, "rub", None) or "000000000"

    # ✅ Titular real del expediente (no la madre)
    titular_nombre = (exp.titular_nombre or "").strip()
    titular_dpi = (exp.titular_dpi or "").strip()

    mapping = {
        "[NOMBRE DEL TITULAR]": titular_nombre,
        "[NÚMERO DE CUI DEL TITULAR]": titular_dpi,
        "[MUNICIPIO]": mun.nombre if mun else "",
        "[DEPARTAMENTO]": dep.nombre if dep else "",
        "[Código RUB]": rub,
        "000000000": rub,  # respaldo si quedó literal en plantilla
    }

    docx_bytes = replace_placeholders_docx_bytes(TEMPLATE_PATH, mapping)
    filename = f"Carta_Aceptacion_{rub}.docx"

    return docx_bytes, filename

# Generación PDF con negritas)
def generar_carta_aceptacion_pdf_bytes(expediente_id: int, db: Session) -> tuple[bytes, str]:
    """
    Genera el documento Word con los reemplazos y negritas aplicadas, 
    y lo convierte a PDF antes de retornar los bytes.
    """
    # 1. Generamos el DOCX usando la lógica existente (que ya aplica negritas en la utilidad template)
    docx_bytes, filename_docx = generar_carta_aceptacion_docx_bytes(expediente_id, db)
    
    # 2. Convertimos los bytes de DOCX a PDF usando la utilidad que soporta negritas
    pdf_bytes = docx_bytes_to_pdf_bytes(docx_bytes)
    
    # 3. Generamos el nombre del archivo con extensión .pdf
    filename_pdf = filename_docx.replace(".docx", ".pdf")
    
    return pdf_bytes, filename_pdf
