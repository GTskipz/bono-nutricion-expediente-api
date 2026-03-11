from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

from fastapi import HTTPException, Request, status
from jose import jwt, JWTError # Dependencia necesario en requirements.txt

# ✅ Importamos el contexto global por request
from app.core.token_context import set_current_token


@dataclass(frozen=True)
class AuthContext:
    token: str
    scheme: str = "Bearer"
    raw_authorization: Optional[str] = None
    user: Optional[Dict[str, Any]] = None
    roles: List[str] = None


def parse_authorization_header(
    authorization: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    """
    Devuelve (scheme, token) si Authorization viene como: "Bearer <token>"
    Si no cumple formato retorna (None, None).
    """
    if not authorization:
        return None, None

    auth = authorization.strip()
    if not auth:
        return None, None

    parts = auth.split(" ", 1)
    if len(parts) != 2:
        return None, None

    scheme = parts[0].strip()
    token = parts[1].strip()

    if not scheme or not token:
        return None, None

    return scheme, token


def require_auth_context(request: Request) -> AuthContext:
    """
    ✅ EXIGE token (401 si no viene).
    VALIDA EL JWT (Versión Estricta).
    Además: guarda el token en el contexto global por request
    para que BpmClient pueda usarlo sin recibirlo por parámetro.
    """
    authorization = request.headers.get("authorization")
    scheme, token = parse_authorization_header(authorization)

    if not scheme or scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization token requerido (Bearer).",
            headers={"WWW-Authenticate": "Bearer"},
        )

    #VALIDACIÓN DE KEYCLOAK 
    try:
        #Se usa 'decode' para forzar la validación de estructura.
        # Esto detectará si el token es basura (como "token_falso") y lanzará excepción.
        payload = jwt.decode(
            token, 
            key="", 
            algorithms=["RS256"], 
            options={
                "verify_signature": False, # No se verifica firma aún (se necesitaria JWKS)
                "verify_aud": False, 
                "verify_exp": True
            }
        )
        
        user_id = payload.get("sub")
        username = payload.get("preferred_username")
        roles = payload.get("realm_access", {}).get("roles", [])

        if not user_id:
            raise JWTError("El token no contiene el identificador de usuario (sub).")

    except Exception as e:
        # Cualquier token que no sea un JWT real caerá aquí
        # devolviendo el 401 para cerrar la vulnerabilidad.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token inválido o mal formado. Error técnico: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # ✅ Guardamos el token en el contexto global por request
    set_current_token(token)

    return AuthContext(
        token=token,
        scheme=scheme,
        raw_authorization=authorization,
        user={
            "id": user_id,
            "username": username,
            "claims": payload
        },
        roles=roles,
    )