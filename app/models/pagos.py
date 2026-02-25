from sqlalchemy import (
    BigInteger, Integer, String, Text, DateTime, ForeignKey, Numeric, Boolean
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base


class LotePago(Base):
    __tablename__ = "lote_pago"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    anio_fiscal: Mapped[int] = mapped_column(Integer, nullable=False)
    mes_fiscal: Mapped[int] = mapped_column(Integer, nullable=False)

    monto_por_persona: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    tope_anual_persona: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)

    banco_codigo: Mapped[str] = mapped_column(String(50), nullable=False, default="BANRURAL")
    proveedor_servicio: Mapped[str | None] = mapped_column(String(80), nullable=True)

    estado: Mapped[str] = mapped_column(String(30), nullable=False, default="CREADO")

    creado_por: Mapped[str | None] = mapped_column(String(255), nullable=True)
    creado_en: Mapped[DateTime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    procesado_en: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)

    observacion: Mapped[str | None] = mapped_column(Text, nullable=True)

    total_items: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pagados: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rechazados: Mapped[int | None] = mapped_column(Integer, nullable=True)

    items = relationship(
        "DetallePago",
        back_populates="lote",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class DetallePago(Base):
    __tablename__ = "detalle_pago"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    lote_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("lote_pago.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    expediente_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("expediente_electronico.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    anio_fiscal: Mapped[int] = mapped_column(Integer, nullable=False)
    mes_fiscal: Mapped[int] = mapped_column(Integer, nullable=False)

    estado: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDIENTE")

    monto_asignado: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    acumulado_pagado_antes: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    excede_tope: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    motivo_rechazo: Mapped[str | None] = mapped_column(Text, nullable=True)

    cui_beneficiario: Mapped[str | None] = mapped_column(String(20), nullable=True)
    nombre_beneficiario: Mapped[str | None] = mapped_column(String(255), nullable=True)

    banco_codigo: Mapped[str | None] = mapped_column(String(50), nullable=True, default="BANRURAL")
    numero_cuenta: Mapped[str | None] = mapped_column(String(50), nullable=True)

    proveedor_servicio: Mapped[str | None] = mapped_column(String(80), nullable=True)
    referencia_externa: Mapped[str | None] = mapped_column(String(120), nullable=True)

    request_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    response_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    response_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_servicio: Mapped[str | None] = mapped_column(Text, nullable=True)

    procesado_en: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)

    creado_en: Mapped[DateTime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    actualizado_en: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)

    lote = relationship("LotePago", back_populates="items")