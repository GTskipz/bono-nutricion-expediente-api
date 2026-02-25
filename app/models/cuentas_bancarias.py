from sqlalchemy import (
    Column, BigInteger, String, Text, DateTime, ForeignKey, Integer
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB

from app.core.db import Base


class LoteAperturaCuenta(Base):
    __tablename__ = "lote_apertura_cuenta"

    id = Column(BigInteger, primary_key=True)

    banco_codigo = Column(String(50), nullable=False, default="BANRURAL")
    estado = Column(String(30), nullable=False, default="CREADO")

    # ✅ NUEVO: proveedor del servicio externo (si aplica a nivel lote)
    proveedor_servicio = Column(String(80), nullable=True)

    # (si aún los usas para archivos internos, se mantienen)
    archivo_solicitud_id = Column(BigInteger, nullable=True)
    archivo_respuesta_id = Column(BigInteger, nullable=True)

    creado_por = Column(String(255), nullable=True)
    creado_en = Column(DateTime, nullable=False, server_default=func.now())

    observacion = Column(Text, nullable=True)

    # ✅ NUEVO: marca cuándo se procesó el lote (cuando corre /procesar)
    procesado_en = Column(DateTime, nullable=True)

    items = relationship(
        "DetalleAperturaCuenta",
        back_populates="lote",
        cascade="all, delete-orphan",
    )


class DetalleAperturaCuenta(Base):
    __tablename__ = "detalle_apertura_cuenta"

    id = Column(BigInteger, primary_key=True)

    lote_id = Column(BigInteger, ForeignKey("lote_apertura_cuenta.id", ondelete="CASCADE"), nullable=False)
    expediente_id = Column(BigInteger, ForeignKey("expediente_electronico.id", ondelete="RESTRICT"), nullable=False)

    estado = Column(String(30), nullable=False, default="PENDIENTE")

    cui_beneficiario = Column(String(20), nullable=True)
    nombre_beneficiario = Column(String(255), nullable=True)
    titular_dpi = Column(String(20), nullable=True)
    titular_nombre = Column(String(255), nullable=True)
    departamento = Column(String(150), nullable=True)
    municipio = Column(String(150), nullable=True)
    direccion = Column(Text, nullable=True)
    telefono = Column(String(50), nullable=True)

    # Respuesta funcional
    numero_cuenta = Column(String(50), nullable=True)
    motivo_rechazo = Column(Text, nullable=True)

    # ✅ NUEVO: integración servicio externo
    proveedor_servicio = Column(String(80), nullable=True)
    referencia_externa = Column(String(120), nullable=True)

    request_payload = Column(JSONB, nullable=True)
    response_payload = Column(JSONB, nullable=True)
    response_status_code = Column(Integer, nullable=True)
    error_servicio = Column(Text, nullable=True)
    procesado_en = Column(DateTime, nullable=True)

    creado_en = Column(DateTime, nullable=False, server_default=func.now())
    actualizado_en = Column(DateTime, nullable=True, onupdate=func.now())

    lote = relationship("LoteAperturaCuenta", back_populates="items")


class CuentaBancariaExpediente(Base):
    __tablename__ = "cuenta_bancaria_expediente"

    id = Column(BigInteger, primary_key=True)

    expediente_id = Column(
        BigInteger,
        ForeignKey("expediente_electronico.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,  # 1 cuenta por expediente (upsert por expediente_id)
    )

    banco_codigo = Column(String(50), nullable=False, default="BANRURAL")
    numero_cuenta = Column(String(50), nullable=False)

    titular_dpi = Column(String(20), nullable=True)
    titular_nombre = Column(String(255), nullable=True)

    cuenta_asignada_en = Column(DateTime, nullable=False, server_default=func.now())

    detalle_apertura_id = Column(
        BigInteger,
        ForeignKey("detalle_apertura_cuenta.id", ondelete="SET NULL"),
        nullable=True,
    )