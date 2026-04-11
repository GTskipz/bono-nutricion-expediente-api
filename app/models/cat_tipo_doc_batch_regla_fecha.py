from datetime import datetime
from sqlalchemy import String, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class CatTipoDocBatchReglaFecha(Base):
    __tablename__ = "cat_tipo_doc_batch_regla_fecha"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    tipo_doc_id: Mapped[int] = mapped_column(
        ForeignKey("cat_tipo_doc_batch.id"),
        nullable=False
    )

    tipo_doc_referencia_id: Mapped[int] = mapped_column(
        ForeignKey("cat_tipo_doc_batch.id"),
        nullable=False
    )

    operador: Mapped[str] = mapped_column(String(5), nullable=False, default=">=")

    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    mensaje_error: Mapped[str | None] = mapped_column(String(255))

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    # Relaciones opcionales (útiles para joins si luego quieres)
    tipo_doc = relationship(
        "CatTipoDocBatch",
        foreign_keys=[tipo_doc_id]
    )

    tipo_doc_referencia = relationship(
        "CatTipoDocBatch",
        foreign_keys=[tipo_doc_referencia_id]
    )