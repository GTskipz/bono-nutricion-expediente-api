import json

from sqlalchemy import text
from sqlalchemy.orm import Session

import asyncio

from app.bpm.bpm_service_task_data import BpmServiceTaskData
from app.core.db import SessionLocal
from app.schemas.expediente import ExpedienteCreate, InfoGeneralIn
from app.services.expedientes_service import (
    crear_expediente_core,
    set_expediente_bpm_minimo_core,
)

from app.services.utils import norm_lookup, norm_str, to_cui, to_int


class SesanExpedienteCreator:

    def crear_desde_bpm(self, bpm_instance_id: str, usuario_id: str | None = None):

        db: Session = SessionLocal()

        try:

            row = db.execute(
                text("""
                    SELECT s.*, b.anio_carga, b.mes_carga
                    FROM sesan_staging s
                    JOIN sesan_batch b ON b.id = s.batch_id
                    WHERE s.bpm_instance_id = :iid
                """),
                {"iid": bpm_instance_id},
            ).mappings().first()

            if not row:
                raise ValueError("Registro no encontrado")

            if row["estado"] == "PROCESADO":
                return {"mensaje": "Registro ya procesado"}

            if row["estado"] != "ESPERANDO_CALLBACK":
                raise ValueError("Registro no está esperando callback BPM")

            anio_carga = int(row["anio_carga"])
            mes_carga = int(row["mes_carga"]) if row.get("mes_carga") else None

            # =====================================================
            # CONSULTA REAL AL BPM
            # =====================================================
            bpm_service = BpmServiceTaskData(db)

            bpm_response = asyncio.run(
                bpm_service.obtener_task_data_por_bpm_instance_id(
                    bpm_instance_id=int(bpm_instance_id)
                )
            )

            bpm_data = self._extraer_datos_bpm(bpm_response)

            # =====================================================
            # VALIDACIÓN SNIS / RENAP
            # =====================================================
            self._validar_personas_bpm(bpm_data)

            # =====================================================
            # CREAR PAYLOAD DEL EXPEDIENTE
            # =====================================================
            payload = self._build_expediente_payload_from_bpm(
                db,
                bpm_data,
                anio_carga,
                mes_carga,
            )

            exp = crear_expediente_core(payload, db)

            if usuario_id:

                db.execute(
                    text("""
                        UPDATE expediente_electronico
                        SET usuario_creacion_id = :uid
                        WHERE id = :eid
                    """),
                    {"uid": usuario_id, "eid": int(exp.id)},
                )

            self._update_expediente_bpm_data(
                db=db,
                expediente_id=int(exp.id),
                bpm_instance_id=bpm_instance_id,
                bpm_response=bpm_response,
                bpm_data=bpm_data,
            )

            db.execute(
                text("""
                    UPDATE sesan_staging
                    SET estado='PROCESADO',
                        expediente_id=:exp
                    WHERE id=:id
                """),
                {"id": row["id"], "exp": exp.id},
            )

            db.commit()

            return {"expediente_id": exp.id}

        except Exception as e:

            db.rollback()

            db.execute(
                text("""
                    UPDATE sesan_staging
                    SET estado='ERROR',
                        error_code='CALLBACK_ERROR',
                        error_mensaje=:msg
                    WHERE bpm_instance_id=:iid
                """),
                {
                    "iid": bpm_instance_id,
                    "msg": str(e)
                }
            )

            db.commit()

            raise

        finally:
            db.close()

    # =====================================================
    # CATÁLOGOS
    # =====================================================

    def _cat_id_by_name(self, db: Session, table: str, name_col: str, value: str | None):

        v = norm_lookup(value)

        if not v:
            return None

        row = db.execute(
            text(f"SELECT id FROM {table} WHERE UPPER({name_col}) = :v LIMIT 1"),
            {"v": v},
        ).scalar()

        return int(row) if row is not None else None

    def _sexo_id(self, db: Session, value: str | None):

        s = norm_lookup(value)

        if not s:
            return None

        if s in ("M", "MASCULINO", "HOMBRE", "1"):
            code = "M"

        elif s in ("F", "FEMENINO", "MUJER", "2"):
            code = "F"

        else:
            return None

        sid = self._cat_id_by_name(db, "cat_sexo", "codigo", code)

        if sid is None:
            sid = self._cat_id_by_name(db, "cat_sexo", "nombre", code)

        return sid

    # =====================================================
    # VALIDACION BPM
    # =====================================================

    def _persona_valida(self, persona: dict | None):

        if not persona:
            return False

        snis = persona.get("validado_snis")
        renap = persona.get("validado_renap")

        return bool(snis) or bool(renap)

    def _extraer_datos_bpm(self, bpm_response: dict):

        if not bpm_response:
            raise ValueError("Respuesta BPM vacía")

        data = bpm_response.get("data")

        if not isinstance(data, dict):
            raise ValueError("Respuesta BPM inválida")

        return data

    def _validar_personas_bpm(self, data: dict):

        nino = data.get("validar_nino")
        madre = data.get("validar_madre")
        padre = data.get("validar_padre")

        if not self._persona_valida(nino):
            raise ValueError("Niño no validado en SNIS ni RENAP")

        if madre and not self._persona_valida(madre):
            raise ValueError("Madre no validada en SNIS ni RENAP")

        if padre and not self._persona_valida(padre):
            raise ValueError("Padre no validado en SNIS ni RENAP")

    # =====================================================
    # CREACIÓN PAYLOAD DESDE BPM
    # =====================================================

    def _build_expediente_payload_from_bpm(
        self,
        db: Session,
        data: dict,
        anio_carga: int,
        mes_carga: int | None,
    ):

        menor = data.get("seccion_menor") or {}
        padres = data.get("seccion_padres") or {}
        salud = data.get("seccion_salud") or {}
        ubicacion = data.get("seccion_ubicacion") or {}

        if not menor:
            raise ValueError("No se encontró seccion_menor")

        nombre_nino = norm_str(menor.get("beneficiario_nombre"))
        cui_nino = to_cui(menor.get("beneficiario_cui"))
        sexo = menor.get("beneficiario_sexo")

        sexo_id = self._sexo_id(db, sexo)

        depto_res_id = self._cat_id_by_name(
            db,
            "cat_departamento",
            "nombre",
            ubicacion.get("residencia_departamento")
        )

        muni_res_id = self._cat_id_by_name(
            db,
            "cat_municipio",
            "nombre",
            ubicacion.get("residencia_municipio")
        )

        area_id = self._cat_id_by_name(
            db,
            "cat_area_salud",
            "nombre",
            salud.get("area_salud")
        )

        distrito_id = self._cat_id_by_name(
            db,
            "cat_distrito_salud",
            "nombre",
            salud.get("distrito_salud")
        )

        servicio_id = self._cat_id_by_name(
            db,
            "cat_servicio_salud",
            "nombre",
            salud.get("servicio_salud")
        )

        ig = InfoGeneralIn(
            anio=str(anio_carga),
            mes=str(mes_carga) if mes_carga else None,
            area_salud_id=area_id,
            distrito_salud_id=distrito_id,
            servicio_salud_id=servicio_id,
            departamento_residencia_id=depto_res_id,
            municipio_residencia_id=muni_res_id,
            comunidad_residencia=norm_str(ubicacion.get("residencia_comunidad")),
            direccion_residencia=norm_str(ubicacion.get("residencia_direccion")),
            cui_del_nino=cui_nino,
            sexo_id=sexo_id,
            edad_en_anios=menor.get("edad_anos"),
            nombre_del_nino=nombre_nino,
            fecha_nacimiento=menor.get("beneficiario_fecha_nacimiento"),
            fecha_del_primer_contacto=salud.get("fecha_contacto"),
            fecha_de_registro=salud.get("fecha_registro"),
            cie_10=norm_str(salud.get("cie_10")),
            diagnostico=norm_str(salud.get("diagnostico")),
            nombre_de_la_madre=norm_str(padres.get("nombre_madre")),
            cui_de_la_madre=to_cui(padres.get("dpi_madre")),
            nombre_del_padre=norm_str(padres.get("nombre_padre")),
            cui_del_padre=to_cui(padres.get("dpi_padre")),
            telefonos_encargados=norm_str(padres.get("telefonos")),
            validacion_id=None,
        )

        payload = ExpedienteCreate(
            nombre_beneficiario=nombre_nino,
            cui_beneficiario=cui_nino,
            rub="",
            departamento_id=depto_res_id,
            municipio_id=muni_res_id,
            anio_carga=anio_carga,
            info_general=ig,
        )

        return payload
    
    def _update_expediente_bpm_data(
        self,
        db: Session,
        expediente_id: int,
        bpm_instance_id: str,
        bpm_response: dict,
        bpm_data: dict,
    ):

        process_instance = bpm_response.get("process_instance") or {}

        menor = bpm_data.get("seccion_menor") or {}
        salud = bpm_data.get("seccion_salud") or {}

        nino = bpm_data.get("validar_nino") or {}
        madre = bpm_data.get("validar_madre") or {}
        padre = bpm_data.get("validar_padre") or {}

        bpm_variables = {
            "validaciones": {
                "beneficiario": {
                    "snis": nino.get("validado_snis"),
                    "renap": nino.get("validado_renap"),
                },
                "madre": {
                    "snis": madre.get("validado_snis"),
                    "renap": madre.get("validado_renap"),
                },
                "padre": {
                    "snis": padre.get("validado_snis"),
                    "renap": padre.get("validado_renap"),
                },
            },
            "resultado_elegibilidad": bpm_data.get("resultado_elegibilidad"),
            "monto_bono": bpm_data.get("monto_bono"),
            "diagnostico": salud.get("diagnostico"),
            "cie_10": salud.get("cie_10"),
        }

        db.execute(
            text("""
                UPDATE expediente_electronico
                SET
                    bpm_process_key = :process_key,
                    bpm_instance_id = :instance_id,
                    bpm_status = :status,
                    bpm_current_task_name = :task_name,
                    bpm_variables = :vars,
                    bpm_last_sync_at = now()
                WHERE id = :id
            """),
            {
                "id": expediente_id,
                "process_key": process_instance.get("process_model_identifier"),
                "instance_id": bpm_instance_id,
                "status": process_instance.get("status"),
                "task_name": process_instance.get("last_milestone_bpmn_name"),
                "vars": json.dumps(bpm_variables), 
            },
        )