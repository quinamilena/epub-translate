from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api import health, upload, glossary
from app.db.database import init_db
from app.services.job_manager import job_manager

app = FastAPI(title="EPUB Translate API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(upload.router, prefix="/api", tags=["translate"])
app.include_router(glossary.router, prefix="/api", tags=["glossary"])


@app.on_event("startup")
def on_startup():
    init_db()
    recovered = job_manager.recover_interrupted()
    if recovered:
        print(f"Jobs interrompidos marcados como 'paused': {recovered}")


@app.get("/")
def root():
    return {"message": "EPUB Translate API", "docs": "/docs"}
