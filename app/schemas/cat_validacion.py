from pydantic import BaseModel, ConfigDict

class ValidacionOut(BaseModel):
    id: int
    codigo: str
    nombre: str
    descripcion: str | None
    activo: bool

    model_config = ConfigDict(from_attributes=True)
