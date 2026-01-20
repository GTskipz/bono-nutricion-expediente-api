from dotenv import load_dotenv
from pathlib import Path

# =====================================================
# Cargar variables de entorno (.env)
# =====================================================
# main.py está en /app
# .env está en la raíz del proyecto
env_path = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=env_path)

from fastapi import FastAPI, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.auth import parse_authorization_header

from app.routers.catalogos import router as catalogos_router
from app.routers.expedientes import router as expedientes_router
from app.routers.sesan import router as sesan_router
from app.routers.reportes import router as reportes_router
from app.routers.bpm_router import router as bpm_router

# =====================================================
# App
# =====================================================
app = FastAPI(title="MIS - Expediente API")

# =====================================================
# Middleware de Autenticación
# =====================================================
PUBLIC_PATHS = {
    "/",
    "/health",
    "/db-check",
    "/openapi.json",
    "/docs",
    "/redoc",

    # ✅ BPM (solo pruebas)
    "/bpm/auth/token",
}

@app.middleware("http")
async def require_bearer_token_middleware(request: Request, call_next):
    path = request.url.path

    # ✅ Permitir rutas públicas + docs + endpoints BPM de prueba
    if (
        path in PUBLIC_PATHS
        or path.startswith("/docs")
        or path.startswith("/redoc")
        or path.startswith("/bpm")  # ✅ /bpm/tasks/by-row/{row_id}
    ):
        return await call_next(request)

    auth = request.headers.get("Authorization")
    scheme, token = parse_authorization_header(auth)

    if not scheme or scheme.lower() != "bearer" or not token:
        return JSONResponse(
            status_code=401,
            content={"detail": "Authorization token requerido (Bearer)."},
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Guardar token para uso posterior (Spiff / BPM)
    request.state.token = token

    return await call_next(request)

# =====================================================
# Routers
# =====================================================
app.include_router(catalogos_router)
app.include_router(expedientes_router)
app.include_router(sesan_router)
app.include_router(reportes_router)
app.include_router(bpm_router)

# =====================================================
# CORS
# =====================================================
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

# =====================================================
# Endpoints base
# =====================================================
@app.get("/")
def root():
    return {"service": "MIS - Expediente API"}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/db-check")
def db_check(db: Session = Depends(get_db)):
    result = db.execute(text("SELECT 1")).scalar()
    return {"db": "ok", "result": result}
