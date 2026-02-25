from sqlalchemy import (
    Column,
    BigInteger,
    String,
    Text,
    Boolean,
    Integer,
    DateTime,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.db import Base


class CatTipoDocBatch(Base):
    __tablename__ = "cat_tipo_doc_batch"

    id = Column(BigInteger, primary_key=True, index=True)

    codigo = Column(String(60), nullable=False, unique=True)
    nombre = Column(String(200), nullable=False)
    descripcion = Column(Text, nullable=True)
    origen = Column(String(60), nullable=True)

    requerido = Column(Boolean, nullable=False, default=False)
    orden = Column(Integer, nullable=False, default=0)
    activo = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    documentos = relationship(
        "SesanBatchDocumento",
        back_populates="tipo",
        lazy="selectin",
    )
