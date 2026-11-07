from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Form
from fastapi.responses import FileResponse
from pathlib import Path
import os
import aiofiles
from app.services.job_manager import job_manager
from app.core.config import settings

router = APIRouter()


@router.post("/upload")
async def upload_epub(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    provider: str = Form(None),
    model: str = Form(None),
    api_key: str = Form(None, alias="apiKey"),
    baseUrl: str = Form(None),
):
    if not file.filename.endswith('.epub'):
        raise HTTPException(status_code=400, detail="Apenas arquivos .epub são permitidos")
    
    # Validar tamanho
    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > settings.max_upload_mb:
        raise HTTPException(status_code=400, detail=f"Arquivo muito grande. Máximo {settings.max_upload_mb}MB")
    
    # Salvar arquivo
    job_id = job_manager.create_job(file.filename)
    file_path = Path(settings.upload_dir) / f"{job_id}_{file.filename}"
    
    async with aiofiles.open(file_path, 'wb') as f:
        await f.write(content)
    
    # Configuração de tradução
    translation_config = {}
    if provider:
        translation_config["provider"] = provider
    if model:
        translation_config["model"] = model
    if api_key:
        translation_config["api_key"] = api_key
    if baseUrl:
        translation_config["base_url"] = baseUrl
    
    # Processar em background
    background_tasks.add_task(job_manager.process_job, job_id, str(file_path), translation_config)
    
    return {"job_id": job_id, "status": "pending", "message": "Upload realizado. Processamento iniciado."}


@router.get("/status/{job_id}")
def get_status(job_id: str):
    job = job_manager.get_job(job_id)
    return job


@router.get("/jobs")
def list_jobs():
    return {"jobs": job_manager.list_jobs()}


@router.post("/jobs/{job_id}/resume")
async def resume_job(
    job_id: str,
    background_tasks: BackgroundTasks,
    api_key: str = Form(None, alias="apiKey"),
):
    if not job_manager.exists(job_id):
        raise HTTPException(status_code=404, detail="Job não encontrado")
    background_tasks.add_task(job_manager.resume, job_id, api_key)
    return {"job_id": job_id, "status": "resuming"}


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str):
    if not job_manager.cancel_job(job_id):
        raise HTTPException(status_code=404, detail="Job não encontrado")
    return {"job_id": job_id, "status": "cancelling"}


@router.get("/download/{filename}")
def download_file(filename: str):
    file_path = Path(settings.output_dir) / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")
    
    return FileResponse(
        path=str(file_path),
        filename=f"traduzido_{filename}",
        media_type="application/epub+zip"
    )
