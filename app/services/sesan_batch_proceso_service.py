from sqlalchemy.orm import Session
from sqlalchemy import text


class SesanBatchProcesoService:

    def __init__(self, db: Session):
        self.db = db

    # =========================
    # Crear proceso
    # =========================
    def crear_proceso(self, batch_id: int, usuario_id: str | None):
        query = text("""
            INSERT INTO sesan_batch_proceso (
                batch_id,
                estado,
                iniciado_por,
                iniciado_en,
                ultima_actualizacion,
                created_at,
                updated_at
            )
            VALUES (
                :batch_id,
                'INICIADO',
                :usuario,
                NOW(),
                NOW(),
                NOW(),
                NOW()
            )
            RETURNING id
        """)

        result = self.db.execute(query, {
            "batch_id": batch_id,
            "usuario": usuario_id
        }).first()

        self.db.commit()

        return int(result[0])

    # =========================
    # Marcar procesando
    # =========================
    def marcar_procesando(self, proceso_id: int):
        self.db.execute(text("""
            UPDATE sesan_batch_proceso
            SET estado = 'PROCESANDO',
                ultima_actualizacion = NOW(),
                updated_at = NOW()
            WHERE id = :id
        """), {"id": proceso_id})

        self.db.commit()

    # =========================
    # Heartbeat
    # =========================
    def heartbeat(self, proceso_id: int):
        self.db.execute(text("""
            UPDATE sesan_batch_proceso
            SET ultima_actualizacion = NOW(),
                updated_at = NOW()
            WHERE id = :id
        """), {"id": proceso_id})

        self.db.commit()

    # =========================
    # Finalizar OK
    # =========================
    def finalizar_ok(self, proceso_id: int):
        self.db.execute(text("""
            UPDATE sesan_batch_proceso
            SET estado = 'FINALIZADO',
                finalizado_en = NOW(),
                ultima_actualizacion = NOW(),
                updated_at = NOW()
            WHERE id = :id
        """), {"id": proceso_id})

        self.db.commit()

    # =========================
    # Finalizar ERROR
    # =========================
    def finalizar_error(self, proceso_id: int, mensaje: str):
        self.db.execute(text("""
            UPDATE sesan_batch_proceso
            SET estado = 'ERROR',
                mensaje_error = :mensaje,
                finalizado_en = NOW(),
                ultima_actualizacion = NOW(),
                updated_at = NOW()
            WHERE id = :id
        """), {
            "id": proceso_id,
            "mensaje": mensaje
        })

        self.db.commit()


    def obtener_proceso_batch(self, batch_id: int):

        # último proceso
        proceso = self.db.execute(
            text("""
                SELECT
                    id,
                    estado,
                    iniciado_por,
                    iniciado_en,
                    ultima_actualizacion,
                    finalizado_en,
                    mensaje_error
                FROM sesan_batch_proceso
                WHERE batch_id = :batch_id
                ORDER BY id DESC
                LIMIT 1
            """),
            {"batch_id": batch_id},
        ).mappings().first()

        # pendientes actuales
        pendientes = self.db.execute(
            text("""
                SELECT COUNT(*) AS total
                FROM sesan_staging
                WHERE batch_id = :batch_id
                AND estado = 'PENDIENTE'
            """),
            {"batch_id": batch_id},
        ).mappings().first()

        total_pendientes = int(pendientes["total"] or 0)

        return {
            "proceso": dict(proceso) if proceso else None,
            "total_pendientes": total_pendientes
        }