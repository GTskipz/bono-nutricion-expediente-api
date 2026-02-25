from sqlalchemy import Column, BigInteger, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func

from app.core.db import Base


class ExpedienteContacto(Base):
    __tablename__ = "expediente_contacto"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    # 1 a 1 con expediente
    expediente_id = Column(
        BigInteger,
        ForeignKey("expediente_electronico.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # Persona de contacto
    nombre_contacto = Column(String(255), nullable=False)

    # Catálogos
    departamento_id = Column(BigInteger, ForeignKey("cat_departamento.id"), nullable=False, index=True)
    municipio_id = Column(BigInteger, ForeignKey("cat_municipio.id"), nullable=False, index=True)

    # Dirección detallada
    poblado = Column(String(200), nullable=True)
    direccion = Column(String(500), nullable=True)
    anotaciones_direccion = Column(Text, nullable=True)

    # Teléfonos
    telefono_1 = Column(String(30), nullable=True)
    telefono_2 = Column(String(30), nullable=True)
