from fastapi import FastAPI, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from fastapi.middleware.cors import CORSMiddleware
from app.core.db import get_db
from app.routers.catalogos import router as catalogos_router
from app.routers.expedientes import router as expedientes_router
from app.routers.sesan import router as sesan_router

app = FastAPI(title="MIS - Expediente API")
app.include_router(catalogos_router)
app.include_router(expedientes_router)
app.include_router(sesan_router)

origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
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
