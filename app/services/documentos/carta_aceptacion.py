from sqlalchemy.orm import Session
from app.utils.docx_template import replace_placeholders_docx_bytes

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
