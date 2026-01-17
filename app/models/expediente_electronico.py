from datetime import datetime

from sqlalchemy import String, Integer, DateTime, ForeignKey, BigInteger
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class ExpedienteElectronico(Base):
    __tablename__ = "expediente_electronico"

    # ✅ PK numérica (BIGINT IDENTITY en DB)
    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # Encabezado
    nombre_beneficiario: Mapped[str | None] = mapped_column(String(255))
    cui_beneficiario: Mapped[str | None] = mapped_column(String(50))

    # ✅ NUEVO: RUB (Registro Único de Beneficiario) - VARCHAR sin limitar formato
    rub: Mapped[str | None] = mapped_column(String(100))

    # ✅ Regla MIS (según tu SQL): NOT NULL
    # Nota: en tu SQL dijiste que lo manda el frontend, pero dejamos fallback por seguridad.
    anio_carga: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=lambda: datetime.utcnow().year,
    )

    # Territorio (FK)
    departamento_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("cat_departamento.id"), nullable=True
    )
    municipio_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("cat_municipio.id"), nullable=True
    )

    # Estado MIS
    estado_expediente: Mapped[str] = mapped_column(
        String(30), nullable=False, default="ABIERTO", index=True
    )

    # BPM (snapshot)
    bpm_process_key: Mapped[str | None] = mapped_column(String(120))
    bpm_instance_id: Mapped[str | None] = mapped_column(String(120), unique=True)
    bpm_status: Mapped[str | None] = mapped_column(String(30), index=True)
    bpm_current_task_key: Mapped[str | None] = mapped_column(String(120))
    bpm_current_task_name: Mapped[str | None] = mapped_column(String(255))
    bpm_variables: Mapped[dict | None] = mapped_column(JSONB)
    bpm_last_sync_at: Mapped[datetime | None] = mapped_column(DateTime)

    # Resumen documentos obligatorios (lo llena el trigger)
    docs_required_status: Mapped[dict | None] = mapped_column(JSONB)

    # Relación 1:1 con info_general
    info_general = relationship(
        "InfoGeneral",
        uselist=False,
        back_populates="expediente",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
