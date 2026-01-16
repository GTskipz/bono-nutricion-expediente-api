from pydantic import BaseModel


class ServicioSaludOut(BaseModel):
    id: int
    distrito_salud_id: int
    nombre: str

    class Config:
        from_attributes = True
