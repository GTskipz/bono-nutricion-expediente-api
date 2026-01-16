from sqlalchemy import Column, Integer, String, ForeignKey, UniqueConstraint
from app.core.db import Base


class CatServicioSalud(Base):
    __tablename__ = "cat_servicio_salud"

    id = Column(Integer, primary_key=True, index=True)
    distrito_salud_id = Column(Integer, ForeignKey("cat_distrito_salud.id"), nullable=False)
    nombre = Column(String, nullable=False)

    __table_args__ = (
        UniqueConstraint("distrito_salud_id", "nombre", name="uq_cat_servicio_distrito_nombre"),
    )
