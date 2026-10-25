from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api import health, upload, glossary

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

@app.get("/")
def root():
    return {"message": "EPUB Translate API", "docs": "/docs"}
