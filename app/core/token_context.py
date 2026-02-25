from contextvars import ContextVar
from typing import Optional

_current_access_token: ContextVar[Optional[str]] = ContextVar("current_access_token", default=None)

def set_current_token(token: str) -> None:
    _current_access_token.set(token)

def get_current_token() -> Optional[str]:
    return _current_access_token.get()
