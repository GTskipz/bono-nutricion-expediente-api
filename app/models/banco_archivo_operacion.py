from sqlalchemy import Column, BigInteger, String, DateTime, Text
from datetime import datetime

from app.core.db import Base


class BancoArchivoOperacion(Base):

    __tablename__ = "banco_archivo_operacion"

    id = Column(BigInteger, primary_key=True, index=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    tipo_operacion = Column(String(40), nullable=False)
    # APERTURA_CUENTA
    # PAGO_BENEFICIARIO

    operacion_id = Column(BigInteger, nullable=False)

    tipo_archivo = Column(String(40), nullable=False)
    # SOLICITUD
    # RESPUESTA
    # REPORTE

    estado = Column(String(20), default="GENERADO", nullable=False)

    banco_codigo = Column(String(20))

    filename = Column(String(255))
    mime_type = Column(String(120))
    size_bytes = Column(BigInteger)

    storage_provider = Column(String(80))
    storage_key = Column(String(500))

    checksum_sha256 = Column(String(80))

    subido_por = Column(String(255))

    observacion = Column(Text)
    descripcion = Column(String(255))