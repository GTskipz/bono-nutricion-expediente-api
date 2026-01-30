from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import timedelta
import os

# Importamos el cliente de MinIO ya configurado (con el fix SSL)
from app.core.minio import minio_client
# Importamos la función para obtener la sesión de base de datos
from app.core.db import get_db

router = APIRouter(
    prefix="/archivos",
    tags=["Gestión de Archivos"]
)

# ==========================================
# ENDPOINT 1: Generar URL para SUBIDA (PUT)
# ==========================================
@router.get("/generar-url-subida")
def obtener_url_firmada(nombre_archivo: str):
    """
    Genera una URL firmada temporal para que el Frontend suba archivos 
    directamente a MinIO (sin pasar la carga pesada por el Backend).
    """
    if not minio_client:
        raise HTTPException(status_code=500, detail="El servicio de almacenamiento no está disponible")

    try:
        # Obtenemos el nombre del bucket de las variables de entorno (default: almacenamiento-mis)
        bucket_name = os.getenv("MINIO_BUCKET", "almacenamiento-mis")
        
        # Generamos la URL firmada con validez de 30 minutos
        url = minio_client.presigned_put_object(
            bucket_name,
            nombre_archivo,
            expires=timedelta(minutes=30)
        )
        return {"url": url, "bucket": bucket_name}
        
    except Exception as e:
        print(f"Error generando URL firmada MinIO: {e}")
        raise HTTPException(status_code=500, detail="Error generando el permiso de subida")


# ==========================================
# ENDPOINT 2: DESCARGAR Archivo MASIVO (GET)
# ==========================================
@router.get("/descargar/{batch_id}")
def descargar_archivo_proxy(
    batch_id: int, 
    db: Session = Depends(get_db)
):
    """
    Descarga un archivo desde MinIO actuando como Proxy (Intermediario).
    1. Busca la metadata en la Base de Datos (PostgreSQL).
    2. Conecta con MinIO para obtener el flujo de bytes (Stream).
    3. Entrega el archivo al navegador del usuario como descarga.
    """
    
    # 1. Consultar la metadata usando SQL Puro (text)
    #    Esto es robusto y evita errores si no tienes los modelos ORM importados.
    query = text("""
        SELECT id, storage_key, storage_provider, archivo_nombre_original, archivo_mime_type 
        FROM sesan_batch 
        WHERE id = :id
    """)
    
    # Ejecutamos la consulta
    result = db.execute(query, {"id": batch_id}).first()
    
    # Validación: ¿Existe el registro en la BD?
    if not result:
        raise HTTPException(status_code=404, detail="Registro de archivo no encontrado en base de datos")
        
    # Extraemos los datos (SQLAlchemy permite acceso por punto .campo)
    storage_key = result.storage_key
    storage_provider = result.storage_provider
    nombre_archivo = result.archivo_nombre_original
    mime_type = result.archivo_mime_type

    # Validación: ¿El archivo tiene una ruta válida en MinIO?
    if not storage_key or storage_provider != "MINIO":
        raise HTTPException(status_code=404, detail="El archivo físico no está disponible en el almacenamiento")

    # 2. Conectar con MinIO para obtener el flujo de datos
    try:
        if not minio_client:
             raise HTTPException(status_code=500, detail="Cliente MinIO no inicializado")

        bucket_name = os.getenv("MINIO_BUCKET", "almacenamiento-mis")

        # get_object devuelve un "stream" (un flujo de datos abierto)
        data_stream = minio_client.get_object(bucket_name, storage_key)
        
        # 3. Preparar los encabezados HTTP para forzar la descarga
        #    Si el nombre original es nulo, generamos uno genérico.
        filename_final = nombre_archivo if nombre_archivo else f"archivo_lote_{batch_id}.xlsx"
        
        headers = {
            # 'attachment' le dice al navegador: "Descárgalo, no lo muestres en pantalla"
            "Content-Disposition": f'attachment; filename="{filename_final}"'
        }

        # 4. Devolver la respuesta en streaming (Tubo directo MinIO -> Usuario)
        #    Leemos en trozos de 32KB para ser eficientes con la memoria RAM.
        return StreamingResponse(
            data_stream.stream(32 * 1024),
            media_type=mime_type or "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers=headers
        )

    except Exception as e:
        print(f"Error descargando desde MinIO: {e}")
        raise HTTPException(status_code=500, detail="Error recuperando el archivo del servidor de almacenamiento")


# ====================================================
# ENDPOINT 3: DESCARGAR Documento Expediente (GET)
# ====================================================
@router.get("/expedientes/documento/{doc_id}")
def descargar_documento_expediente(
    doc_id: int, 
    db: Session = Depends(get_db)
):
    """
    Descarga un documento individual (DPI, Recibo, etc) desde la tabla documentos_y_anexos.
    """
    # 1. Buscar la metadata usando el nombre REAL de la tabla
    query = text("""
        SELECT id, storage_key, filename, mime_type, storage_provider 
        FROM documentos_y_anexos 
        WHERE id = :id
    """)
    
    result = db.execute(query, {"id": doc_id}).first()
    
    # Validaciones de seguridad
    if not result:
        raise HTTPException(status_code=404, detail="Documento no encontrado en la base de datos")

    storage_key = result.storage_key
    filename = result.filename
    mime_type = result.mime_type
    provider = result.storage_provider

    if not storage_key:
        raise HTTPException(status_code=404, detail="El registro existe pero no tiene archivo asociado")

    # (Opcional) Verificar que sea de MinIO
    if provider and provider != "MINIO":
         # Si tienes archivos viejos en FTP o disco local, aquí podrías manejarlos diferente
         pass 

    # 2. Conectar a MinIO y hacer Streaming
    try:
        bucket_name = os.getenv("MINIO_BUCKET", "almacenamiento-mis")
        
        if not minio_client:
             raise HTTPException(status_code=500, detail="Servicio de almacenamiento no disponible")

        # Obtenemos el flujo de datos desde MinIO
        data_stream = minio_client.get_object(bucket_name, storage_key)
        
        # Generamos nombre final si viene nulo
        final_name = filename if filename else f"documento_{doc_id}.dat"
        
        # 3. Responder con el archivo
        return StreamingResponse(
            data_stream.stream(32 * 1024),
            media_type=mime_type or "application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="{final_name}"'
            }
        )

    except Exception as e:
        print(f"Error descargando documento {doc_id}: {e}")
        # Tip: Si MinIO da error "NoSuchKey", significa que el archivo se borró de la bodega pero sigue en la BD
        raise HTTPException(status_code=404, detail="El archivo físico no se encuentra en el servidor")