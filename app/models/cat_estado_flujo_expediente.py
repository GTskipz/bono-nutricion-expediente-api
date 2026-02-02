from sqlalchemy import Column, BigInteger, String, Text, Integer, Boolean
from app.core.db import Base


class CatEstadoFlujoExpediente(Base):
    __tablename__ = "cat_estado_flujo_expediente"

    id = Column(BigInteger, primary_key=True)

    codigo = Column(String(40), nullable=False, unique=True)
    nombre = Column(String(100), nullable=False)
    descripcion = Column(Text)
    orden = Column(Integer, nullable=False)
    activo = Column(Boolean, nullable=False, default=True)
