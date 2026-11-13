import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.db.database import init_db
from app.repositories.job_repository import JobRepository
from app.services.epub_parser import PARSER_VERSION
from app.services.pdf_parser import PDF_PARSER_VERSION
from app.services.translation_pipeline import TranslationPipeline


class JobManager:
    """Fachada do pipeline. Todo o estado vive no banco, não em memória."""

    def __init__(self):
        init_db()
        self.job_repo = JobRepository()
        self.pipeline = TranslationPipeline()

    def create_job(self, filename: str, source_format: str = "epub") -> str:
        job_id = str(uuid.uuid4())
        source_format = (source_format or "epub").lower()
        parser_version = (
            PDF_PARSER_VERSION if source_format == "pdf" else PARSER_VERSION
        )
        self.job_repo.create(
            job_id,
            filename,
            source_format=source_format,
            parser_version=parser_version,
        )
        return job_id

    def exists(self, job_id: str) -> bool:
        return self.job_repo.get(job_id) is not None

    def get_job(self, job_id: str) -> Dict[str, Any]:
        job = self.job_repo.get(job_id)
        if not job:
            return {"status": "error", "message": "Job não encontrado"}
        return self._serialize(job)

    def list_jobs(self, limit: int = 50) -> List[Dict[str, Any]]:
        return [self._serialize(job) for job in self.job_repo.list(limit)]

    def _serialize(self, job: Dict[str, Any]) -> Dict[str, Any]:
        output_path = job.get("output_path")
        validation = self._load_json(job.get("validation_json"))
        errors = self._load_json(job.get("errors_json"))
        return {
            "job_id": job["id"],
            "status": job["status"],
            "progress": job["progress"],
            "message": job["message"],
            "filename": job["filename"],
            "source_format": job.get("source_format") or "epub",
            "context_blocks": job.get("context_blocks", 2),
            "download_url": (
                f"/download/{Path(output_path).name}" if output_path else None
            ),
            "output_path": output_path,
            "validation": validation,
            "translator_errors": errors,
            "total_chapters": job.get("total_chapters", 0),
            "done_chapters": job.get("done_chapters", 0),
            "total_blocks": job.get("total_blocks", 0),
            "done_blocks": job.get("done_blocks", 0),
        }

    @staticmethod
    def _load_json(value: Optional[str]) -> Any:
        if not value:
            return None
        try:
            return json.loads(value)
        except Exception:
            return None

    async def process_job(
        self,
        job_id: str,
        file_path: Optional[str] = None,
        translation_config: Optional[Dict[str, Any]] = None,
    ) -> None:
        translation_config = translation_config or {}

        fields: Dict[str, Any] = {}
        if file_path:
            fields["source_path"] = str(file_path)

        fields["provider"] = (
            translation_config.get("provider") or settings.translation_provider
        )
        fields["model"] = translation_config.get("model") or settings.translation_model
        fields["base_url"] = (
            translation_config.get("base_url") or settings.translation_base_url
        )
        if translation_config.get("glossary"):
            fields["glossary"] = translation_config["glossary"]
        if translation_config.get("api_key"):
            # A chave em si nunca é persistida.
            fields["has_api_key"] = 1

        self.job_repo.update(job_id, **fields)

        api_key = translation_config.get("api_key") or settings.translation_api_key
        await self.pipeline.run(job_id, api_key=api_key)

    async def resume(self, job_id: str, api_key: Optional[str] = None) -> None:
        job = self.job_repo.get(job_id)
        # "queued" tira o job de paused/cancelled antes de rodar; assim o
        # pipeline não confunde a retomada com um novo pedido de pausa.
        if job and job["status"] in ("cancelled", "paused", "pausing"):
            self.job_repo.update(
                job_id, status="queued", message="Retomando tradução..."
            )
        await self.pipeline.run(job_id, api_key=api_key)

    def cancel_job(self, job_id: str) -> bool:
        if not self.exists(job_id):
            return False
        self.job_repo.update(
            job_id, status="cancelled", message="Cancelamento solicitado"
        )
        return True

    def pause_job(self, job_id: str) -> bool:
        """Solicita a pausa. O pipeline para ao terminar o lote atual."""
        job = self.job_repo.get(job_id)
        if not job:
            return False
        if job["status"] not in ("queued", "extracting", "translating"):
            return False
        self.job_repo.update(
            job_id,
            status="pausing",
            message="Pausa solicitada. Aguardando o lote atual terminar...",
        )
        return True

    def recover_interrupted(self) -> int:
        return self.job_repo.recover_interrupted()


job_manager = JobManager()
