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
    suffix = Path(file.filename).suffix.lower()
    if suffix not in {'.epub', '.pdf'}:
        raise HTTPException(
            status_code=400,
            detail="Apenas arquivos .epub ou .pdf são permitidos",
        )

    # Validar tamanho
    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > settings.max_upload_mb:
        raise HTTPException(status_code=400, detail=f"Arquivo muito grande. Máximo {settings.max_upload_mb}MB")

    if suffix == '.pdf' and b'%PDF-' not in content[:1024]:
        raise HTTPException(status_code=400, detail="Arquivo PDF inválido")
    if suffix == '.epub' and not content.startswith(b'PK'):
        raise HTTPException(status_code=400, detail="Arquivo EPUB inválido")

    # Salvar arquivo
    source_format = suffix.lstrip('.')
    job_id = job_manager.create_job(file.filename, source_format=source_format)
    safe_name = os.path.basename(file.filename.replace('\\', '/'))
    file_path = Path(settings.upload_dir) / f"{job_id}_{safe_name}"
    
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
    
    return {
        "job_id": job_id,
        "status": "pending",
        "source_format": source_format,
        "message": "Upload realizado. Processamento iniciado.",
    }


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


@router.post("/jobs/{job_id}/pause")
def pause_job(job_id: str):
    if not job_manager.exists(job_id):
        raise HTTPException(status_code=404, detail="Job não encontrado")
    if not job_manager.pause_job(job_id):
        raise HTTPException(
            status_code=409, detail="Job não está em tradução"
        )
    return {"job_id": job_id, "status": "pausing"}


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

    media_types = {
        '.epub': 'application/epub+zip',
        '.pdf': 'application/pdf',
    }
    media_type = media_types.get(
        file_path.suffix.lower(), 'application/octet-stream'
    )

    return FileResponse(
        path=str(file_path),
        filename=f"traduzido_{filename}",
        media_type=media_type,
    )
