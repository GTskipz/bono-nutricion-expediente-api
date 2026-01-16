from pydantic import BaseModel

class AreaSaludOut(BaseModel):
    id: int
    nombre: str

    class Config:
        from_attributes = True
