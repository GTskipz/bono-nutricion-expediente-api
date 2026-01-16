from sqlalchemy import Column, Integer, String, ForeignKey, UniqueConstraint
from app.core.db import Base


class CatDistritoSalud(Base):
    __tablename__ = "cat_distrito_salud"

    id = Column(Integer, primary_key=True, index=True)
    area_salud_id = Column(Integer, ForeignKey("cat_area_salud.id"), nullable=False)
    nombre = Column(String, nullable=False)

    __table_args__ = (
        UniqueConstraint("area_salud_id", "nombre", name="uq_cat_distrito_area_nombre"),
    )
