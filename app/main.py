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
from app.core.token_context import set_current_token  # ✅ NUEVO: setear token global por request

from app.routers.catalogos import router as catalogos_router
from app.routers.expedientes import router as expedientes_router
from app.routers.sesan import router as sesan_router
from app.routers.reportes import router as reportes_router
from app.routers.bpm_router import router as bpm_router
from app.routers.sesan_documentos import router as sesan_documentos
from app.routers.bandejas import router as bandejas
from app.routers.cuentas_bancarias import router as cuentas_bancarias
from app.routers.pagos import router as pagos

# 1. Importar el nuevo router de Archivos (MinIO)
from app.routers.archivos import router as archivos_router

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
    # BPM (solo pruebas)
    "/bpm/auth/token",
    # Opcional: Si quieres probar la subida SIN token al inicio, descomenta esta línea:
    "/archivos/generar-url-subida"
}

@app.middleware("http")
async def require_bearer_token_middleware(request: Request, call_next):
    # Permitir preflight CORS (OPTIONS) sin auth
    if request.method == "OPTIONS":
        return await call_next(request)

    path = request.url.path

    # ✅ Permitir rutas públicas + docs + endpoints BPM
    # ❗ OJO: ya NO se whitelistea /sesan (antes impedía setear token)
    if (
        path in PUBLIC_PATHS
        or path.startswith("/docs")
        or path.startswith("/redoc")
        or path.startswith("/bpm")   # ✅ /bpm/tasks/by-row/{row_id}
        or path.startswith("/archivos/descargar")
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

    # ✅ Guardar token para uso posterior (Spiff / BPM)
    set_current_token(token)      # ✅ esto alimenta a BpmClient.get_current_token()
    request.state.token = token   # (opcional) si lo usas en otras partes

    return await call_next(request)

# =====================================================
# CORS (Configuración Profesional)
# =====================================================
origins = [
    "http://localhost:5174",    # Tu Frontend React (Vite)
    "http://localhost:3000",    # Por si usas otro puerto a veces
    "http://127.0.0.1:5174",    # Variante de localhost
    # Aquí se agregara la IP/Dominio del MIDES cuando se haga el despliegue
    "http://145.32.10.230",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,      # <--- Solo permitimos a los "amigos" de la lista
    allow_credentials=True,     # <--- ¡VITAL! Permite pasar el Token Bearer y Cookies
    allow_methods=["*"],
    allow_headers=["*"],
)

# =====================================================
# Routers
# =====================================================
app.include_router(catalogos_router)
app.include_router(expedientes_router)
app.include_router(sesan_router)
app.include_router(reportes_router)
app.include_router(bpm_router)
app.include_router(sesan_documentos)
app.include_router(archivos_router)
app.include_router(bandejas)
app.include_router(cuentas_bancarias)
app.include_router(pagos)

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
