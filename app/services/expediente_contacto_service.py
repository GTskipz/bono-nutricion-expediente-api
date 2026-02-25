from sqlalchemy.orm import Session
from sqlalchemy import text

from app.services.tracking_evento_service import TrackingEventoService


def get_contacto_expediente(db: Session, expediente_id: int):
    row = db.execute(
        text("""
            SELECT
                c.expediente_id,
                c.nombre_contacto,
                c.departamento_id,
                d.nombre AS departamento_nombre,
                c.municipio_id,
                m.nombre AS municipio_nombre,
                c.poblado,
                c.direccion,
                c.anotaciones_direccion,
                c.telefono_1,
                c.telefono_2
            FROM expediente_contacto c
            JOIN cat_departamento d ON d.id = c.departamento_id
            JOIN cat_municipio m ON m.id = c.municipio_id
            WHERE c.expediente_id = :expediente_id
            LIMIT 1
        """),
        {"expediente_id": expediente_id},
    ).mappings().first()

    if not row:
        return None

    return dict(row)


def upsert_contacto_expediente(db: Session, expediente_id: int, payload, usuario: str | None = None):
    """
    Upsert de contacto por expediente.
    ✅ Registra evento importante en tracking_evento:
       - DOCS_SUBIDOS NO aplica aquí
       - Se registra como evento de EXPEDIENTE (cambio de datos de contacto)
    """

    # validar que exista expediente
    exists = db.execute(
        text("""
            SELECT id
            FROM expediente_electronico
            WHERE id = :id
            LIMIT 1
        """),
        {"id": expediente_id},
    ).mappings().first()

    if not exists:
        return None

    # detectar si ya existía contacto (para distinguir creado vs actualizado)
    existed_contact = db.execute(
        text("""
            SELECT 1
            FROM expediente_contacto
            WHERE expediente_id = :expediente_id
            LIMIT 1
        """),
        {"expediente_id": expediente_id},
    ).mappings().first() is not None

    def s(v):
        return v.strip() if isinstance(v, str) else v

    db.execute(
        text("""
            INSERT INTO expediente_contacto (
                expediente_id,
                nombre_contacto,
                departamento_id,
                municipio_id,
                poblado,
                direccion,
                anotaciones_direccion,
                telefono_1,
                telefono_2,
                updated_at
            )
            VALUES (
                :expediente_id,
                :nombre_contacto,
                :departamento_id,
                :municipio_id,
                :poblado,
                :direccion,
                :anotaciones_direccion,
                :telefono_1,
                :telefono_2,
                NOW()
            )
            ON CONFLICT (expediente_id)
            DO UPDATE SET
                nombre_contacto = EXCLUDED.nombre_contacto,
                departamento_id = EXCLUDED.departamento_id,
                municipio_id = EXCLUDED.municipio_id,
                poblado = EXCLUDED.poblado,
                direccion = EXCLUDED.direccion,
                anotaciones_direccion = EXCLUDED.anotaciones_direccion,
                telefono_1 = EXCLUDED.telefono_1,
                telefono_2 = EXCLUDED.telefono_2,
                updated_at = NOW()
        """),
        {
            "expediente_id": expediente_id,
            "nombre_contacto": s(payload.nombre_contacto) or "",
            "departamento_id": payload.departamento_id,
            "municipio_id": payload.municipio_id,
            "poblado": payload.poblado,
            "direccion": payload.direccion,
            "anotaciones_direccion": payload.anotaciones_direccion,
            "telefono_1": payload.telefono_1,
            "telefono_2": payload.telefono_2,
        },
    )

    # ✅ TRACKING IMPORTANTE (historial del expediente)
    titulo = "Contacto actualizado" if existed_contact else "Contacto registrado"
    TrackingEventoService._registrar(
        db,
        expediente_id=int(expediente_id),
        titulo=titulo,
        origen=TrackingEventoService.ORIGEN_EXPEDIENTE,
        tipo_evento="CONTACTO_UPSERT",
        usuario=usuario,
        observacion=(
            f"Nombre: {s(payload.nombre_contacto) or ''} | "
            f"Depto ID: {payload.departamento_id} | Mun ID: {payload.municipio_id}"
        ),
        commit=False,
    )

    db.commit()

    return get_contacto_expediente(db, expediente_id)