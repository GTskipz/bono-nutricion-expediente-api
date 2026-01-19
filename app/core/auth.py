from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, List, Dict, Any

from fastapi import Header, HTTPException, status


@dataclass(frozen=True)
class AuthContext:
    token: str
    scheme: str = "Bearer"
    raw_authorization: Optional[str] = None
    user: Optional[Dict[str, Any]] = None
    roles: List[str] = None


def parse_authorization_header(authorization: Optional[str]) -> tuple[Optional[str], Optional[str]]:
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


def require_auth_context(authorization: Optional[str] = Header(default=None)) -> AuthContext:
    """
    ✅ EXIGE token (401 si no viene).
    ❗ No valida el token, solo verifica que exista.
    """
    scheme, token = parse_authorization_header(authorization)

    if not scheme or scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization token requerido (Bearer).",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return AuthContext(
        token=token,
        scheme=scheme,
        raw_authorization=authorization,
        user=None,
        roles=[],
    )
