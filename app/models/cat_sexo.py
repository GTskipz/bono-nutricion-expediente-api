from sqlalchemy import Column, Integer, String, Boolean
from app.core.db import Base

class CatSexo(Base):
    __tablename__ = "cat_sexo"

    id = Column(Integer, primary_key=True, index=True)
    codigo = Column(String, unique=True, nullable=False)
    nombre = Column(String, nullable=False)
    activo = Column(Boolean, nullable=False, default=True)
