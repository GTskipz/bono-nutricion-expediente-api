import uuid
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Text, BigInteger
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base

class DocumentosYAnexos(Base):
    __tablename__ = "documentos_y_anexos"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    expediente_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    tab: Mapped[str] = mapped_column(String(20), nullable=False)  # DOCUMENTOS | ANEXOS
    tipo_documento_id: Mapped[int | None] = mapped_column(Integer)
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="NO_ADJUNTADO")

    filename: Mapped[str | None] = mapped_column(String(255))
    mime_type: Mapped[str | None] = mapped_column(String(120))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    storage_provider: Mapped[str | None] = mapped_column(String(30))
    storage_key: Mapped[str | None] = mapped_column(String(500))
    checksum_sha256: Mapped[str | None] = mapped_column(String(64))

    subido_por: Mapped[str | None] = mapped_column(String(120))
    observacion: Mapped[str | None] = mapped_column(Text)
    descripcion: Mapped[str | None] = mapped_column(String(250))
