# app/services/sesan_service.py
from __future__ import annotations

import os   # Agregado para variables de entorno
import io   # Agregado para manejo de streams de bytes
from fastapi import HTTPException, UploadFile
from openpyxl import Workbook
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import date, datetime
import json

from app.core.db import SessionLocal
from app.services.excel_reader import read_sesan_xlsx_rows
from app.services.sesan_batch_processor import SesanBatchProcessor
from app.services.sesan_expediente_service import SesanExpedienteCreator
from app.services.utils import (
    norm_str, to_int, to_date, sha256_bytes, to_cui, to_rub, norm_lookup
)

# ✅ Reusar creación oficial de expediente
from app.routers.expedientes import crear_expediente_core, set_expediente_bpm_minimo_core
from app.schemas.expediente import ExpedienteCreate, InfoGeneralIn

from app.bpm.bpm_client import BpmClient
from app.bpm.bpm_payload_builder import build_spiff_payload_from_staging_row

from app.models.sesan_batch import SesanBatch
from app.models.sesan_batch_documento import SesanBatchDocumento
from app.models.cat_tipo_doc_batch import CatTipoDocBatch

# IMPORTAMOS EL CLIENTE MINIO (Agregado)
try:
    from app.dependencies import minio_client
except ImportError:
    minio_client = None
    print("Advertencia: app.dependencies.minio_client no encontrado.")


