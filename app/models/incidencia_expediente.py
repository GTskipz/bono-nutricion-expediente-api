from datetime import datetime

from sqlalchemy import (
    String,
    Integer,
    DateTime,
    Text,
    BigInteger,
    Boolean,
    ForeignKey,
    CheckConstraint,
)

from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


# ======================================================
# CATÁLOGO DE TIPOS DE INCIDENCIA
# ======================================================

class CatIncidenciaExpediente(Base):

    __tablename__ = "cat_incidencia_expediente"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    codigo: Mapped[str] = mapped_column(
        String(80), unique=True, nullable=False
    )

    nombre: Mapped[str] = mapped_column(
        String(180), nullable=False
    )

    descripcion: Mapped[str | None] = mapped_column(Text)

    afecta_estado: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )


# ======================================================
# INCIDENCIA DEL EXPEDIENTE
# ======================================================

class IncidenciaExpediente(Base):

    __tablename__ = "incidencia_expediente"

    __table_args__ = (
        CheckConstraint(
            "estado IN ('ACTIVA','PROCESADA','CERRADA')",
            name="chk_incidencia_estado",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )

    expediente_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("expediente_electronico.id", ondelete="CASCADE"),
        nullable=False,
    )

    tipo_incidencia_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("cat_incidencia_expediente.id"),
        nullable=False,
    )

    descripcion: Mapped[str | None] = mapped_column(Text)

    estado: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="ACTIVA",
    )

    usuario_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )


# ======================================================
# HISTORIAL DE INCIDENCIAS
# ======================================================

class HistorialIncidenciaExpediente(Base):

    __tablename__ = "historial_incidencia_expediente"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )

    incidencia_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("incidencia_expediente.id", ondelete="CASCADE"),
        nullable=False,
    )

    accion: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )

    descripcion: Mapped[str | None] = mapped_column(Text)

    usuario_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow
    )


# ======================================================
# ARCHIVOS DE INCIDENCIA
# ======================================================

class IncidenciaExpedienteArchivo(Base):

    __tablename__ = "incidencia_expediente_archivo"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )

    incidencia_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("incidencia_expediente.id", ondelete="CASCADE"),
        nullable=False,
    )

    filename: Mapped[str | None] = mapped_column(
        String(255)
    )

    mime_type: Mapped[str | None] = mapped_column(
        String(120)
    )

    size_bytes: Mapped[int | None] = mapped_column(
        BigInteger
    )

    storage_provider: Mapped[str | None] = mapped_column(
        String(80)
    )

    storage_key: Mapped[str | None] = mapped_column(
        String(500)
    )

    checksum_sha256: Mapped[str | None] = mapped_column(
        String(80)
    )

    activo: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True
    )

    usuario_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow
    )