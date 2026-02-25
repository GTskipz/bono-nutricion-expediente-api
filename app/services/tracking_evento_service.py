from __future__ import annotations

from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session

from app.models.tracking_evento import TrackingEvento


class TrackingEventoService:
    """
    Servicio centralizado de historial por EXPEDIENTE.
    Registra únicamente eventos importantes.
    Usa la tabla tracking_evento existente.
    """

    # =========================
    # ORÍGENES
    # =========================
    ORIGEN_EXPEDIENTE = "EXPEDIENTE"
    ORIGEN_DOCUMENTOS = "DOCUMENTOS"
    ORIGEN_CUENTAS = "CUENTAS"
    ORIGEN_PAGOS = "PAGOS"
    ORIGEN_BPM = "BPM"

    # =========================
    # TIPOS DE EVENTO IMPORTANTES
    # =========================
    # Documentos
    DOCS_SUBIDOS = "DOCS_SUBIDOS"
    DOCS_VERIFICADOS = "DOCS_VERIFICADOS"
    DOCS_RECHAZADOS = "DOCS_RECHAZADOS"

    # Cuentas
    CUENTA_INTENTO = "CUENTA_INTENTO"
    CUENTA_CREADA = "CUENTA_CREADA"
    CUENTA_RECHAZADA = "CUENTA_RECHAZADA"
    CUENTA_ERROR = "CUENTA_ERROR_TECNICO"

    # Pagos
    PAGO_INTENTO = "PAGO_INTENTO"
    PAGO_APROBADO = "PAGO_APROBADO"
    PAGO_RECHAZADO = "PAGO_RECHAZADO"
    PAGO_EXCEDE_TOPE = "PAGO_EXCEDE_TOPE"
    PAGO_ERROR = "PAGO_ERROR_TECNICO"

    # =========================
    # MÉTODO BASE INTERNO
    # =========================
    @staticmethod
    def _registrar(
        db: Session,
        *,
        expediente_id: int,
        titulo: str,
        origen: str,
        tipo_evento: str,
        usuario: Optional[str] = None,
        observacion: Optional[str] = None,
        commit: bool = True,
    ) -> TrackingEvento:

        evento = TrackingEvento(
            expediente_id=expediente_id,
            fecha_evento=datetime.utcnow(),
            titulo=titulo,
            usuario=usuario,
            observacion=observacion,
            origen=origen,
            tipo_evento=tipo_evento,
        )

        db.add(evento)

        if commit:
            db.commit()
            db.refresh(evento)

        return evento

    # =========================================================
    # DOCUMENTOS
    # =========================================================
    @classmethod
    def documentos_subidos(cls, db: Session, expediente_id: int, usuario: str | None = None):
        return cls._registrar(
            db,
            expediente_id=expediente_id,
            titulo="Documentos subidos",
            origen=cls.ORIGEN_DOCUMENTOS,
            tipo_evento=cls.DOCS_SUBIDOS,
            usuario=usuario,
        )

    @classmethod
    def documentos_verificados(cls, db: Session, expediente_id: int, usuario: str | None = None):
        return cls._registrar(
            db,
            expediente_id=expediente_id,
            titulo="Documentos verificados",
            origen=cls.ORIGEN_DOCUMENTOS,
            tipo_evento=cls.DOCS_VERIFICADOS,
            usuario=usuario,
        )

    @classmethod
    def documentos_rechazados(cls, db: Session, expediente_id: int, motivo: str | None = None, usuario: str | None = None):
        return cls._registrar(
            db,
            expediente_id=expediente_id,
            titulo="Documentos rechazados",
            origen=cls.ORIGEN_DOCUMENTOS,
            tipo_evento=cls.DOCS_RECHAZADOS,
            usuario=usuario,
            observacion=motivo,
        )

    # =========================================================
    # CUENTAS BANCARIAS
    # =========================================================
    @classmethod
    def cuenta_intento(cls, db: Session, expediente_id: int, lote_id: int | None = None, usuario: str | None = None):
        obs = f"Lote apertura #{lote_id}" if lote_id else None

        return cls._registrar(
            db,
            expediente_id=expediente_id,
            titulo="Intento de creación de cuenta bancaria",
            origen=cls.ORIGEN_CUENTAS,
            tipo_evento=cls.CUENTA_INTENTO,
            usuario=usuario,
            observacion=obs,
        )

    @classmethod
    def cuenta_creada(cls, db: Session, expediente_id: int, numero_cuenta: str | None = None, usuario: str | None = None):
        obs = f"Cuenta: {numero_cuenta}" if numero_cuenta else None

        return cls._registrar(
            db,
            expediente_id=expediente_id,
            titulo="Cuenta bancaria creada",
            origen=cls.ORIGEN_CUENTAS,
            tipo_evento=cls.CUENTA_CREADA,
            usuario=usuario,
            observacion=obs,
        )

    @classmethod
    def cuenta_rechazada(cls, db: Session, expediente_id: int, motivo: str | None = None, usuario: str | None = None):
        return cls._registrar(
            db,
            expediente_id=expediente_id,
            titulo="Cuenta bancaria rechazada",
            origen=cls.ORIGEN_CUENTAS,
            tipo_evento=cls.CUENTA_RECHAZADA,
            usuario=usuario,
            observacion=motivo,
        )

    @classmethod
    def cuenta_error(cls, db: Session, expediente_id: int, detalle: str | None = None, usuario: str | None = None):
        return cls._registrar(
            db,
            expediente_id=expediente_id,
            titulo="Error técnico en creación de cuenta",
            origen=cls.ORIGEN_CUENTAS,
            tipo_evento=cls.CUENTA_ERROR,
            usuario=usuario,
            observacion=detalle,
        )

    # =========================================================
    # PAGOS
    # =========================================================
    @classmethod
    def pago_intento(
        cls,
        db: Session,
        expediente_id: int,
        lote_id: int | None = None,
        anio: int | None = None,
        mes: int | None = None,
        monto: float | None = None,
        usuario: str | None = None,
    ):
        partes = []
        if lote_id:
            partes.append(f"Lote #{lote_id}")
        if anio and mes:
            partes.append(f"Periodo {anio}-{mes:02d}")
        if monto:
            partes.append(f"Monto Q{monto:,.2f}")

        return cls._registrar(
            db,
            expediente_id=expediente_id,
            titulo="Intento de pago",
            origen=cls.ORIGEN_PAGOS,
            tipo_evento=cls.PAGO_INTENTO,
            usuario=usuario,
            observacion=" | ".join(partes) if partes else None,
        )

    @classmethod
    def pago_aprobado(cls, db: Session, expediente_id: int, monto: float | None = None, usuario: str | None = None):
        obs = f"Monto Q{monto:,.2f}" if monto else None

        return cls._registrar(
            db,
            expediente_id=expediente_id,
            titulo="Pago aprobado",
            origen=cls.ORIGEN_PAGOS,
            tipo_evento=cls.PAGO_APROBADO,
            usuario=usuario,
            observacion=obs,
        )

    @classmethod
    def pago_rechazado(cls, db: Session, expediente_id: int, motivo: str | None = None, usuario: str | None = None):
        return cls._registrar(
            db,
            expediente_id=expediente_id,
            titulo="Pago rechazado",
            origen=cls.ORIGEN_PAGOS,
            tipo_evento=cls.PAGO_RECHAZADO,
            usuario=usuario,
            observacion=motivo,
        )

    @classmethod
    def pago_excede_tope(cls, db: Session, expediente_id: int, usuario: str | None = None):
        return cls._registrar(
            db,
            expediente_id=expediente_id,
            titulo="Pago rechazado por exceder tope anual",
            origen=cls.ORIGEN_PAGOS,
            tipo_evento=cls.PAGO_EXCEDE_TOPE,
            usuario=usuario,
        )

    @classmethod
    def pago_error(cls, db: Session, expediente_id: int, detalle: str | None = None, usuario: str | None = None):
        return cls._registrar(
            db,
            expediente_id=expediente_id,
            titulo="Error técnico en proceso de pago",
            origen=cls.ORIGEN_PAGOS,
            tipo_evento=cls.PAGO_ERROR,
            usuario=usuario,
            observacion=detalle,
        )