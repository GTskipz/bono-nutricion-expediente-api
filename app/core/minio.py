import os
from minio import Minio
from dotenv import load_dotenv
# Se importa para manejar la conexión SSL
import urllib3 

# Asegurar carga de variables
load_dotenv()

def get_minio_client():
    try:
        # 1. Creamos un gestor de conexiones que IGNORE los certificados (CERT_NONE)
        # Esto es necesario porque el servidor MIDES tiene un certificado autofirmado.
        http_client = urllib3.PoolManager(
            timeout=urllib3.Timeout.DEFAULT_TIMEOUT,
            cert_reqs='CERT_NONE',  #Desactiva la verificación SSL
            retries=urllib3.Retry(
                total=5,
                backoff_factor=0.2,
                status_forcelist=[500, 502, 503, 504]
            )
        )

        client = Minio(
            endpoint=os.getenv("MINIO_ENDPOINT", "minio.mis.com"),
            access_key=os.getenv("MINIO_ACCESS_KEY"),
            secret_key=os.getenv("MINIO_SECRET_KEY"),
            secure=str(os.getenv("MINIO_SECURE", "True")).lower() == "true",
            # 2.Le pasamos nuestro cliente permisivo a MinIO
            http_client=http_client, 
            region="us-east-1"
        )
        return client
    except Exception as e:
        print(f"Error fatal iniciando cliente MinIO: {e}")
        return None

# Instancia única
minio_client = get_minio_client()