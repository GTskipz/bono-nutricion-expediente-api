from sqlalchemy import Column, Integer, String
from app.core.db import Base

class CatAreaSalud(Base):
    __tablename__ = "cat_area_salud"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, unique=True, nullable=False)
