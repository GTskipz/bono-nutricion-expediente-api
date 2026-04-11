from sqlalchemy import BigInteger, String, Text, TIMESTAMP, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime

from app.core.db import Base


class SesanBatchProceso(Base):
    __tablename__ = "sesan_batch_proceso"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    batch_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("sesan_batch.id", ondelete="CASCADE"),
        nullable=False
    )

    estado: Mapped[str] = mapped_column(String(50), nullable=False)

    iniciado_por: Mapped[str | None] = mapped_column(String(100))

    iniciado_en: Mapped[datetime] = mapped_column(
        TIMESTAMP, default=datetime.utcnow
    )

    ultima_actualizacion: Mapped[datetime] = mapped_column(
        TIMESTAMP, default=datetime.utcnow
    )

    finalizado_en: Mapped[datetime | None] = mapped_column(TIMESTAMP)

    mensaje_error: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, default=datetime.utcnow
    )

    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, default=datetime.utcnow
    )