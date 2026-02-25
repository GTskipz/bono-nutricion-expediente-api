# app/bpm/keycloak_token_cache.py
import time
import asyncio
from typing import Optional, Dict, Any

from app.bpm.keycloak_client import KeycloakClient

_lock = asyncio.Lock()
_cached: Optional[Dict[str, Any]] = None
_expires_at: float = 0.0  # epoch seconds


async def get_keycloak_token_cached(skew_seconds: int = 60) -> Dict[str, Any]:
    """
    Token de SERVICIO (password grant) cacheado en memoria.
    Se refresca automáticamente cuando está por expirar.
    """
    global _cached, _expires_at

    now = time.time()
    if _cached and now < (_expires_at - skew_seconds):
        return _cached

    async with _lock:
        now = time.time()
        if _cached and now < (_expires_at - skew_seconds):
            return _cached

        kc = KeycloakClient()
        token = await kc.get_token_password_grant()

        expires_in = int(token.get("expires_in", 0) or 0)
        _cached = token
        _expires_at = time.time() + max(expires_in, 0)

        return token


async def get_access_token_cached() -> str:
    """
    Devuelve access_token de servicio cacheado.
    """
    token = await get_keycloak_token_cached()
    access = token.get("access_token")
    if not access:
        raise RuntimeError("Keycloak no devolvió access_token")
    return access


async def get_access_token() -> str:
    """
    ✅ Estrategia final (BÁSICA):
    - Siempre usa token de servicio cacheado (NO passthrough).
    """
    return await get_access_token_cached()