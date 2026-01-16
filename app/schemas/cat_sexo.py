from pydantic import BaseModel


class SexoOut(BaseModel):
    id: int
    codigo: str
    nombre: str
    activo: bool

    class Config:
        from_attributes = True