class SesanService:
    def __init__(self, db: Session):
        self.db = db
        self.bpm = BpmClient()

    # =====================================================
    # Lookups catálogo / reglas
    # =====================================================

    def _cat_id_by_name(self, table: str, name_col: str, value: str | None) -> int | None:
        v = norm_lookup(value)
        if not v:
            return None

        row = self.db.execute(
            text(f"SELECT id FROM {table} WHERE UPPER({name_col}) = :v LIMIT 1"),
            {"v": v},
        ).scalar()

        return int(row) if row is not None else None

    def _sexo_id(self, value: str | None) -> int | None:
        s = norm_lookup(value)
        if not s:
            return None
        if s in ("M", "MASCULINO", "HOMBRE", "1"):
            code = "M"
        elif s in ("F", "FEMENINO", "MUJER", "2"):
            code = "F"
        else:
            return None

        sid = self._cat_id_by_name("cat_sexo", "codigo", code)
        if sid is None:
            sid = self._cat_id_by_name("cat_sexo", "nombre", code)
        return sid

    def _validacion_id(self, raw: str | None) -> int | None:
        s = norm_lookup(raw)
        if not s:
            return None
        if s in ("VALIDO", "VÁLIDO"):
            vid = self._cat_id_by_name("cat_validacion", "codigo", "VALIDO")
            if vid is None:
                vid = self._cat_id_by_name("cat_validacion", "nombre", "VALIDO")
            return vid
        if s in ("INVALIDO", "INVÁLIDO"):
            vid = self._cat_id_by_name("cat_validacion", "codigo", "INVALIDO")
            if vid is None:
                vid = self._cat_id_by_name("cat_validacion", "nombre", "INVALIDO")
            return vid
        return None

    # =====================================================
    # DB helpers (igual que tu router original)
    # =====================================================

    def _recalc_batch_counts(self, batch_id: int):
        counts = self.db.execute(
            text("""
                SELECT
                  COUNT(*) AS total,
                  SUM(CASE WHEN estado = 'PENDIENTE' THEN 1 ELSE 0 END) AS pendientes,
                  SUM(CASE WHEN estado = 'PROCESADO' THEN 1 ELSE 0 END) AS procesados,
                  SUM(CASE WHEN estado = 'ERROR' THEN 1 ELSE 0 END) AS errores,
                  SUM(CASE WHEN estado = 'IGNORADO' THEN 1 ELSE 0 END) AS ignorados
                FROM sesan_staging
                WHERE batch_id = :batch_id
            """),
            {"batch_id": batch_id},
        ).mappings().one()

        total = int(counts["total"] or 0)
        pendientes = int(counts["pendientes"] or 0)
        procesados = int(counts["procesados"] or 0)
        errores = int(counts["errores"] or 0)
        ignorados = int(counts["ignorados"] or 0)

        if total <= 0:
            estado = "CARGADO"
        elif pendientes == 0:
            estado = "FINALIZADO"
        else:
            estado = "EN_REVISION"

        self.db.execute(
            text("""
                UPDATE sesan_batch
                SET
                  total_registros = :total,
                  total_pendientes = :pendientes,
                  total_procesados = :procesados,
                  total_error = :errores,
                  total_ignorados = :ignorados,
                  estado = :estado,
                  updated_at = NOW()
                WHERE id = :batch_id
            """),
            {
                "batch_id": batch_id,
                "total": total,
                "pendientes": pendientes,
                "procesados": procesados,
                "errores": errores,
                "ignorados": ignorados,
                "estado": estado,
            },
        )

    def _is_dup_cui_in_year(self, cui_nino: str, anio_carga: int, current_row_id: int) -> bool:
        exists = self.db.execute(
            text("""
                SELECT 1
                FROM sesan_staging s
                JOIN sesan_batch b ON b.id = s.batch_id
                WHERE b.anio_carga = :anio
                  AND s.estado = 'PROCESADO'
                  AND s.cui_nino = :cui
                  AND s.id <> :row_id
                LIMIT 1
            """),
            {"anio": anio_carga, "cui": cui_nino, "row_id": current_row_id},
        ).scalar()
        return bool(exists)

    def _is_dup_cui_in_expedientes(self, cui_nino: str, anio_carga: int) -> bool:
        exists = self.db.execute(
            text("""
                SELECT 1
                FROM info_general ig
                WHERE ig.cui_del_nino = :cui
                  AND ig.anio = :anio
                LIMIT 1
            """),
            {"cui": cui_nino, "anio": str(anio_carga)},
        ).scalar()
        return bool(exists)

    def _is_dup_rub_in_year(self, rub: str, anio_carga: int, current_row_id: int) -> bool:
        exists = self.db.execute(
            text("""
                SELECT 1
                FROM sesan_staging s
                JOIN sesan_batch b ON b.id = s.batch_id
                WHERE b.anio_carga = :anio
                  AND s.estado = 'PROCESADO'
                  AND s.rub = :rub
                  AND s.id <> :row_id
                LIMIT 1
            """),
            {"anio": anio_carga, "rub": rub, "row_id": current_row_id},
        ).scalar()
        return bool(exists)

    def _is_dup_rub_in_expedientes(self, rub: str, anio_carga: int) -> bool:
        exists = self.db.execute(
            text("""
                SELECT 1
                FROM expediente_electronico e
                WHERE e.rub = :rub
                  AND e.anio_carga = :anio
                LIMIT 1
            """),
            {"rub": rub, "anio": anio_carga},
        ).scalar()
        return bool(exists)

    def _build_expediente_payload_from_row(self, row: dict, anio_carga: int, mes_carga: int | None):
        #rub = to_rub(row.get("rub"))
        rub = ""
        cui_nino = to_cui(row.get("cui_nino"))
        nombre_nino = norm_str(row.get("nombre_nino"))

        depto_res_id = self._cat_id_by_name("cat_departamento", "nombre", row.get("departamento_residencia"))
        muni_res_id = self._cat_id_by_name("cat_municipio", "nombre", row.get("municipio_residencia"))

        area_id = self._cat_id_by_name("cat_area_salud", "nombre", row.get("area_salud"))
        distrito_id = self._cat_id_by_name("cat_distrito_salud", "nombre", row.get("distrito_salud"))
        servicio_id = self._cat_id_by_name("cat_servicio_salud", "nombre", row.get("servicio_salud"))

        sexo_id = self._sexo_id(row.get("sexo"))
        validacion_id = self._validacion_id(row.get("validacion_raw"))

        ig_anio = str(anio_carga)
        ig_mes = str(to_int(row.get("mes")) or mes_carga or "") or None

        ig = InfoGeneralIn(
            anio=ig_anio,
            mes=ig_mes,
            area_salud_id=area_id,
            distrito_salud_id=distrito_id,
            servicio_salud_id=servicio_id,
            departamento_residencia_id=depto_res_id,
            municipio_residencia_id=muni_res_id,
            comunidad_residencia=norm_str(row.get("comunidad_residencia")),
            direccion_residencia=norm_str(row.get("direccion_residencia")),
            cui_del_nino=cui_nino,
            sexo_id=sexo_id,
            edad_en_anios=norm_str(row.get("edad_en_anios")),
            nombre_del_nino=nombre_nino,
            fecha_nacimiento=row.get("fecha_nacimiento"),
            fecha_del_primer_contacto=row.get("fecha_primer_contacto"),
            fecha_de_registro=row.get("fecha_registro"),
            cie_10=norm_str(row.get("cie_10")),
            diagnostico=norm_str(row.get("diagnostico")),
            nombre_de_la_madre=norm_str(row.get("nombre_madre")),
            cui_de_la_madre=to_cui(row.get("cui_madre")),
            nombre_del_padre=norm_str(row.get("nombre_padre")),
            cui_del_padre=to_cui(row.get("cui_padre")),
            telefonos_encargados=norm_str(row.get("telefonos_encargados")),
            validacion_id=validacion_id,
        )

        payload = ExpedienteCreate(
            nombre_beneficiario=nombre_nino,
            cui_beneficiario=cui_nino,
            rub=rub,
            departamento_id=depto_res_id,
            municipio_id=muni_res_id,
            anio_carga=anio_carga,
            info_general=ig,
        )

        return payload

    # =====================================================
    # 1) Crear batch + staging (SUBIDA)
    # =====================================================
    def crear_batch(
        self,
        *,
        nombre_lote: str,
        anio_carga: int,
        mes_carga: int | None,
        descripcion: str | None,
        origen: str,
        usuario_carga: str | None,
        file: UploadFile,
    ):
        import os
        import io
        import json
        import tempfile
        from datetime import datetime
        from sqlalchemy import text
        from fastapi import HTTPException

        from app.services.sesan_batch_documentos_service import crear_placeholders_docs_requeridos
        from app.services.excel_reader import iter_sesan_xlsx_rows, validar_excel_sesan 

        try:
            # =====================================================
            # 1) Guardar UploadFile a TEMP sin cargar a RAM
            # =====================================================
            ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
            safe_name = (file.filename or "sesan.xlsx").replace("\\", "_").replace("/", "_")

            fd, tmp_path = tempfile.mkstemp(suffix=f"_{safe_name}")
            os.close(fd)

            size_bytes = 0
            file.file.seek(0)
            with open(tmp_path, "wb") as out:
                while True:
                    chunk = file.file.read(1024 * 1024)  # 1MB
                    if not chunk:
                        break
                    out.write(chunk)
                    size_bytes += len(chunk)

            if size_bytes == 0:
                raise HTTPException(status_code=400, detail="Archivo vacío.")

            # =====================================================
            # 2) SHA256 desde disco (streaming)
            # =====================================================
            import hashlib
            h = hashlib.sha256()
            with open(tmp_path, "rb") as f:
                while True:
                    chunk = f.read(1024 * 1024)
                    if not chunk:
                        break
                    h.update(chunk)
            checksum = h.hexdigest()

            # =====================================================
            # 3) Subir a MinIO desde archivo (no BytesIO)
            # =====================================================
            bucket_name = os.getenv("MINIO_BUCKET", "almacenamiento-mis")
            object_name = f"sesan/{anio_carga}/{ts}_{safe_name}"

            if minio_client:
                # fput_object es ideal para archivos grandes
                minio_client.fput_object(
                    bucket_name,
                    object_name,
                    tmp_path,
                    content_type=file.content_type
                )
                storage_provider = "MINIO"
                storage_key = object_name
            else:
                print("Cliente MinIO no disponible, usando FTP simulado")
                storage_provider = "ftp"
                storage_key = f"ftp://PENDIENTE/sesan/{ts}_{safe_name}"

            # =====================================================
            # 🔍 VALIDACIÓN DEL EXCEL (ANTES DE TODO)
            # =====================================================
            header_row = validar_excel_sesan(tmp_path)

            # =====================================================
            # 4) Insert sesan_batch (igual que antes)
            # =====================================================
            batch_id = self.db.execute(
                text("""
                    INSERT INTO sesan_batch (
                    nombre_lote, descripcion, origen,
                    anio_carga, mes_carga, usuario_carga,
                    archivo_nombre_original, archivo_mime_type, archivo_size_bytes,
                    storage_provider, storage_key, checksum_sha256,
                    estado,
                    total_registros, total_pendientes, total_procesados, total_error, total_ignorados,
                    created_at, updated_at
                    )
                    VALUES (
                    :nombre_lote, :descripcion, :origen,
                    :anio_carga, :mes_carga, :usuario_carga,
                    :archivo_nombre_original, :archivo_mime_type, :archivo_size_bytes,
                    :storage_provider, :storage_key, :checksum_sha256,
                    'CARGADO',
                    0, 0, 0, 0, 0,
                    NOW(), NOW()
                    )
                    RETURNING id
                """),
                {
                    "nombre_lote": nombre_lote,
                    "descripcion": descripcion,
                    "origen": origen,
                    "anio_carga": anio_carga,
                    "mes_carga": mes_carga,
                    "usuario_carga": usuario_carga,
                    "archivo_nombre_original": file.filename or "sesan.xlsx",
                    "archivo_mime_type": file.content_type,
                    "archivo_size_bytes": size_bytes,
                    "storage_provider": storage_provider,
                    "storage_key": storage_key,
                    "checksum_sha256": checksum,
                }
            ).scalar_one()

            batch_id = int(batch_id)

            # ✅ 4.1) Crear placeholders docs requeridos (sin archivos)
            placeholders_created = crear_placeholders_docs_requeridos(self.db, batch_id)

            # =====================================================
            # 5) Insert staging por CHUNKS (executemany)
            # =====================================================
            insert_staging = text("""
                INSERT INTO sesan_staging (
                batch_id, row_num,
                rub,
                anio, mes, area_salud, distrito_salud, servicio_salud,
                departamento_residencia, municipio_residencia, comunidad_residencia, direccion_residencia,
                cui_nino, sexo, edad_en_anios, nombre_nino,
                fecha_nacimiento, fecha_primer_contacto, fecha_registro,
                cie_10, diagnostico,
                nombre_madre, cui_madre, nombre_padre, cui_padre, telefonos_encargados,
                validacion_raw,
                raw_data,
                estado,
                created_at, updated_at
                )
                VALUES (
                :batch_id, :row_num,
                :rub,
                :anio, :mes, :area_salud, :distrito_salud, :servicio_salud,
                :departamento_residencia, :municipio_residencia, :comunidad_residencia, :direccion_residencia,
                :cui_nino, :sexo, :edad_en_anios, :nombre_nino,
                :fecha_nacimiento, :fecha_primer_contacto, :fecha_registro,
                :cie_10, :diagnostico,
                :nombre_madre, :cui_madre, :nombre_padre, :cui_padre, :telefonos_encargados,
                :validacion_raw,
                CAST(:raw_data AS jsonb),
                'PENDIENTE',
                NOW(), NOW()
                )
            """)

            CHUNK_SIZE = int(os.getenv("SESAN_STAGING_CHUNK", "1000"))
            buffer = []
            total = 0

            # iterador streaming (no lista)
            for item in iter_sesan_xlsx_rows(tmp_path):
                r = item["data"]
                raw_for_audit = item.get("raw") or {}

                buffer.append(
                    {
                        "batch_id": batch_id,
                        "row_num": item["excel_row"],

                        "rub": to_rub(r.get("RUB")),

                        "anio": to_int(r.get("ANO")),
                        "mes": to_int(r.get("MES")),
                        "area_salud": norm_str(r.get("AREA_DE_SALUD")),
                        "distrito_salud": norm_str(r.get("DISTRITO_DE_SALUD")),
                        "servicio_salud": norm_str(r.get("SERVICIO_DE_SALUD")),

                        "departamento_residencia": norm_str(r.get("DEPTO_RESIDENCIA")),
                        "municipio_residencia": norm_str(r.get("MUNI_RESIDENCIA")),
                        "comunidad_residencia": norm_str(r.get("COMUNIDAD_RESIDENCIA")),
                        "direccion_residencia": norm_str(r.get("DIRECCION_RESIDENCIA")),

                        "cui_nino": to_cui(r.get("CUI_NINO")),
                        "sexo": norm_str(r.get("SEXO")),
                        "edad_en_anios": norm_str(r.get("EDAD_EN_ANOS")),
                        "nombre_nino": norm_str(r.get("NOMBRE_NINO")),

                        "fecha_nacimiento": to_date(r.get("FECHA_NACIMIENTO")),
                        "fecha_primer_contacto": to_date(r.get("FECHA_PRIMER_CONTACTO")),
                        "fecha_registro": to_date(r.get("FECHA_REGISTRO")),

                        "cie_10": norm_str(r.get("CIE_10")),
                        "diagnostico": norm_str(r.get("DIAGNOSTICO")),

                        "nombre_madre": norm_str(r.get("NOMBRE_MADRE")),
                        "cui_madre": to_cui(r.get("CUI_MADRE")),
                        "nombre_padre": norm_str(r.get("NOMBRE_PADRE")),
                        "cui_padre": to_cui(r.get("CUI_PADRE")),
                        "telefonos_encargados": norm_str(r.get("TELEFONOS_ENCARGADOS")),

                        "validacion_raw": norm_str(r.get("VALIDACION")),

                        "raw_data": json.dumps(raw_for_audit, default=str),
                    }
                )
                total += 1

                if len(buffer) >= CHUNK_SIZE:
                    # ✅ 1 llamada por 1000 filas (mucho más rápido)
                    self.db.execute(insert_staging, buffer)
                    buffer.clear()

            # flush final
            if buffer:
                self.db.execute(insert_staging, buffer)

            if total == 0:
                raise HTTPException(status_code=422, detail="No se encontraron filas válidas.")

            # =====================================================
            # 6) Recalcular counts + commit
            # =====================================================
            self._recalc_batch_counts(batch_id)
            self.db.commit()

            return {
                "batch_id": batch_id,
                "total_registros": total,
                "storage_key": storage_key,
                "checksum_sha256": checksum,
                "docs_placeholders_created": placeholders_created,
            }

        except HTTPException:
            self.db.rollback()
            raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(status_code=500, detail=f"Error creando batch SESAN: {str(e)}")
        finally:
            # limpiar archivo temporal
            try:
                if "tmp_path" in locals() and tmp_path and os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass

    # =====================================================
    # 2) Listar batches por año
    # =====================================================
    def listar_batches(
        self,
        *,
        anio: int,
        mes: int | None,
        estado: str | None,
        fecha_inicio: date | None,
        fecha_fin: date | None,
        page: int,
        limit: int,
    ):
        offset = (page - 1) * limit

        where = [
            "anio_carga = :anio",
            "estado <> 'ELIMINADO'"
        ]

        params: dict = {"anio": anio, "offset": offset, "limit": limit}

        # mes
        if mes is not None:
            where.append("mes_carga = :mes")
            params["mes"] = mes

        # estado (legacy string)
        if estado:
            where.append("UPPER(estado) = UPPER(:estado)")
            params["estado"] = estado

        # fechas sobre created_at
        # - inicio: desde las 00:00:00 del día
        if fecha_inicio is not None:
            where.append("created_at >= :fecha_inicio")
            params["fecha_inicio"] = fecha_inicio

        # - fin: inclusivo por día (hasta < fin + 1 día)
        #   para que si el usuario elige 2026-02-16, incluya TODO ese día
        if fecha_fin is not None:
            where.append("created_at < (:fecha_fin::date + INTERVAL '1 day')")
            params["fecha_fin"] = fecha_fin

        where_sql = " AND ".join(where)

        # COUNT
        total = self.db.execute(
            text(f"SELECT COUNT(*) FROM sesan_batch WHERE {where_sql}"),
            params,
        ).scalar() or 0

        # DATA
        rows = self.db.execute(
            text(f"""
                SELECT *
                FROM sesan_batch
                WHERE {where_sql}
                ORDER BY created_at DESC
                OFFSET :offset
                LIMIT :limit
            """),
            params,
        ).mappings().all()

        return {
            "page": page,
            "limit": limit,
            "total": int(total),
            "data": [dict(r) for r in rows],
        }

    def listar_anios(self):
        rows = self.db.execute(
            text("""
                SELECT
                  anio_carga,
                  COUNT(*) AS total_batches
                FROM sesan_batch
                GROUP BY anio_carga
                ORDER BY anio_carga DESC
            """)
        ).mappings().all()

        return {
            "data": [
                {"anio_carga": r["anio_carga"], "total_batches": int(r["total_batches"])}
                for r in rows
            ]
        }

    # =====================================================
    # 3) Listar filas por batch
    # =====================================================
    def listar_filas_batch(self, *, batch_id: int, estado: str | None, page: int, limit: int):
        offset = (page - 1) * limit

        base = "FROM sesan_staging WHERE batch_id = :batch_id"
        params = {"batch_id": batch_id}

        if estado:
            base += " AND estado = :estado"
            params["estado"] = estado

        total = self.db.execute(
            text(f"SELECT COUNT(*) {base}"),
            params,
        ).scalar() or 0

        rows = self.db.execute(
            text(f"""
                SELECT
                  id, row_num, estado, error_code, error_mensaje,
                  rub,
                  cui_nino, nombre_nino,
                  departamento_residencia, municipio_residencia,
                  cie_10, diagnostico,
                  expediente_id,
                  intentos, ultimo_intento_at,
                  corregido_por, corregido_at,
                  ignorado_por, ignorado_at, motivo_ignorado
                {base}
                ORDER BY row_num ASC
                OFFSET :offset
                LIMIT :limit
            """),
            {**params, "offset": offset, "limit": limit},
        ).mappings().all()

        return {
            "page": page,
            "limit": limit,
            "total": int(total),
            "data": [dict(r) for r in rows],
        }

    # =====================================================
    # 4) Procesar pendientes batch
    # =====================================================
    @staticmethod
    async def procesar_pendientes_batch_background(
        batch_id: int,
        limit: int,
        usuario_id: str | None = None,
    ):

        db = SessionLocal()

        try:

            service = SesanService(db)

            await service.procesar_pendientes_batch(
                batch_id=batch_id,
                limit=limit,
                usuario_id=usuario_id,
            )

        finally:

            db.close()
        
    async def procesar_pendientes_batch(
        self,
        *,
        batch_id: int,
        limit: int,
        usuario_id: str | None = None
    ):

        processor = SesanBatchProcessor(self.bpm)

        while True:

            rows = self.db.execute(
                text("""
                    SELECT id
                    FROM sesan_staging
                    WHERE batch_id = :batch_id
                    AND estado = 'PENDIENTE'
                    ORDER BY row_num ASC
                    LIMIT :limit
                """),
                {"batch_id": batch_id, "limit": limit},
            ).mappings().all()

            ids = [int(r["id"]) for r in rows]

            if not ids:
                break

            await processor.procesar_lote(
                row_ids=ids,
                usuario_id=usuario_id
            )

    # =====================================================
    # 5) Procesar fila individual
    # =====================================================
    async def procesar_row(
        self,
        *,
        row_id: int,
        usuario_id: str | None = None
    ):

        processor = SesanBatchProcessor(self.bpm)

        return await processor.procesar_row(
            row_id=row_id,
            usuario_id=usuario_id
        )
    
    # =====================================================
    # 6) Reintentar errores batch
    # =====================================================
    def reintentar_errores_batch(self, *, batch_id: int, limit: int):
        try:
            updated = self.db.execute(
                text("""
                    WITH to_update AS (
                      SELECT id
                      FROM sesan_staging
                      WHERE batch_id = :batch_id
                        AND estado = 'ERROR'
                      ORDER BY row_num ASC
                      LIMIT :limit
                    )
                    UPDATE sesan_staging s
                    SET
                      estado = 'PENDIENTE',
                      error_code = NULL,
                      error_mensaje = NULL,
                      updated_at = NOW()
                    FROM to_update u
                    WHERE s.id = u.id
                    RETURNING s.id
                """),
                {"batch_id": batch_id, "limit": limit},
            ).fetchall()

            self._recalc_batch_counts(batch_id)
            self.db.commit()

            return {"batch_id": batch_id, "rows_reintentadas": len(updated)}

        except HTTPException:
            self.db.rollback()
            raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(status_code=500, detail=f"Error reintentando errores: {str(e)}")

    # =====================================================
    # 7) Reintentar fila
    # =====================================================
    def reintentar_row(self, *, row_id: int):
        try:
            row = self.db.execute(
                text("SELECT id, batch_id FROM sesan_staging WHERE id = :id"),
                {"id": row_id},
            ).mappings().first()

            if not row:
                raise HTTPException(status_code=404, detail="Fila staging no encontrada.")

            self.db.execute(
                text("""
                    UPDATE sesan_staging
                    SET
                      estado = 'PENDIENTE',
                      error_code = NULL,
                      error_mensaje = NULL,
                      updated_at = NOW()
                    WHERE id = :id
                """),
                {"id": row_id},
            )

            self._recalc_batch_counts(int(row["batch_id"]))
            self.db.commit()

            return {"row_id": row_id, "estado": "PENDIENTE"}

        except HTTPException:
            self.db.rollback()
            raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(status_code=500, detail=f"Error reintentando fila: {str(e)}")

    # =====================================================
    # 8) Ignorar fila
    # =====================================================
    def ignorar_row(self, *, row_id: int, motivo: str, usuario: str | None):
        try:
            row = self.db.execute(
                text("SELECT id, batch_id FROM sesan_staging WHERE id = :id"),
                {"id": row_id},
            ).mappings().first()

            if not row:
                raise HTTPException(status_code=404, detail="Fila staging no encontrada.")

            self.db.execute(
                text("""
                    UPDATE sesan_staging
                    SET
                      estado = 'IGNORADO',
                      motivo_ignorado = :motivo,
                      ignorado_por = :usuario,
                      ignorado_at = NOW(),
                      updated_at = NOW()
                    WHERE id = :id
                """),
                {"id": row_id, "motivo": motivo, "usuario": usuario},
            )

            self._recalc_batch_counts(int(row["batch_id"]))
            self.db.commit()

            return {"row_id": row_id, "estado": "IGNORADO"}

        except HTTPException:
            self.db.rollback()
            raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(status_code=500, detail=f"Error ignorando fila: {str(e)}")

    # =====================================================
    # BPM persistence helpers
    # =====================================================
    def _set_row_bpm_result(self, row_id: int, bpm_status: str, bpm_res: dict, bpm_instance_id: str | None = None):
        """
        Si las columnas aún no existen (esquema viejo), no revienta.
        """
        try:
            self.db.execute(
                text("""
                    UPDATE sesan_staging
                    SET
                      bpm_status = :bpm_status,
                      bpm_instance_id = :bpm_instance_id,
                      bpm_response_json = :bpm_response_json
                    WHERE id = :id
                """),
                {
                    "id": row_id,
                    "bpm_status": bpm_status,
                    "bpm_instance_id": bpm_instance_id,
                    "bpm_response_json": json.dumps(bpm_res, ensure_ascii=False),
                },
            )
        except Exception as e:
            # No cambiamos lógica: solo evitamos que falle por columnas faltantes
            print(f"[SESAN][BPM][WARN] No se pudo guardar bpm_result (¿faltan columnas?): {e}")

    def _set_row_bpm_request(self, row_id: int, bpm_req: dict):
        """
        Si la columna bpm_request_json aún no existe, no revienta.
        """
        try:
            self.db.execute(
                text("""
                    UPDATE sesan_staging
                    SET
                      bpm_request_json = :bpm_request_json
                    WHERE id = :id
                """),
                {
                    "id": row_id,
                    "bpm_request_json": json.dumps(bpm_req, ensure_ascii=False),
                },
            )
        except Exception as e:
            print(f"[SESAN][BPM][WARN] No se pudo guardar bpm_request (¿falta bpm_request_json?): {e}")

    # =====================================================
    # CONSULTA DETALLE BATCH
    # =====================================================
    def obtener_batch(self, batch_id: int) -> dict:
        row = self.db.execute(
            text("""
                SELECT
                    id,
                    nombre_lote,
                    descripcion,
                    origen,
                    anio_carga,
                    mes_carga,
                    usuario_carga,
                    estado,
                    total_registros,
                    total_pendientes,
                    total_en_proceso,
                    total_procesados,
                    total_error,
                    total_ignorados,
                    archivo_nombre_original,
                    archivo_mime_type,
                    archivo_size_bytes,
                    storage_provider,
                    storage_key,
                    checksum_sha256,
                    created_at,
                    updated_at
                FROM sesan_batch
                WHERE id = :id
            """),
            {"id": batch_id},
        ).mappings().first()

        if not row:
            raise HTTPException(status_code=404, detail="Batch no encontrado.")

        return dict(row)

    def listar_documentos_batch(self, batch_id: int) -> list[dict]:
        rows = self.db.execute(
            text("""
                SELECT
                    d.id,
                    d.batch_id,
                    d.tipo_doc_id,
                    t.codigo AS tipo_codigo,
                    t.nombre AS tipo_nombre,
                    t.descripcion AS tipo_descripcion,
                    t.requerido,
                    t.orden,
                    t.activo,

                    d.fecha_documento,
                    d.archivo_nombre_original,
                    d.archivo_mime_type,
                    d.archivo_size_bytes,
                    d.storage_provider,
                    d.storage_key,
                    d.checksum_sha256,
                    d.created_at,
                    d.updated_at,

                    CASE
                        WHEN d.storage_key IS NULL
                          OR d.storage_key = 'PENDIENTE'
                        THEN TRUE
                        ELSE FALSE
                    END AS is_placeholder

                FROM sesan_batch_documento d
                JOIN cat_tipo_doc_batch t ON t.id = d.tipo_doc_id
                WHERE d.batch_id = :batch_id
                ORDER BY t.orden ASC, t.id ASC
            """),
            {"batch_id": batch_id},
        ).mappings().all()

        return [dict(r) for r in rows]

    def obtener_detalle_batch(self, batch_id: int) -> dict:
        batch = self.obtener_batch(batch_id)
        documentos = self.listar_documentos_batch(batch_id)

        return {
            "batch": batch,
            "documentos": documentos,
        }

    def eliminar_lote(self, lote_id: int):
        # 1️⃣ Buscar el lote
        lote = self.db.execute(
            text("""
                SELECT id, estado
                FROM sesan_batch
                WHERE id = :id
            """),
            {"id": lote_id},
        ).mappings().first()

        if not lote:
            raise ValueError("El lote no existe")

        # 2️⃣ Validar estado
        if (lote["estado"] or "").upper() != "EN_REVISION":
            raise ValueError(
                "Solo se pueden eliminar lotes en estado CARGADO"
            )

        # 3️⃣ Soft delete
        self.db.execute(
            text("""
                UPDATE sesan_batch
                SET estado = 'ELIMINADO',
                    updated_at = NOW()
                WHERE id = :id
            """),
            {"id": lote_id},
        )

        # 4️⃣ Confirmar transacción
        self.db.commit()

        return {
            "message": "Lote eliminado correctamente",
            "id": lote_id,
        }
    
    def generar_plantilla_sesan(self):
        headers = [
            "#",
            "AÑO",
            "MES",
            "ÁREA DE SALUD",
            "DISTRITO DE SALUD",
            "SERVICIO DE SALUD",
            "DEPARTAMENTO DE RESIDENCIA",
            "MUNICIPIO DE RESIDENCIA",
            "COMUNIDAD RESIDENCIA",
            "DIRECCIÓN RESIDENCIA",
            "CUI DEL NIÑO",
            "SEXO",
            "EDAD EN AÑOS",
            "NOMBRE DEL NIÑO",
            "FECHA NACIMIENTO",
            "FECHA DEL PRIMER CONTACTO",
            "FECHA DE REGISTRO",
            "CIE-10",
            "DIAGNÓSTICO",
            "NOMBRE DE LA MADRE",
            "CUI DE LA MADRE",
            "NOMBRE DEL PADRE",
            "CUI DEL PADRE",
            "TELÉFONOS ENCARGADOS",
            "VALIDACION",
        ]

        wb = Workbook()
        ws = wb.active
        ws.title = "SESAN"

        # escribir headers
        ws.append(headers)

        # opcional: congelar header
        ws.freeze_panes = "A2"

        # guardar en memoria
        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)

        return buffer
    
    def obtener_totales_batch(self, batch_id: int) -> dict:
        row = self.db.execute(
            text("""
                SELECT
                    id,
                    total_registros,
                    total_pendientes,
                    total_en_proceso,
                    total_procesados,
                    total_error,
                    total_ignorados,
                    estado
                FROM sesan_batch
                WHERE id = :id
            """),
            {"id": batch_id},
        ).mappings().first()

        if not row:
            raise HTTPException(status_code=404, detail="Batch no encontrado.")

        return dict(row)
    
    def reprocesar_batch_esperando_callback(self, batch_id: int):

        rows = self.db.execute(
            text("""
                SELECT bpm_instance_id
                FROM sesan_staging
                WHERE batch_id = :batch_id
                AND estado = 'ESPERANDO_CALLBACK'
            """),
            {"batch_id": batch_id},
        ).mappings().all()

        creator = SesanExpedienteCreator()

        ids = [row["bpm_instance_id"] for row in rows]

        for bpm_instance_id in ids:

            try:

                creator.crear_desde_bpm(
                    bpm_instance_id=bpm_instance_id,
                    usuario_id=None
                )

            except Exception as e:

                print(f"Error reprocesando {bpm_instance_id}: {e}")