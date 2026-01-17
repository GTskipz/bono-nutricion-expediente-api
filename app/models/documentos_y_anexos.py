from datetime import datetime

from sqlalchemy import (
    String,
    Integer,
    DateTime,
    Text,
    BigInteger,
    ForeignKey,
    CheckConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class DocumentosYAnexos(Base):
    __tablename__ = "documentos_y_anexos"

    __table_args__ = (
        CheckConstraint("tab IN ('DOCUMENTOS','ANEXOS')", name="chk_doc_tab"),
        CheckConstraint(
            "estado IN ('NO_ADJUNTADO','ADJUNTADO','RECHAZADO')",
            name="chk_doc_estado",
        ),
    )

    # ✅ PK numérica
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

    # ✅ FK numérica al expediente
    expediente_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("expediente_electronico.id", ondelete="CASCADE"),
        nullable=False,
    )

    tab: Mapped[str] = mapped_column(String(20), nullable=False)  # DOCUMENTOS | ANEXOS

    # FK a catálogo tipo documento
    tipo_documento_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("cat_tipo_documento.id")
    )

    estado: Mapped[str] = mapped_column(
        String(20), nullable=False, default="NO_ADJUNTADO"
    )

    filename: Mapped[str | None] = mapped_column(String(255))
    mime_type: Mapped[str | None] = mapped_column(String(120))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)

    storage_provider: Mapped[str | None] = mapped_column(String(80))
    storage_key: Mapped[str | None] = mapped_column(String(500))

    checksum_sha256: Mapped[str | None] = mapped_column(String(80))

    subido_por: Mapped[str | None] = mapped_column(String(255))
    observacion: Mapped[str | None] = mapped_column(Text)
    descripcion: Mapped[str | None] = mapped_column(String(255))
