from datetime import datetime

from sqlalchemy import String, Text, DateTime, BigInteger, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class TrackingEvento(Base):
    __tablename__ = "tracking_evento"

    # ✅ PK numérica
    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    # ✅ FK numérica al expediente
    expediente_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("expediente_electronico.id", ondelete="CASCADE"),
        nullable=False,
        index=True,  # recomendado para consultas por expediente
    )

    fecha_evento: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    titulo: Mapped[str] = mapped_column(String(255), nullable=False)
    usuario: Mapped[str | None] = mapped_column(String(255))
    observacion: Mapped[str | None] = mapped_column(Text)

    origen: Mapped[str | None] = mapped_column(String(30))
    tipo_evento: Mapped[str | None] = mapped_column(String(50))
