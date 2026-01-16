import uuid
from datetime import date

from sqlalchemy import String, Integer, Text, Date, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class InfoGeneral(Base):
    __tablename__ = "info_general"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # 1:1 con expediente
    expediente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("expediente_electronico.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )

    # Periodo
    numero: Mapped[str | None] = mapped_column(String(50))
    anio: Mapped[str | None] = mapped_column(String(10))
    mes: Mapped[str | None] = mapped_column(String(10))

    # Salud (normalizado)
    area_salud_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("cat_area_salud.id")
    )
    distrito_salud_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("cat_distrito_salud.id")
    )
    servicio_salud_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("cat_servicio_salud.id")
    )

    # Residencia
    departamento_residencia_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("cat_departamento.id")
    )
    municipio_residencia_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("cat_municipio.id")
    )
    comunidad_residencia: Mapped[str | None] = mapped_column(String(255))
    direccion_residencia: Mapped[str | None] = mapped_column(String(500))

    # Niño
    cui_del_nino: Mapped[str | None] = mapped_column(String(50))
    sexo_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("cat_sexo.id")
    )
    edad_en_anios: Mapped[str | None] = mapped_column(String(20))
    nombre_del_nino: Mapped[str | None] = mapped_column(String(255))

    fecha_nacimiento: Mapped[date | None] = mapped_column(Date)
    fecha_del_primer_contacto: Mapped[date | None] = mapped_column(Date)
    fecha_de_registro: Mapped[date | None] = mapped_column(Date)

    # Diagnóstico
    cie_10: Mapped[str | None] = mapped_column(String(30))
    diagnostico: Mapped[str | None] = mapped_column(Text)

    # Madre / Padre
    nombre_de_la_madre: Mapped[str | None] = mapped_column(String(255))
    cui_de_la_madre: Mapped[str | None] = mapped_column(String(50))
    nombre_del_padre: Mapped[str | None] = mapped_column(String(255))
    cui_del_padre: Mapped[str | None] = mapped_column(String(50))

    telefonos_encargados: Mapped[str | None] = mapped_column(String(255))

    # Validación
    validacion_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("cat_validacion.id")
    )

    # Relación inversa
    expediente = relationship(
        "ExpedienteElectronico",
        back_populates="info_general",
        lazy="joined",
    )
