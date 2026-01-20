from fastapi import APIRouter, HTTPException
import httpx

from app.bpm.keycloak_client import KeycloakClient
from app.bpm.bpm_client import BpmClient

router = APIRouter(prefix="/bpm", tags=["BPM"])


# =====================================================
# 🔐 Prueba Keycloak (token password grant)
# =====================================================
@router.get("/auth/token")
async def get_keycloak_token():
    """
    PRUEBA:
    Obtiene token desde Keycloak (password grant).
    Devuelve JSON con access_token, expires_in, etc.
    """
    try:
        kc = KeycloakClient()
        token = await kc.get_token_password_grant()
        return token

    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    except httpx.HTTPStatusError as e:
        try:
            body = e.response.json()
        except Exception:
            body = {"error": e.response.text}

        raise HTTPException(
            status_code=e.response.status_code,
            detail={
                "message": "Keycloak rechazó la solicitud de token",
                "keycloak": body,
            },
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================
# ✅ PRUEBA BPM: consultar estado de instancia
# =====================================================
@router.get("/process-instance/{bpm_instance_id}")
async def get_process_instance(bpm_instance_id: int):
    """
    PRUEBA BPM:
    Consulta el estado de una instancia Spiff ya creada
    (después de POST /messages/registrar_nutricion).
    """
    bpm = BpmClient()

    try:
        result = await bpm.get_process_instance(bpm_instance_id)
        return {
            "bpm_instance_id": str(bpm_instance_id),
            "process_instance": result,
        }
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Error consultando instancia BPM: {str(e)}",
        )
