from pydantic import BaseModel, Field
from typing import Optional


class ExpedienteContactoIn(BaseModel):
    nombre_contacto: str = Field(..., min_length=1, max_length=255)

    departamento_id: int
    municipio_id: int

    poblado: Optional[str] = Field(None, max_length=200)
    direccion: Optional[str] = Field(None, max_length=500)
    anotaciones_direccion: Optional[str] = None

    telefono_1: Optional[str] = Field(None, max_length=30)
    telefono_2: Optional[str] = Field(None, max_length=30)


class ExpedienteContactoOut(BaseModel):
    expediente_id: int

    nombre_contacto: str
    departamento_id: int
    municipio_id: int

    poblado: Optional[str] = None
    direccion: Optional[str] = None
    anotaciones_direccion: Optional[str] = None
    telefono_1: Optional[str] = None
    telefono_2: Optional[str] = None

    departamento_nombre: Optional[str] = None
    municipio_nombre: Optional[str] = None
