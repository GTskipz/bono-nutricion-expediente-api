from sqlalchemy import (
    Column,
    BigInteger,
    String,
    Date,
    DateTime,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.db import Base


class SesanBatchDocumento(Base):
    __tablename__ = "sesan_batch_documento"

    id = Column(BigInteger, primary_key=True, index=True)

    batch_id = Column(
        BigInteger,
        ForeignKey("sesan_batch.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    tipo_doc_id = Column(
        BigInteger,
        ForeignKey("cat_tipo_doc_batch.id"),
        nullable=False,
        index=True,
    )

    # Placeholder permitido
    fecha_documento = Column(Date, nullable=True)

    archivo_nombre_original = Column(String(255), nullable=True)
    archivo_mime_type = Column(String(120), nullable=True)
    archivo_size_bytes = Column(BigInteger, nullable=True)

    storage_provider = Column(String(50), nullable=True)
    storage_key = Column(String(500), nullable=True)
    checksum_sha256 = Column(String(64), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "batch_id",
            "tipo_doc_id",
            name="uq_sesan_batch_documento_batch_tipo",
        ),
    )

    # Relaciones
    batch = relationship("SesanBatch", back_populates="documentos", lazy="selectin")
    tipo = relationship("CatTipoDocBatch", back_populates="documentos", lazy="selectin")
