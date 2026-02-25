from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.token_context import set_current_token


class TokenContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        auth = request.headers.get("authorization") or ""
        if auth.lower().startswith("bearer "):
            token = auth.split(" ", 1)[1].strip()
            if token:
                set_current_token(token)
        return await call_next(request)
