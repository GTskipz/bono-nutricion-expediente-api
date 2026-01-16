import uuid
from datetime import datetime

from sqlalchemy import String, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class ExpedienteElectronico(Base):
    __tablename__ = "expediente_electronico"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
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

    # ✅ Regla MIS (según tu SQL): NOT NULL
    anio_carga: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=lambda: datetime.utcnow().year,  # fallback si no viene
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
        String(30), nullable=False, default="ABIERTO"
    )

    # BPM (snapshot)
    bpm_process_key: Mapped[str | None] = mapped_column(String(120))
    bpm_instance_id: Mapped[str | None] = mapped_column(String(120), unique=True)
    bpm_status: Mapped[str | None] = mapped_column(String(30))
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
