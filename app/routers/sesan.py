from datetime import date
from fastapi import APIRouter, BackgroundTasks, Depends, UploadFile, File, Form, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.auth import AuthContext, require_auth_context
from app.core.db import SessionLocal, get_db
from app.services.sesan_batch_proceso_service import SesanBatchProcesoService
from app.services.sesan_service import SesanService

router = APIRouter(prefix="/sesan", tags=["SESAN"])


@router.post("/batch", status_code=201)
def crear_batch_sesan(
    db: Session = Depends(get_db),
    nombre_lote: str = Form(...),
    anio_carga: int = Form(...),
    mes_carga: int | None = Form(None),
    descripcion: str | None = Form(None),
    origen: str = Form("SESAN"),
    # usuario_carga: str | None = Form(None), Se elimina del formulario manual
    file: UploadFile = File(...),
    auth: AuthContext = Depends(require_auth_context), #Se agrega la validación obligatoria
):
    #Se extrae el ID real del token decodificado
    user_id = auth.user.get('id')

    return SesanService(db).crear_batch(
        nombre_lote=nombre_lote,
        anio_carga=anio_carga,
        mes_carga=mes_carga,
        descripcion=descripcion,
        origen=origen,
        usuario_carga=user_id, #Se pasa el ID verificado de Keycloak
        file=file,
    )


@router.get("/batches")
def listar_batches(
    anio: int = Query(...),
    mes: int | None = Query(None, ge=1, le=12),
    estado: str | None = Query(None),
    fecha_inicio: date | None = Query(None),
    fecha_fin: date | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return SesanService(db).listar_batches(
        anio=anio,
        mes=mes,
        estado=estado,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        page=page,
        limit=limit,
    )


@router.get("/anios")
def listar_anios_sesan(db: Session = Depends(get_db)):
    return SesanService(db).listar_anios()


@router.get("/batch/{batch_id}/rows")
def listar_filas_batch(
    batch_id: int,
    estado: str | None = Query(None, description="PENDIENTE | ERROR | PROCESADO | IGNORADO"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return SesanService(db).listar_filas_batch(
        batch_id=batch_id,
        estado=estado,
        page=page,
        limit=limit,
    )


@router.post("/batch/{batch_id}/procesar-pendientes")
async def procesar_pendientes_batch(
    batch_id: int,
    background_tasks: BackgroundTasks,
    limit: int = Query(50, ge=1, le=100),
    auth: AuthContext = Depends(require_auth_context),
    db: Session = Depends(get_db),  # CAMBIO
):

    usuario_id = auth.user.get("id")

    # CAMBIO: crear proceso antes del hilo
    proceso_service = SesanBatchProcesoService(db)
    proceso_id = proceso_service.crear_proceso(
        batch_id=batch_id,
        usuario_id=usuario_id,
    )

    background_tasks.add_task(
        SesanService.procesar_pendientes_batch_background,
        batch_id,
        limit,
        usuario_id,
        proceso_id,  # CAMBIO
    )

    return {
        "mensaje": "Procesamiento iniciado",
        "batch_id": batch_id,
        "limit": limit,
        "proceso_id": proceso_id,  # CAMBIO
    }


@router.post("/row/{row_id}/procesar")
async def procesar_row(
    row_id: int,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_auth_context),
):

    usuario_id = auth.user.get("id")

    service = SesanService(db=db)

    return await service.procesar_row(
        row_id=row_id,
        usuario_id=usuario_id
    )


@router.post("/batch/{batch_id}/reintentar-errores")
def reintentar_errores_batch(
    batch_id: int,
    limit: int = Query(2000, ge=1, le=50000),
    db: Session = Depends(get_db),
):
    return SesanService(db).reintentar_errores_batch(batch_id=batch_id, limit=limit)

@router.post("/row/{row_id}/reintentar")
def reintentar_row(
    row_id: int,
    db: Session = Depends(get_db),
):
    return SesanService(db).reintentar_row(row_id=row_id)

@router.post("/row/{row_id}/ignorar")
def ignorar_row(
    row_id: int,
    motivo: str = Form(...),
    # usuario: str | None = Form(None), Se quita del Form manual
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_auth_context), # <-- Se agrega la validación
):
    # Se extrae el ID real del token decodificado
    user_id = auth.user.get('id')

    return SesanService(db).ignorar_row(
        row_id=row_id, 
        motivo=motivo, 
        usuario=user_id # <-- Se envia ID verificado
    )

@router.get("/batch/{batch_id}")
def obtener_detalle_batch(batch_id: int, db: Session = Depends(get_db)):
    return SesanService(db).obtener_detalle_batch(batch_id)

@router.get("/batch/{batch_id}/proceso")
def obtener_estado_proceso(batch_id: int, db: Session = Depends(get_db)):
    return SesanBatchProcesoService(db).obtener_proceso_batch(batch_id)

@router.delete("/lotes/{lote_id}")
def eliminar_lote(lote_id: int, db: SesanService = Depends(get_db)):
    return SesanService(db).eliminar_lote(lote_id)

@router.get("/plantilla")
def descargar_plantilla(db: SesanService = Depends(get_db)):
    file_stream = SesanService(db).generar_plantilla_sesan()

    return StreamingResponse(
        file_stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": "attachment; filename=plantilla_sesan.xlsx"
        },
    )

@router.get("/batch/{batch_id}/totales")
def obtener_totales_batch(
    batch_id: int,
    db: SesanService = Depends(get_db),
):
    return SesanService(db).obtener_totales_batch(batch_id)


@router.post("/batch/{batch_id}/reprocesar-esperando-callback")
def reprocesar_batch(
    batch_id: int,
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(require_auth_context),  
    db: Session = Depends(get_db),  
):

    usuario_id = auth.user.get("id") 

    proceso_service = SesanBatchProcesoService(db)
    proceso_id = proceso_service.crear_proceso(
        batch_id=batch_id,
        usuario_id=usuario_id,
    )

    background_tasks.add_task(
        reprocesar_batch_wrapper,
        batch_id,
        proceso_id, 
    )

    return {
        "mensaje": "Reproceso iniciado",
        "batch_id": batch_id,
        "proceso_id": proceso_id, 
    }

def reprocesar_batch_wrapper(
    batch_id: int,
    proceso_id: int,  
):

    db = SessionLocal()
    proceso_service = SesanBatchProcesoService(db)  

    try:
        # =========================
        # marcar procesando
        # =========================
        proceso_service.marcar_procesando(proceso_id)  

        SesanService(db).reprocesar_batch_esperando_callback(
            batch_id=batch_id,
            proceso_id=proceso_id,  
        )

        # =========================
        # finalizar OK
        # =========================
        proceso_service.finalizar_ok(proceso_id)  

    except Exception as e:
        # =========================
        # finalizar ERROR
        # =========================
        proceso_service.finalizar_error(proceso_id, str(e))  
        raise

    finally:
        db.close()