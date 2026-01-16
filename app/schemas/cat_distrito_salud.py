from pydantic import BaseModel


class DistritoSaludOut(BaseModel):
    id: int
    area_salud_id: int
    nombre: str

    class Config:
        from_attributes = True
