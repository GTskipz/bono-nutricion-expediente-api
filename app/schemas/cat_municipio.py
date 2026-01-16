from pydantic import BaseModel

class MunicipioOut(BaseModel):
    id: int
    departamento_id: int
    nombre: str
    codigo: str | None = None

    class Config:
        from_attributes = True
