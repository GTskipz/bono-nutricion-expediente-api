from pydantic import BaseModel

class DepartamentoOut(BaseModel):
    id: int
    nombre: str
    codigo: str | None = None

    class Config:
        from_attributes = True
