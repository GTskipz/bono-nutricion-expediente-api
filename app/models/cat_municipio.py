from sqlalchemy import Integer, String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base

class CatMunicipio(Base):
    __tablename__ = "cat_municipio"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    departamento_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("cat_departamento.id"), nullable=False
    )
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    codigo: Mapped[str | None] = mapped_column(String(20))
