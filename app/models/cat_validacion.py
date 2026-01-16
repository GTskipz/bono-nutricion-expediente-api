from sqlalchemy import Column, Integer, String, Boolean
from app.core.db import Base

class CatValidacion(Base):
    __tablename__ = "cat_validacion"

    id = Column(Integer, primary_key=True, index=True)
    codigo = Column(String(50), unique=True, nullable=False)
    nombre = Column(String(255), nullable=False)
    descripcion = Column(String(500), nullable=True)
    activo = Column(Boolean, nullable=False, default=True)
