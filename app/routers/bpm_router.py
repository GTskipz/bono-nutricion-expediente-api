from fastapi import APIRouter, Depends, HTTPException
import httpx
from sqlalchemy.orm import Session

from app.bpm.keycloak_client import KeycloakClient
from app.bpm.bpm_client import BpmClient

from app.core.db import get_db
from app.bpm.bpm_service_task_data import BpmServiceTaskData
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

@router.get("/task/{task_id}/instruction")
async def get_task_instruction(task_id: int):
    bpm = BpmClient()
    try:
        result = await bpm.get_task_instruction(task_id)
        return {
            "task_id": task_id,
            "instruction": result,
        }
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Error consultando task instruction BPM: {str(e)}",
        )
    
@router.get("/expediente/{expediente_id}/task/data")
async def get_task_data_por_expediente(
    expediente_id: int,
    db: Session = Depends(get_db),
):
    service = BpmServiceTaskData(db)

    try:
        result = await service.obtener_task_data_por_expediente_id(
            expediente_id=expediente_id
        )

        return {
            "expediente_id": expediente_id,
            "data": result,
        }

    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Error consultando task data BPM por expediente: {str(e)}",
        )
    
@router.get("/instancia/{bpm_instance_id}/task/data")
async def get_task_data_por_instancia(
    bpm_instance_id: int,
    db: Session = Depends(get_db),
):
    service = BpmServiceTaskData(db)

    try:
        result = await service.obtener_task_data_por_bpm_instance_id(
            bpm_instance_id=bpm_instance_id
        )

        return {
            "bpm_instance_id": bpm_instance_id,
            "data": result,
        }

    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Error consultando task data BPM por instancia: {str(e)}",
        )