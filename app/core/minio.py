import os
from minio import Minio
from dotenv import load_dotenv
import urllib3

# cargar variables
load_dotenv()


def get_minio_client():

    try:

        http_client = urllib3.PoolManager(

            # timeout prudente
            timeout=urllib3.Timeout(
                connect=5.0,   # tiempo máximo para conectar
                read=60.0      # tiempo máximo esperando respuesta
            ),

            cert_reqs='CERT_NONE',  # servidor usa certificado autofirmado

            retries=urllib3.Retry(
                total=3,
                backoff_factor=0.5,
                status_forcelist=[500, 502, 503, 504]
            )
        )

        client = Minio(
            endpoint=os.getenv("MINIO_ENDPOINT", "minio.mis.com"),
            access_key=os.getenv("MINIO_ACCESS_KEY"),
            secret_key=os.getenv("MINIO_SECRET_KEY"),
            secure=str(os.getenv("MINIO_SECURE", "True")).lower() == "true",
            http_client=http_client,
            region="us-east-1"
        )

        return client

    except Exception as e:

        print(f"Error fatal iniciando cliente MinIO: {e}")

        return None


# instancia única
minio_client = get_minio_client()