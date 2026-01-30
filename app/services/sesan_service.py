# app/services/sesan_service.py
from __future__ import annotations

import os   # Agregado para variables de entorno
import io   # Agregado para manejo de streams de bytes
from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime
import json

from app.services.excel_reader import read_sesan_xlsx_rows
from app.services.utils import (
    norm_str, to_int, to_date, sha256_bytes, to_cui, to_rub, norm_lookup
)

# ✅ Reusar creación oficial de expediente
from app.routers.expedientes import crear_expediente_core
from app.schemas.expediente import ExpedienteCreate, InfoGeneralIn

from app.bpm.bpm_client import BpmClient
from app.bpm.bpm_payload_builder import build_spiff_payload_from_staging_row

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

    def _set_row_error(self, row_id: int, code: str, msg: str):
        self.db.execute(
            text("""
                UPDATE sesan_staging
                SET
                  estado = 'ERROR',
                  error_code = :code,
                  error_mensaje = :msg,
                  intentos = COALESCE(intentos, 0) + 1,
                  ultimo_intento_at = NOW(),
                  updated_at = NOW()
                WHERE id = :id
            """),
            {"id": row_id, "code": code, "msg": msg},
        )

    def _set_row_processed(self, row_id: int, expediente_id: int):
        self.db.execute(
            text("""
                UPDATE sesan_staging
                SET
                  estado = 'PROCESADO',
                  expediente_id = :expediente_id,
                  error_code = NULL,
                  error_mensaje = NULL,
                  intentos = COALESCE(intentos, 0) + 1,
                  ultimo_intento_at = NOW(),
                  updated_at = NOW()
                WHERE id = :id
            """),
            {"id": row_id, "expediente_id": expediente_id},
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
        rub = to_rub(row.get("rub"))
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
    # ✅ Procesar 1 fila (BPM decide → si aprueba crea expediente)
    # =====================================================
    async def _procesar_row_creando_expediente(self, row_id: int):
        print(f"[SESAN] ▶️ Iniciando procesamiento row_id={row_id}")

        row = self.db.execute(
            text("""
                SELECT
                s.*,
                b.anio_carga,
                b.mes_carga
                FROM sesan_staging s
                JOIN sesan_batch b ON b.id = s.batch_id
                WHERE s.id = :id
                FOR UPDATE
            """),
            {"id": row_id},
        ).mappings().first()

        if not row:
            print(f"[SESAN][ERROR] ❌ Row {row_id} no encontrada")
            raise HTTPException(status_code=404, detail="Fila staging no encontrada.")

        print(f"[SESAN] Estado actual={row.get('estado')} batch_id={row.get('batch_id')}")

        if row["estado"] == "IGNORADO":
            print(f"[SESAN] ⚠️ Row {row_id} está IGNORADA")
            raise HTTPException(status_code=409, detail="La fila está IGNORADA.")

        if row["estado"] == "PROCESADO" and row.get("expediente_id"):
            print(f"[SESAN] ✅ Row {row_id} ya procesada expediente_id={row.get('expediente_id')}")
            return {
                "row_id": row_id,
                "estado": "PROCESADO",
                "expediente_id": int(row["expediente_id"])
            }

        anio_carga = int(row["anio_carga"])
        mes_carga = int(row["mes_carga"]) if row.get("mes_carga") is not None else None

        rub = to_rub(row.get("rub"))
        cui = to_cui(row.get("cui_nino"))
        nombre = norm_str(row.get("nombre_nino"))

        print(
            f"[SESAN] Datos básicos -> "
            f"año={anio_carga} mes={mes_carga} rub={rub} cui={cui} nombre={nombre}"
        )

        if not cui:
            print(f"[SESAN][ERROR] ❌ CUI vacío row_id={row_id}")
            raise ValueError("MISSING_CUI|CUI del niño vacío.")

        if not nombre:
            print(f"[SESAN][ERROR] ❌ Nombre vacío row_id={row_id}")
            raise ValueError("MISSING_NAME|Nombre del niño vacío.")

        if self._is_dup_cui_in_year(cui, anio_carga, row_id):
            print(f"[SESAN][ERROR] ❌ CUI duplicado en staging año={anio_carga}")
            raise ValueError(f"DUP_CUI_YEAR|CUI duplicado en el año de carga {anio_carga} (staging).")

        if self._is_dup_cui_in_expedientes(cui, anio_carga):
            print(f"[SESAN][ERROR] ❌ CUI duplicado en expedientes año={anio_carga}")
            raise ValueError(f"DUP_CUI_YEAR|CUI duplicado en el año de carga {anio_carga} (expedientes).")

        if rub:
            if self._is_dup_rub_in_year(rub, anio_carga, row_id):
                print(f"[SESAN][ERROR] ❌ RUB duplicado en staging año={anio_carga}")
                raise ValueError(f"DUP_RUB_YEAR|RUB duplicado en el año de carga {anio_carga} (staging).")

            if self._is_dup_rub_in_expedientes(rub, anio_carga):
                print(f"[SESAN][ERROR] ❌ RUB duplicado en expedientes año={anio_carga}")
                raise ValueError(f"DUP_RUB_YEAR|RUB duplicado en el año de carga {anio_carga} (expedientes).")

        # =====================================================
        # ✅ BPM decide
        # =====================================================
        try:
            print(f"[SESAN][BPM] ▶️ Construyendo payload BPM row_id={row_id}")
            payload_spiff = build_spiff_payload_from_staging_row(row=row)

            print(f"[SESAN][BPM] Payload enviado:\n{payload_spiff}")

            # Guardar request BPM (si existe columna)
            self._set_row_bpm_request(row_id=row_id, bpm_req=payload_spiff)

            print(f"[SESAN][BPM] ▶️ Enviando a Spiff (message registrar_nutricion)")
            bpm_eval = await self.bpm.evaluate_run_and_get_decision(payload_spiff)

            print(
                f"[SESAN][BPM] Respuesta -> "
                f"instance_id={bpm_eval.bpm_instance_id} "
                f"status={bpm_eval.status} "
                f"milestone={bpm_eval.last_milestone_bpmn_name} "
                f"should_create={bpm_eval.should_create_expediente}"
            )

            # Guardar respuesta BPM (si existe columna)
            self._set_row_bpm_result(
                row_id=row_id,
                bpm_status=bpm_eval.status,
                bpm_res=bpm_eval.raw_status,
                bpm_instance_id=str(bpm_eval.bpm_instance_id),
            )

            if not bpm_eval.should_create_expediente:
                print(f"[SESAN][BPM] ❌ NO permitido crear expediente (DPI no encontrado)")
                # ✅ CORREGIDO: firma real (code, msg)
                self._set_row_error(
                    row_id,
                    "DPI_NO_ENCONTRADO",
                    "No se pudo validar el DPI del niño en los registros oficiales."
                )
                return {
                    "row_id": row_id,
                    "estado": "ERROR",
                    "codigo": "DPI_NO_ENCONTRADO"
                }

        except Exception as e:
            print(f"[SESAN][BPM][ERROR] ❌ {str(e)}")
            # ✅ CORREGIDO: firma real (code, msg)
            self._set_row_error(
                row_id,
                "BPM_ERROR",
                str(e)
            )
            raise ValueError(f"BPM_ERROR|{str(e)}")

        # =====================================================
        # ✅ Crear expediente
        # =====================================================
        print(f"[SESAN] ▶️ Creando expediente electrónico row_id={row_id}")
        payload = self._build_expediente_payload_from_row(row, anio_carga, mes_carga)
        exp = crear_expediente_core(payload, self.db)

        self._set_row_processed(row_id, int(exp.id))
        self._recalc_batch_counts(int(row["batch_id"]))

        print(f"[SESAN] ✅ Expediente creado id={exp.id} row_id={row_id}")

        return {
            "row_id": row_id,
            "estado": "PROCESADO",
            "expediente_id": int(exp.id)
        }

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
        try:
            file_bytes = file.file.read()
            if not file_bytes:
                raise HTTPException(status_code=400, detail="Archivo vacío.")

            size_bytes = len(file_bytes)
            checksum = sha256_bytes(file_bytes)

            ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
            safe_name = (file.filename or "sesan.xlsx").replace("\\", "_").replace("/", "_")
            
            # INICIO CAMBIO A MINIO (Mantiene lógica original, agrega MinIO)
            bucket_name = os.getenv("MINIO_BUCKET", "almacenamiento-mis")
            # Estructura: sesan/2026/20260127120000_archivo.xlsx
            object_name = f"sesan/{anio_carga}/{ts}_{safe_name}"

            if minio_client:
                # Subir el archivo real a MinIO
                minio_client.put_object(
                    bucket_name,
                    object_name,
                    io.BytesIO(file_bytes),
                    size_bytes,
                    content_type=file.content_type
                )
                storage_provider = "MINIO"
                storage_key = object_name 
            else:
                # Fallback original por si acaso falla la importación
                print("Cliente MinIO no disponible, usando FTP simulado")
                storage_provider = "ftp"
                storage_key = f"ftp://PENDIENTE/sesan/{ts}_{safe_name}"
            # FIN CAMBIO MINIO

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

            rows = read_sesan_xlsx_rows(file_bytes)
            if not rows:
                raise HTTPException(status_code=422, detail="No se encontraron filas válidas.")

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

            total = 0
            for item in rows:
                r = item["data"]
                raw_for_audit = item.get("raw") or {}

                self.db.execute(
                    insert_staging,
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

            self._recalc_batch_counts(batch_id)
            self.db.commit()

            return {
                "batch_id": batch_id,
                "total_registros": total,
                "storage_key": storage_key,
                "checksum_sha256": checksum,
            }

        except HTTPException:
            self.db.rollback()
            raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(status_code=500, detail=f"Error creando batch SESAN: {str(e)}")

    # =====================================================
    # 2) Listar batches por año
    # =====================================================
    def listar_batches_por_anio(self, *, anio: int, page: int, limit: int):
        offset = (page - 1) * limit

        total = self.db.execute(
            text("SELECT COUNT(*) FROM sesan_batch WHERE anio_carga = :anio"),
            {"anio": anio},
        ).scalar() or 0

        rows = self.db.execute(
            text("""
                SELECT *
                FROM sesan_batch
                WHERE anio_carga = :anio
                ORDER BY created_at DESC
                OFFSET :offset
                LIMIT :limit
            """),
            {"anio": anio, "offset": offset, "limit": limit},
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
    async def procesar_pendientes_batch(self, *, batch_id: int, limit: int):
        try:
            batch = self.db.execute(
                text("SELECT id, anio_carga FROM sesan_batch WHERE id = :id"),
                {"id": batch_id},
            ).mappings().first()

            if not batch:
                raise HTTPException(status_code=404, detail="Batch no encontrado.")

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

            procesados = 0
            errores = 0

            for r in rows:
                rid = int(r["id"])
                try:
                    await self._procesar_row_creando_expediente(rid)
                    procesados += 1
                except ValueError as ve:
                    raw = str(ve)
                    if "|" in raw:
                        code, msg = raw.split("|", 1)
                    else:
                        code, msg = "VALIDATION_ERROR", raw
                    self._set_row_error(rid, code.strip(), msg.strip())
                    errores += 1
                except HTTPException as he:
                    self._set_row_error(rid, "HTTP_ERROR", str(he.detail))
                    errores += 1
                except Exception as e:
                    self._set_row_error(rid, "UNEXPECTED_ERROR", str(e))
                    errores += 1

            self._recalc_batch_counts(batch_id)
            self.db.commit()

            return {
                "batch_id": batch_id,
                "procesados": procesados,
                "errores": errores,
                "total_intentados": len(rows),
            }

        except HTTPException:
            self.db.rollback()
            raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(status_code=500, detail=f"Error procesando pendientes: {str(e)}")

    # =====================================================
    # 5) Procesar fila individual
    # =====================================================
    async def procesar_row(self, *, row_id: int):
        try:
            result = await self._procesar_row_creando_expediente(row_id)
            self.db.commit()
            return result

        except HTTPException:
            self.db.rollback()
            raise

        except ValueError as ve:
            self.db.rollback()
            raw = str(ve)
            if "|" in raw:
                code, msg = raw.split("|", 1)
            else:
                code, msg = "VALIDATION_ERROR", raw

            self._set_row_error(row_id, code.strip(), msg.strip())

            try:
                b = self.db.execute(
                    text("SELECT batch_id FROM sesan_staging WHERE id=:id"),
                    {"id": row_id},
                ).scalar()
                if b is not None:
                    self._recalc_batch_counts(int(b))
                self.db.commit()
            except Exception:
                self.db.rollback()

            raise HTTPException(status_code=422, detail=msg.strip())

        except Exception as e:
            self.db.rollback()
            self._set_row_error(row_id, "UNEXPECTED_ERROR", str(e))

            try:
                b = self.db.execute(
                    text("SELECT batch_id FROM sesan_staging WHERE id=:id"),
                    {"id": row_id},
                ).scalar()
                if b is not None:
                    self._recalc_batch_counts(int(b))
                self.db.commit()
            except Exception:
                self.db.rollback()

            raise HTTPException(status_code=500, detail=f"Error procesando fila: {str(e)}")

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