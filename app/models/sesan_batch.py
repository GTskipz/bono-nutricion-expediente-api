from sqlalchemy import (
    Column,
    BigInteger,
    Integer,
    String,
    Text,
    DateTime,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.db import Base


class SesanBatch(Base):
    __tablename__ = "sesan_batch"

    id = Column(BigInteger, primary_key=True, index=True)

    nombre_lote = Column(String(200), nullable=False)
    descripcion = Column(Text, nullable=True)
    origen = Column(String(50), nullable=False)

    anio_carga = Column(Integer, nullable=False)
    mes_carga = Column(Integer, nullable=False)

    usuario_carga = Column(String(200), nullable=True)

    archivo_nombre_original = Column(String(255), nullable=True)
    archivo_mime_type = Column(String(150), nullable=True)
    archivo_size_bytes = Column(BigInteger, nullable=True)
    storage_provider = Column(String(50), nullable=True)
    storage_key = Column(String(500), nullable=True)
    checksum_sha256 = Column(String(64), nullable=True)

    estado = Column(String(50), nullable=False, default="CARGADO")

    total_registros = Column(Integer, nullable=False, default=0)
    total_pendientes = Column(Integer, nullable=False, default=0)
    total_procesados = Column(Integer, nullable=False, default=0)
    total_error = Column(Integer, nullable=False, default=0)
    total_ignorados = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relación con documentos
    documentos = relationship(
        "SesanBatchDocumento",
        back_populates="batch",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
