from fastapi import FastAPI, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session
from fastapi.middleware.cors import CORSMiddleware

from app.core.db import get_db
from app.core.auth import parse_authorization_header

from app.routers.catalogos import router as catalogos_router
from app.routers.expedientes import router as expedientes_router
from app.routers.sesan import router as sesan_router

app = FastAPI(title="MIS - Expediente API")

# ✅ Middleware: exigir token en todo excepto rutas públicas
PUBLIC_PATHS = {
    "/health",
    "/db-check",
    "/openapi.json",
    "/docs",
    "/redoc",
}

@app.middleware("http")
async def require_bearer_token_middleware(request: Request, call_next):
    path = request.url.path

    # permitir docs y endpoints públicos
    if path in PUBLIC_PATHS or path.startswith("/docs") or path.startswith("/redoc"):
        return await call_next(request)

    auth = request.headers.get("Authorization")
    scheme, token = parse_authorization_header(auth)

    if not scheme or scheme.lower() != "bearer" or not token:
        return JSONResponse(
            status_code=401,
            content={"detail": "Authorization token requerido (Bearer)."},
            headers={"WWW-Authenticate": "Bearer"},
        )

    # ✅ opcional: guardar token para reusarlo luego (Spiff / Keycloak)
    request.state.token = token

    return await call_next(request)

# Routers
app.include_router(catalogos_router)
app.include_router(expedientes_router)
app.include_router(sesan_router)

origins = [
    "http://localhost:5174",
    "http://127.0.0.1:5174",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/db-check")
def db_check(db: Session = Depends(get_db)):
    result = db.execute(text("SELECT 1")).scalar()
    return {"db": "ok", "result": result}
