from pydantic import BaseModel

class TipoDocumentoOut(BaseModel):
    id: int
    codigo: str
    nombre: str
    es_obligatorio: bool
    orden: int
    activo: bool

    class Config:
        from_attributes = True
